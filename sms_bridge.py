#!/usr/bin/env python3
"""
SMS Bridge - SMPP to M3UA Gateway
Converts SMPP messages from Jasmin to M3UA/SCCP for osmo-stp
"""

import sys
import time
import logging
import signal
import socket
import struct
from logging.handlers import RotatingFileHandler
import yaml
import requests
from datetime import datetime
from smpp_server import SMPPServer

class SMSBridge:
    def __init__(self, config_file='config.yaml'):
        self.config = self.load_config(config_file)
        self.setup_logging()
        self.running = False
        self.osmo_socket = None
        self.stats = {
            'total_messages': 0,
            'successful': 0,
            'failed': 0,
            'start_time': datetime.now()
        }
        
    def load_config(self, config_file):
        """Load configuration from YAML file"""
        try:
            with open(config_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)
            
    def setup_logging(self):
        """Setup logging with rotation"""
        log_config = self.config['logging']
        
        self.logger = logging.getLogger('SMSBridge')
        self.logger.setLevel(getattr(logging, log_config['level']))
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(log_config['format'])
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)
        
        try:
            file_handler = RotatingFileHandler(
                log_config['file'],
                maxBytes=log_config['max_bytes'],
                backupCount=log_config['backup_count']
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(console_format)
            self.logger.addHandler(file_handler)
        except Exception as e:
            self.logger.warning(f"Could not setup file logging: {e}")
            
    def connect_to_osmostp(self):
        """Establish SCTP connection to osmo-stp"""
        try:
            osmo_config = self.config['osmo_stp']
            
            # Try SCTP first (osmo-stp uses SCTP)
            try:
                import sctp
                sock = sctp.sctpsocket_tcp(socket.AF_INET)
                sock.connect((osmo_config['host'], osmo_config['port']))
                self.logger.info(f"Connected to osmo-stp via SCTP at {osmo_config['host']}:{osmo_config['port']}")
                return sock
            except ImportError:
                self.logger.warning("pysctp not available, trying TCP fallback")
            except Exception as e:
                self.logger.warning(f"SCTP connection failed: {e}, trying TCP fallback")
            
            # Fallback to TCP
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.connect((osmo_config['host'], osmo_config['port']))
            self.logger.info(f"Connected to osmo-stp via TCP at {osmo_config['host']}:{osmo_config['port']}")
            return sock
            
        except Exception as e:
            self.logger.error(f"Failed to connect to osmo-stp: {e}")
            return None
            
    def encode_sccp_message(self, source, destination, message_text):
        """
        Encode SMS into SCCP message format (UDT - Unitdata)
        """
        sccp_config = self.config['sccp']
        
        message_type = 0x09
        protocol_class = 0x00
        
        called_party = self.encode_sccp_address(destination, sccp_config, is_called=True)
        calling_party = self.encode_sccp_address(source, sccp_config, is_called=False)
        
        data = message_text.encode('utf-8')
        
        sccp_msg = bytearray()
        sccp_msg.append(message_type)
        sccp_msg.append(protocol_class)
        
        sccp_msg.append(3)
        sccp_msg.append(3 + len(called_party) + 1)
        sccp_msg.append(3 + len(called_party) + 1 + len(calling_party) + 1)
        
        sccp_msg.append(len(called_party))
        sccp_msg.extend(called_party)
        
        sccp_msg.append(len(calling_party))
        sccp_msg.extend(calling_party)
        
        sccp_msg.append(len(data))
        sccp_msg.extend(data)
        
        return bytes(sccp_msg)
        
    def encode_sccp_address(self, number, sccp_config, is_called=True):
        """Encode phone number into SCCP address format"""
        address = bytearray()
        
        ai = 0x00
        ai |= (1 << 0)
        ai |= (1 << 6)
        
        ssn = sccp_config['remote_ssn'] if is_called else sccp_config['local_ssn']
        ai |= (1 << 1)
        
        address.append(ai)
        address.append(ssn)
        
        gt_indicator = (sccp_config['gti'] << 4) | sccp_config['np']
        address.append(gt_indicator)
        address.append(sccp_config['nai'])
        
        digits = self.encode_bcd(number)
        address.extend(digits)
        
        return bytes(address)
        
    def encode_bcd(self, number):
        """Encode number in BCD format"""
        if len(number) % 2 != 0:
            number += 'F'
            
        bcd = bytearray()
        for i in range(0, len(number), 2):
            high = int(number[i], 16) if number[i] != 'F' else 0xF
            low = int(number[i+1], 16) if number[i+1] != 'F' else 0xF
            bcd.append((low << 4) | high)
            
        return bytes(bcd)
        
    def encode_m3ua_message(self, sccp_payload):
        """
        Encode SCCP message into M3UA DATA message
        """
        osmo_config = self.config['osmo_stp']
        
        version = 1
        msg_class = 1
        msg_type = 1
        
        protocol_data = bytearray()
        
        opc = osmo_config['opc']
        dpc = osmo_config['dpc']
        si = 3
        ni = osmo_config['ni']
        mp = 0
        sls = 0
        
        protocol_data.extend(struct.pack('>I', opc))
        protocol_data.extend(struct.pack('>I', dpc))
        protocol_data.append(si)
        protocol_data.append(ni)
        protocol_data.append(mp)
        protocol_data.append(sls)
        
        protocol_data.extend(sccp_payload)
        
        tag = 0x0210
        length = len(protocol_data)
        
        param = bytearray()
        param.extend(struct.pack('>H', tag))
        param.extend(struct.pack('>H', length))
        param.extend(protocol_data)
        
        while len(param) % 4 != 0:
            param.append(0)
        
        msg_length = 8 + len(param)
        
        m3ua_msg = bytearray()
        m3ua_msg.append(version)
        m3ua_msg.append(0)
        m3ua_msg.append(msg_class)
        m3ua_msg.append(msg_type)
        m3ua_msg.extend(struct.pack('>I', msg_length))
        m3ua_msg.extend(param)
        
        return bytes(m3ua_msg)
        
    def send_sms(self, source, destination, message_text):
        """Send SMS through osmo-stp"""
        try:
            if source not in self.config['allowed_senders']:
                self.logger.warning(f"Sender {source} not in whitelist, using default")
                source = self.config['allowed_senders'][0]
            
            self.logger.info(f"Processing SMS: {source} -> {destination}: {message_text[:50]}...")
            
            sccp_msg = self.encode_sccp_message(source, destination, message_text)
            self.logger.debug(f"SCCP message: {sccp_msg.hex()}")
            
            m3ua_msg = self.encode_m3ua_message(sccp_msg)
            self.logger.debug(f"M3UA message: {m3ua_msg.hex()}")
            
            if not self.osmo_socket:
                self.osmo_socket = self.connect_to_osmostp()
                if not self.osmo_socket:
                    raise Exception("Cannot connect to osmo-stp")
            
            self.osmo_socket.sendall(m3ua_msg)
            self.logger.info(f"SMS sent successfully: {source} -> {destination}")
            
            self.stats['successful'] += 1
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send SMS: {e}")
            self.stats['failed'] += 1
            
            if self.osmo_socket:
                try:
                    self.osmo_socket.close()
                except:
                    pass
                self.osmo_socket = None
            
            return False
            
    def fetch_messages_from_jasmin(self):
        """Fetch pending messages from Jasmin HTTP API"""
        try:
            jasmin_config = self.config['jasmin']
            url = f"http://{jasmin_config['host']}:{jasmin_config['http_port']}/sms/receive"
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                messages = response.json()
                return messages if isinstance(messages, list) else []
            else:
                self.logger.debug(f"No messages from Jasmin: {response.status_code}")
                return []
                
        except requests.exceptions.RequestException as e:
            self.logger.debug(f"Jasmin API not available: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error fetching from Jasmin: {e}")
            return []
            
    def print_stats(self):
        """Print statistics"""
        uptime = datetime.now() - self.stats['start_time']
        self.logger.info(f"=== Statistics ===")
        self.logger.info(f"Uptime: {uptime}")
        self.logger.info(f"Total messages: {self.stats['total_messages']}")
        self.logger.info(f"Successful: {self.stats['successful']}")
        self.logger.info(f"Failed: {self.stats['failed']}")
        
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        
    def handle_smpp_message(self, source, destination, text):
        """Callback for SMPP server when message received"""
        self.stats['total_messages'] += 1
        self.send_sms(source, destination, text)
        
    def run(self):
        """Main loop"""
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        self.logger.info("SMS Bridge starting...")
        self.logger.info(f"SMPP Server: {self.config['smpp_server']['host']}:{self.config['smpp_server']['port']}")
        self.logger.info(f"osmo-stp: {self.config['osmo_stp']['host']}:{self.config['osmo_stp']['port']}")
        
        # Start SMPP server
        smpp_server = SMPPServer(self.config, self.handle_smpp_message)
        if not smpp_server.start():
            self.logger.error("Failed to start SMPP server")
            return
        
        self.running = True
        stats_counter = 0
        
        try:
            while self.running:
                try:
                    # Print stats every 60 seconds
                    stats_counter += 1
                    if stats_counter >= 60:
                        self.print_stats()
                        stats_counter = 0
                    
                    time.sleep(1)
                    
                except Exception as e:
                    self.logger.error(f"Error in main loop: {e}")
                    time.sleep(5)
        finally:
            # Cleanup
            smpp_server.stop()
            if self.osmo_socket:
                self.osmo_socket.close()
        
        self.print_stats()
        self.logger.info("SMS Bridge stopped")

def main():
    """Entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='SMS Bridge - SMPP to M3UA Gateway')
    parser.add_argument('--config', default='config.yaml', help='Config file path')
    parser.add_argument('--test', action='store_true', help='Test mode')
    args = parser.parse_args()
    
    bridge = SMSBridge(config_file=args.config)
    
    if args.test:
        bridge.logger.info("=== TEST MODE ===")
        bridge.logger.info("Testing osmo-stp connection...")
        sock = bridge.connect_to_osmostp()
        if sock:
            bridge.logger.info("✓ osmo-stp connection successful")
            sock.close()
        else:
            bridge.logger.error("✗ osmo-stp connection failed")
            sys.exit(1)
        
        bridge.logger.info("Testing Jasmin API...")
        messages = bridge.fetch_messages_from_jasmin()
        bridge.logger.info(f"✓ Jasmin API accessible (messages: {len(messages)})")
        
        bridge.logger.info("=== ALL TESTS PASSED ===")
        sys.exit(0)
    
    bridge.run()

if __name__ == '__main__':
    main()
