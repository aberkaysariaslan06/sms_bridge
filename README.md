# SMS Bridge - SMPP to M3UA Gateway

## Neden Bu Bridge'e Ihtiyac Varu

Bu bridge, SMPP uzerinden gelen mesajlari M3UA/SCCP tarafina aktarir ve entegrasyonu Python tabanli, bakimi kolay bir servise tasir.

### Hedeflenen Faydalar

- Harici binary bagimliligini minimuma indirir
- Kurulum ve guncelleme surecini basit tutar
- Loglama, hata yakalama ve yeniden baglanma gibi operasyonel ihtiyaclari karsilar
- Konfigurasyon ile ortama kolayca uyarlanir

### Kullanildigi Senaryolar

- Eski bir gateway/binary yerine acik ve bakimi kolay bir bridge kullanmak
- SMPP -> M3UA/SCTP entegrasyonunu merkezilesirmek
- Operasyonel gorunurlugu arttirmak (log, metrik, test modu)

---

## Mimari

```
[SMPP Gateway] -- HTTP/REST --> [SMS Bridge] -- M3UA/SCTP --> [STP] -- M3UA/SIGTRAN --> [Operator SMSC]

Notes:
- Ports and hosts are configurable in config.yaml.
- Point codes and routing values are environment-specific.
```

---

## Protokol Detaylari

### SMPP → SCCP Donusumu

**SMPP Mesaji:**
```
Source: <SENDER_ID>
Destination: <DESTINATION_MSISDN>
Text: "Test mesaji"
```

**SCCP Mesaji:**
```
Called Party Address:
  - GTI: 4 (E.164)
  - NP: 1 (ISDN/Telephony)
  - NAI: 4 (International)
  - Address: <DESTINATION_MSISDN>

Calling Party Address:
  - GTI: 4
  - NP: 1
  - NAI: 4
  - Address: <SENDER_ID>

Data: GSM MAP Forward-SM payload
```

### M3UA Encapsulation

```
M3UA Header:
  - Version: 1
  - Message Class: Transfer Messages (1)
  - Message Type: DATA (1)
  - OPC: <OPC> (SMSC point code)
  - DPC: <DPC> (stp point code)
  - SLS: 0
  - SI: SCCP (3)

Payload: SCCP message
```

---

## Kurulum

### 1. Gereksinimler

```bash
# Python 3.8+ gerekli
python3 --version

# Sistem paketleri
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
```

### 2. Proje Kurulumu

```bash
# Proje dizinine git
cd /opt/sms-bridge

# Virtual environment olustur
python3 -m venv venv
source venv/bin/activate

# Bagimliliklari kur
pip install -r requirements.txt
```

### 3. Konfigurasyon

`config.yaml` dosyasini duzenleyin:

```yaml
jasmin:
  host: "<HOST>"
  http_port: <HTTP_PORT>
  poll_interval: 1

osmo_stp:
  host: "<HOST>"
  port: <OSMO_STP_PORT>
  opc: <OPC>
  dpc: <DPC>
```

### 4. Log Dizini Olustur

```bash
sudo mkdir -p /var/log/sms-bridge
sudo chown smsbridge:smsbridge /var/log/sms-bridge
```

### 5. Test

```bash
# Manuel test
python3 sms_bridge.py --test

# Normal calistirma
python3 sms_bridge.py
```

### 6. Systemd Service (Production)

```bash
# Service dosyasini kopyala
sudo cp systemd/sms-bridge.service /etc/systemd/system/

# Service'i etkinlestir
sudo systemctl daemon-reload
sudo systemctl enable sms-bridge
sudo systemctl start sms-bridge

# Durumu kontrol et
sudo systemctl status sms-bridge
```

---

## Kullanim

### Manuel Baslatma (Test icin)

```bash
cd /opt/sms-bridge
source venv/bin/activate
python3 sms_bridge.py
```

### Production (Systemd)

```bash
# Baslat
sudo systemctl start sms-bridge

# Durdur
sudo systemctl stop sms-bridge

# Restart
sudo systemctl restart sms-bridge

# Log'lari izle
sudo journalctl -u sms-bridge -f
```

---

## Monitoring

### Log Dosyalari

```bash
# Bridge log'lari
tail -f /var/log/sms-bridge/bridge.log

# Systemd log'lari
journalctl -u sms-bridge -f

# osmo-stp log'lari
journalctl -u osmo-stp -f
```

### Metrikler

Bridge, asagidaki metrikleri loglar:
- Toplam islenen mesaj sayisi
- Basarili/basarisiz gonderim
- Ortalama islem suresi
- SCTP baglanti durumu

---

## Troubleshooting

### Bridge baslamiyor

```bash
# Python versiyonu kontrol
python3 --version  # 3.8+ olmali

# Bagimliliklar kurulu muu
pip list | grep -E "pyyaml|requests"

# Config dosyasi dogru muu
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

### osmo-stp'ye baglanamiyor

```bash
# osmo-stp calisiyor muu
systemctl status osmo-stp

# Port dinliyor muu
ss -tlnp | rg <OSMO_STP_PORT>

# Firewall engeli var miu
sudo iptables -L -n | rg <OSMO_STP_PORT>
```

### Jasmin'den mesaj gelmiyor

```bash
# Jasmin calisiyor muu
systemctl status jasmin

# HTTP API erisilebilir miu
curl http://<JASMIN_HOST>:<JASMIN_HTTP_PORT>/sms/receive

# SMPP baglantisi var miu
telnet <JASMIN_HOST> <JASMIN_SMPP_PORT>
```

---

## Guvenlik

### Best Practices

1. **Virtual Environment Kullan**
   - Sistem Python'una dokunma
   - Izole calisma ortami

2. **Minimum Privilege**
   - Bridge'i root olarak calistirma
   - Dedicated user kullan

3. **Log Rotation**
   - Disk dolmasini onle
   - Eski log'lari arsivle

4. **Config Dosyasi Izinleri**
   ```bash
   chmod 600 config.yaml
   chown smsbridge:smsbridge config.yaml
   ```

---

## Lisans

MIT License

---

## Destek

Destek bilgileri internal kanallar ile paylasilir.
