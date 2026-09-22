# MITM altyapısı kurulum notları (referans)

Bu, §6'da anlatılan altyapıyı kurmak için kullanılan komutların özetidir.
Kendi ortamınıza göre arayüz adı / IP aralığı değiştirilmelidir. Bu adımların
çoğu root yetkisi gerektirir.

## 1. Ağ arayüzünü hazırla

```sh
nmcli device set <IFACE> managed no   # NetworkManager'ı bu arayüzden çek
sudo ip addr flush dev <IFACE>
sudo ip addr add 192.168.50.1/24 dev <IFACE>
sudo ip link set <IFACE> up
```

## 2. dnsmasq (DHCP+DNS)

```sh
sudo pacman -S dnsmasq   # dağıtıma göre değişir
sudo setcap 'cap_net_bind_service,cap_net_admin,cap_net_raw=+ep' "$(readlink -f "$(which dnsmasq)")"
dnsmasq -C dnsmasq_goflex.conf --no-daemon
```

`dnsmasq_goflex.conf.example` dosyasına bakın.

## 3. iptables NAT yönlendirmesi

Docker kullanıyorsanız kendi `DOCKER` NAT zincirini PREROUTING'in başına koyar;
kurallarınızı `-I ... 1` ile en başa eklemeniz gerekir yoksa paketler Docker'a
gider:

```sh
sudo iptables -t nat -I PREROUTING 1 -i <IFACE> -p tcp --dport 80  -j REDIRECT --to-port 8080
sudo iptables -t nat -I PREROUTING 2 -i <IFACE> -p tcp --dport 443 -j REDIRECT --to-port 8443
sudo iptables -t nat -L PREROUTING -n -v --line-numbers   # doğrulama
```

## 4. Yakalayıcı sunucu

```sh
BIND_IP=192.168.50.1 CERTFILE=selfsigned.pem LOGFILE=requests.log python3 catcher.py
```

## 5. Eski OpenSSL (SSLv2-uyumlu ClientHello için)

Modern OpenSSL (1.1.0+) SSLv2-uyumlu ClientHello'yu ayrıştıramıyor. Çözüm:
izole bir Docker container'ında eski bir OpenSSL çalıştırmak.

```sh
docker run --name legacy-ssl --network host -d debian:8 sleep infinity
docker exec legacy-ssl bash -c "
  echo 'deb http://archive.debian.org/debian jessie main' > /etc/apt/sources.list
  echo 'deb http://archive.debian.org/debian-security jessie/updates main' >> /etc/apt/sources.list
  apt-get -o Acquire::Check-Valid-Until=false update
  apt-get -o Acquire::Check-Valid-Until=false install -y --allow-unauthenticated openssl
"
docker cp cert.pem legacy-ssl:/cert.pem
docker cp key.pem  legacy-ssl:/key.pem

# İmajı commit edip tekrar kullanılabilir hale getir:
docker commit legacy-ssl legacy-ssl-img
docker rm -f legacy-ssl

# Kendi kendini yeniden başlatan (her bağlantıdan sonra tek seferlik kapanıyor) container:
docker run --name legacy-ssl --network host --restart unless-stopped -d legacy-ssl-img \
  bash -c 'while true; do openssl s_server -accept 8443 -cert /cert.pem -key /key.pem -debug -state; sleep 0.2; done'
```

**Bilinen sorun:** Bu container bazen dış bir bağlantı olmadan da kendi kendine
kapanıp yeniden başlıyor (sebebi netleştirilemedi). Üretim kullanımı için daha
sağlam bir supervisor (örn. `s6-overlay`, gerçek bir init sistemi) önerilir.
