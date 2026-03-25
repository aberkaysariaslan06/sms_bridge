#!/usr/bin/env python3
"""
SMPP Server Module
Listens for SMPP connections from Jasmin and forwards messages to Bridge
"""

import socket
import struct
import threading
import logging
from datetime import datetime

class SMPPServer:
    """Simple SMPP Server for receiving messages from Jasmin"""
    
    # SMPP Command IDs
    BIND_TRANSMITTER = 0x00000001
    BIND_RECEIVER = 0x00000002
    BIND_TRANSCEIVER = 0x00000009
    BIND_TRANSMITTER_RESP = 0x80000001
    BIND_RECEIVER_RESP = 0x80000002
    BIND_TRANSCEIVER_RESP = 0x80000009
    SUBMIT_SM = 0x00000004
    SUBMIT_SM_RESP = 0x80000004
    DELIVER_SM = 0x00000005
    DELIVER_SM_RESP = 0x80000005
    UNBIND = 0x00000006
    UNBIND_RESP = 0x80000006
    ENQUIRE_LINK = 0x00000015
    ENQUIRE_LINK_RESP = 0x80000015
    
    # SMPP Status
    ESME_ROK = 0x00000000
    ESME_RINVPASWD = 0x00000001
    ESME_RINVSYSID = 0x00000002
    
    def __init__(self, config, message_callback):
        self.config = config
        self.message_callback = message_callback
        self.logger = logging.getLogger('SMPPServer')
        self.logger.setLevel(logging.DEBUG)
        
        # Add console handler if not already present
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        self.running = False
        self.server_socket = None
        self.clients = []
        
    def start(self):
        """Start SMPP server"""
        try:
            smpp_config = self.config['smpp_server']
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((smpp_config['host'], smpp_config['port']))
            self.server_socket.listen(5)
            
            self.running = True
            self.logger.info(f"SMPP Server listening on {smpp_config['host']}:{smpp_config['port']}")
            
            # Accept connections in separate thread
            accept_thread = threading.Thread(target=self._accept_connections, daemon=True)
            accept_thread.start()
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to start SMPP server: {e}")
            return False
            
    def stop(self):
        """Stop SMPP server"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        for client in self.clients:
            try:
                client.close()
            except:
                pass
        self.logger.info("SMPP Server stopped")
        
    def _accept_connections(self):
        """Accept incoming SMPP connections"""
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                self.logger.info(f"New SMPP connection from {address}")
                
                # Handle client in separate thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, address),
                    daemon=True
                )
                client_thread.start()
                self.clients.append(client_socket)
                
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error accepting connection: {e}")
                    
    def _handle_client(self, client_socket, address):
        """Handle SMPP client connection"""
        bound = False
        sequence_number = 1
        
        try:
            while self.running:
                # Read PDU header (16 bytes)
                header = self._recv_exact(client_socket, 16)
                if not header:
                    break
                    
                command_length, command_id, command_status, seq_num = struct.unpack('>IIII', header)
                
                # Read PDU body
                body_length = command_length - 16
                body = b''
                if body_length > 0:
                    body = self._recv_exact(client_socket, body_length)
                    if not body:
                        break
                
                self.logger.info(f"Received PDU: cmd_id=0x{command_id:08x}, seq={seq_num}, len={command_length}")
                
                # Handle PDU
                if command_id == self.BIND_TRANSCEIVER:
                    bound = self._handle_bind(client_socket, body, seq_num)
                    
                elif command_id == self.SUBMIT_SM:
                    if bound:
                        self._handle_submit_sm(client_socket, body, seq_num)
                    else:
                        self.logger.warning("Received SUBMIT_SM before BIND")
                        
                elif command_id == self.ENQUIRE_LINK:
                    self._send_enquire_link_resp(client_socket, seq_num)
                    
                elif command_id == self.UNBIND:
                    self._send_unbind_resp(client_socket, seq_num)
                    break
                    
                else:
                    self.logger.warning(f"Unknown command_id: 0x{command_id:08x}")
                    
        except Exception as e:
            self.logger.error(f"Error handling client {address}: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
            if client_socket in self.clients:
                self.clients.remove(client_socket)
            self.logger.info(f"Client {address} disconnected")
            
    def _recv_exact(self, sock, length):
        """Receive exact number of bytes"""
        data = b''
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return data
        
    def _handle_bind(self, client_socket, body, seq_num):
        """Handle BIND_TRANSCEIVER"""
        try:
            # Parse BIND PDU
            parts = body.split(b'\x00')
            system_id = parts[0].decode('latin-1') if len(parts) > 0 else ''
            password = parts[1].decode('latin-1') if len(parts) > 1 else ''
            
            self.logger.info(f"BIND request: system_id={system_id}")
            
            # Validate credentials
            smpp_config = self.config['smpp_server']
            if system_id == smpp_config['system_id'] and password == smpp_config['password']:
                status = self.ESME_ROK
                self.logger.info(f"BIND successful for {system_id}")
            else:
                status = self.ESME_RINVPASWD
                self.logger.warning(f"BIND failed for {system_id}: invalid credentials")
            
            # Send BIND_TRANSCEIVER_RESP
            system_id = str(smpp_config.get('system_id', ''))
            resp_body = (system_id + '\x00').encode('ascii', errors='ignore')
            resp_length = 16 + len(resp_body)
            resp_header = struct.pack('>IIII', resp_length, self.BIND_TRANSCEIVER_RESP, status, seq_num)
            
            try:
                client_socket.sendall(resp_header + resp_body)
                self.logger.info(f"BIND response sent: {resp_length} bytes, status={status}")
            except Exception as send_err:
                self.logger.error(f"Failed to send BIND response: {send_err}")
                return False
            
            return status == self.ESME_ROK
            
        except Exception as e:
            self.logger.error(f"Error handling BIND: {e}")
            return False
            
    def _handle_submit_sm(self, client_socket, body, seq_num):
        """Handle SUBMIT_SM"""
        try:
            # Parse SUBMIT_SM PDU (simplified)
            offset = 0
            
            # service_type (C-Octet String)
            service_type_end = body.find(b'\x00', offset)
            service_type = body[offset:service_type_end].decode('latin-1')
            offset = service_type_end + 1
            
            # source_addr_ton, source_addr_npi
            source_addr_ton = body[offset]
            source_addr_npi = body[offset + 1]
            offset += 2
            
            # source_addr (C-Octet String)
            source_addr_end = body.find(b'\x00', offset)
            source_addr = body[offset:source_addr_end].decode('latin-1')
            offset = source_addr_end + 1
            
            # dest_addr_ton, dest_addr_npi
            dest_addr_ton = body[offset]
            dest_addr_npi = body[offset + 1]
            offset += 2
            
            # destination_addr (C-Octet String)
            dest_addr_end = body.find(b'\x00', offset)
            destination_addr = body[offset:dest_addr_end].decode('latin-1')
            offset = dest_addr_end + 1
            
            # esm_class, protocol_id, priority_flag
            offset += 3
            
            # schedule_delivery_time (C-Octet String)
            schedule_end = body.find(b'\x00', offset)
            offset = schedule_end + 1
            
            # validity_period (C-Octet String)
            validity_end = body.find(b'\x00', offset)
            offset = validity_end + 1
            
            # registered_delivery, replace_if_present_flag, data_coding, sm_default_msg_id
            offset += 4
            
            # sm_length
            sm_length = body[offset]
            offset += 1
            
            # short_message
            short_message = body[offset:offset + sm_length]
            try:
                message_text = short_message.decode('utf-8')
            except:
                message_text = short_message.decode('latin-1')
            
            self.logger.info(f"SUBMIT_SM: {source_addr} -> {destination_addr}: {message_text[:50]}...")
            
            # Call message callback
            if self.message_callback:
                self.message_callback(source_addr, destination_addr, message_text)
            
            # Send SUBMIT_SM_RESP
            message_id = f"{int(datetime.now().timestamp())}"
            resp_body = message_id.encode('latin-1') + b'\x00'
            resp_length = 16 + len(resp_body)
            resp_header = struct.pack('>IIII', resp_length, self.SUBMIT_SM_RESP, self.ESME_ROK, seq_num)
            client_socket.sendall(resp_header + resp_body)
            
        except Exception as e:
            self.logger.error(f"Error handling SUBMIT_SM: {e}")
            # Send error response
            resp_length = 16 + 1
            resp_header = struct.pack('>IIII', resp_length, self.SUBMIT_SM_RESP, 0x00000008, seq_num)
            client_socket.sendall(resp_header + b'\x00')
            
    def _send_enquire_link_resp(self, client_socket, seq_num):
        """Send ENQUIRE_LINK_RESP"""
        resp_length = 16
        resp_header = struct.pack('>IIII', resp_length, self.ENQUIRE_LINK_RESP, self.ESME_ROK, seq_num)
        client_socket.sendall(resp_header)
        
    def _send_unbind_resp(self, client_socket, seq_num):
        """Send UNBIND_RESP"""
        resp_length = 16
        resp_header = struct.pack('>IIII', resp_length, self.UNBIND_RESP, self.ESME_ROK, seq_num)
        client_socket.sendall(resp_header)
