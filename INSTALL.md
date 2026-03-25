# SMS Bridge Kurulum Rehberi

## Hizli Baslangic

### 1. Log Dizini Olustur

```bash
sudo mkdir -p /var/log/sms-bridge
sudo chown smsbridge:smsbridge /var/log/sms-bridge
```

### 2. Virtual Environment Kur

```bash
cd /opt/sms-bridge

# Virtual environment olustur
python3 -m venv venv

# Aktif et
source venv/bin/activate

# Bagimliliklari kur
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Executable Izinleri

```bash
chmod +x sms_bridge.py
```

### 4. Test Et

```bash
# osmo-stp baglanti testi
python3 sms_bridge.py --test
```

**Beklenen cikti:**
```
✓ osmo-stp connection successful
✓ Jasmin API accessible
=== ALL TESTS PASSED ===
```

### 5. Manuel Calistir (Test)

```bash
# Terminal'de calistir
python3 sms_bridge.py
```

**Cikis:** `Ctrl+C`

### 6. Systemd Service Kur (Production)

```bash
# Service dosyasini kopyala
sudo cp systemd/sms-bridge.service /etc/systemd/system/

# Systemd'yi yenile
sudo systemctl daemon-reload

# Service'i etkinlestir (boot'ta otomatik baslat)
sudo systemctl enable sms-bridge

# Service'i baslat
sudo systemctl start sms-bridge

# Durumu kontrol et
sudo systemctl status sms-bridge
```

---

## Kontrol Komutlari

### Service Yonetimi

```bash
# Baslat
sudo systemctl start sms-bridge

# Durdur
sudo systemctl stop sms-bridge

# Yeniden baslat
sudo systemctl restart sms-bridge

# Durum
sudo systemctl status sms-bridge

# Boot'ta otomatik baslatmayi kapat
sudo systemctl disable sms-bridge
```

### Log Izleme

```bash
# Canli log izle (systemd)
sudo journalctl -u sms-bridge -f

# Son 100 satir
sudo journalctl -u sms-bridge -n 100

# Bugunun loglari
sudo journalctl -u sms-bridge --since today

# Bridge log dosyasi
tail -f /var/log/sms-bridge/bridge.log
```

### Baglanti Kontrolleri

```bash
# osmo-stp calisiyor muu
systemctl status osmo-stp

# osmo-stp port dinliyor muu
ss -tlnp | rg <OSMO_STP_PORT>

# Bridge osmo-stp'ye bagli miu
ss -tn | rg <OSMO_STP_PORT>
```

---

## Troubleshooting

### Sorun: Bridge baslamiyor

**Kontrol:**
```bash
# Config dosyasi dogru muu
python3 -c "import yaml; print(yaml.safe_load(open('config.yaml')))"

# Virtual environment aktif miu
which python3  # /opt/sms-bridge/venv/bin/python3 olmali

# Bagimliliklar kurulu muu
pip list | grep -E "requests|PyYAML"
```

### Sorun: osmo-stp'ye baglanamiyor

**Kontrol:**
```bash
# osmo-stp calisiyor muu
systemctl status osmo-stp

# Port acik miu
telnet <OSMO_STP_HOST> <OSMO_STP_PORT>

# Firewall engeli var miu
sudo iptables -L -n | rg <OSMO_STP_PORT>
```

**Cozum:**
```bash
# osmo-stp'yi baslat
sudo systemctl start osmo-stp

# Bridge'i yeniden baslat
sudo systemctl restart sms-bridge
```

### Sorun: Log dosyasi yazamiyor

**Kontrol:**
```bash
# Dizin var miu
ls -ld /var/log/sms-bridge

# Izinler dogru muu
ls -l /var/log/sms-bridge/
```

**Cozum:**
```bash
sudo mkdir -p /var/log/sms-bridge
sudo chown smsbridge:smsbridge /var/log/sms-bridge
sudo chmod 755 /var/log/sms-bridge
```

---

## Guncelleme

### Kod Guncellemesi

```bash
cd /opt/sms-bridge

# Service'i durdur
sudo systemctl stop sms-bridge

# Kodu guncelle (git pull veya manuel)
# ...

# Virtual environment'i guncelle
source venv/bin/activate
pip install --upgrade -r requirements.txt

# Service'i baslat
sudo systemctl start sms-bridge
```

### Config Guncellemesi

```bash
# config.yaml'i duzenle
nano config.yaml

# Service'i yeniden baslat
sudo systemctl restart sms-bridge

# Log'lari kontrol et
sudo journalctl -u sms-bridge -f
```

---

## Kaldirma

```bash
# Service'i durdur ve devre disi birak
sudo systemctl stop sms-bridge
sudo systemctl disable sms-bridge

# Service dosyasini sil
sudo rm /etc/systemd/system/sms-bridge.service
sudo systemctl daemon-reload

# Proje dizinini sil
rm -rf /opt/sms-bridge

# Log dizinini sil (opsiyonel)
sudo rm -rf /var/log/sms-bridge
```

---

## Performans Izleme

### CPU ve Memory Kullanimi

```bash
# Service resource kullanimi
systemctl status sms-bridge

# Detayli resource bilgisi
ps aux | grep sms_bridge

# Memory kullanimi
pmap $(pgrep -f sms_bridge.py)
```

### Istatistikler

Bridge her 60 saniyede bir istatistik loglar:
- Toplam mesaj sayisi
- Basarili/basarisiz gonderimler
- Uptime

```bash
# Istatistikleri goster
grep "Statistics" /var/log/sms-bridge/bridge.log
```

---

## Guvenlik

### Config Dosyasi Izinleri

```bash
# Sadece smsbridge kullanicisi okuyabilsin
chmod 600 config.yaml
chown smsbridge:smsbridge config.yaml
```

### Service Izolasyonu

Service dosyasi zaten `User=smsbridge` ile calisiyor, root yetkisi yok.

### Firewall (Opsiyonel)

```bash
# Sadece localhost'tan osmo-stp'ye erisim
sudo iptables -A INPUT -p tcp --dport <OSMO_STP_PORT> -s <LOCAL_HOST> -j ACCEPT
sudo iptables -A INPUT -p tcp --dport <OSMO_STP_PORT> -j DROP
```

---

## Yedekleme

### Onemli Dosyalar

```bash
# Config yedekle
cp config.yaml config.yaml.backup

# Tum projeyi yedekle
tar -czf sms-bridge-backup-$(date +%Y%m%d).tar.gz /opt/sms-bridge

# Log'lari yedekle
tar -czf sms-bridge-logs-$(date +%Y%m%d).tar.gz /var/log/sms-bridge
```

---

## Destek

Destek bilgileri internal kanallar ile paylasilir.


Sorun yasarsaniz:

1. Log dosyalarini kontrol edin
2. Test modunu calistirin: `python3 sms_bridge.py --test`
3. osmo-stp durumunu kontrol edin
