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
  echo 'deb [trusted=yes] http://archive.debian.org/debian jessie main' > /etc/apt/sources.list
  echo 'deb [trusted=yes] http://archive.debian.org/debian-security jessie/updates main' >> /etc/apt/sources.list
  apt-get -o Acquire::Check-Valid-Until=false -o Acquire::AllowInsecureRepositories=true update
  apt-get -o Acquire::Check-Valid-Until=false -o Acquire::AllowInsecureRepositories=true \
    install -y --allow-unauthenticated openssl
"
docker cp cert.pem legacy-ssl:/cert.pem
docker cp key.pem  legacy-ssl:/key.pem

# Temiz Jessie kurulumunu yeni bir imaj olarak sakla (eski goflex-legacy-ssl-img'i kullanma):
docker commit legacy-ssl goflex-legacy-ssl-clean:test
docker stop legacy-ssl
docker rm legacy-ssl

# stdin'i açık tutan kalıcı sunucu. Bu pipe zorunludur; aşağıdaki kök neden notuna bakın.
docker run --name legacy-ssl --network host --restart unless-stopped -d \
  goflex-legacy-ssl-clean:test \
  sh -c 'tail -f /dev/null | openssl s_server -accept 8443 -cert /cert.pem -key /key.pem -debug -state'
```

**`-ssl2` bayrağı DENENDİ, işe yaramadı:** Bu build (Debian 8'in openssl 1.0.1t paketi)
`-ssl2`'yi "unknown option" ile reddediyor — `s_server --help`'in listelemesi yanıltıcı, o
yardım metni statik ve gerçek derleme desteğini yansıtmıyor (muhtemelen Debian paketi
`no-ssl2` ile derlenmiş). 2026-09-25'te denenip geri alındı.

**Kök neden (2026-09-25'te yerel olarak kanıtlandı):** Sorun sertifika, cipher veya bozuk
imaj değildi. Detached çalışan `s_server` kapalı stdin görüyordu. `strace`, TCP `accept()`
başarılı olduktan hemen sonra şu sırayı gösterdi: `read(0, "", 16384) = 0`, istemci soketine
`shutdown(..., SHUT_RD)`, ardından dinleme soketine `shutdown(..., SHUT_RDWR)`. Dolayısıyla
TLS byte'ı okunmadan bağlantı RST ile kapanıyor ve `SSL_accept()` sayacı 0 kalıyordu.

Jessie'nin OpenSSL 1.0.1t paketinde `-ign_eof` seçeneği yoktur. `docker exec -d -i` de CLI
ayrıldıktan sonra stdin'i kalıcı biçimde açık tutmadı. Kanıtlanmış çözüm, boş fakat kapanmayan
bir pipe kullanmaktır:

```sh
tail -f /dev/null | openssl s_server -accept 8443 \
  -cert /cert.pem -key /key.pem -debug -state
```

Temiz `debian:8` container'ında aynı sertifika ve anahtarla art arda iki yerel test başarıyla
tamamlandı. Her testte istemci dönüş kodu `0`, protokol `TLSv1`, cipher
`ECDHE-RSA-AES256-SHA` oldu. PID 1 olarak yukarıdaki pipe ile başlatılan ayrı test container'ında
da handshake `1468` byte okuyup `331` byte yazdı; sunucu bağlantıdan sonra ayakta ve 8443'te
dinlemede kaldı.

Mevcut production-adlı container'a dokunmadan önce onu geri alınabilir biçimde yeniden
adlandırıp, yalnız doğrulanmış temiz imajla yenisini başlatın:

```sh
docker stop goflex-legacy-ssl
docker rename goflex-legacy-ssl goflex-legacy-ssl-broken-backup
docker run --name goflex-legacy-ssl --network host --restart unless-stopped -d \
  goflex-legacy-ssl-clean:test \
  sh -c 'tail -f /dev/null | openssl s_server -accept 8443 -cert /cert.pem -key /key.pem -debug -state'
```

Bu tanıyı yapan ajan production geçiş komutlarını **çalıştırmadı**. Ancak final
kontrolü sırasında eşzamanlı başka bir işlem tarafından geçişin uygulanmış olduğu görüldü:
eski container `goflex-legacy-ssl-broken-backup` adıyla durdurulmuş hâlde saklanıyor;
yeni `goflex-legacy-ssl`, temiz imaj ve yukarıdaki stdin-pipe komutuyla çalışıyor.
Salt-okuma `docker logs` kontrolünde iki tamamlanmış handshake cipher'ı görüldü:
`ECDHE-RSA-AES256-GCM-SHA384` ve `DHE-RSA-AES256-SHA`. Bağımsız ilk kanıt ise
`legacy-ssl-test-runtime` test container'ında elde edildi.

## 6. `s_server -HTTP` ile `/cpestatus` yanıtı

2026-09-25'te `goflex-legacy-ssl-clean:test` imajındaki OpenSSL 1.0.1t ile
canlı olarak doğrulandı. Mevcut `goflex-legacy-ssl` container'ına dokunmadan,
yalnız localhost'ta `18443` portunu yayımlayan ayrı test container'ı:

```sh
docker run --name goflex-legacy-ssl-http-test \
  -p 127.0.0.1:18443:8443 \
  -e GOFLEX_SERIAL=X \
  -e GOFLEX_PASS=Y \
  -e GOFLEX_LAN=Z \
  -d goflex-legacy-ssl-clean:test \
  sh -c 'set -eu; mkdir -p /http-responses; cd /http-responses; body='"'"'<?xml version="1.0"?><response code="0" status="ok"/>'"'"'; printf '"'"'HTTP/1.1 200 OK\r\nContent-Type: application/xml\r\nContent-Length: %s\r\nConnection: close\r\n\r\n%s'"'"' "${#body}" "$body" > cpestatus; ln -s cpestatus "cpestatus?serial=REDACTED}&pass=REDACTED}&lan=${GOFLEX_LAN}"; tail -f /dev/null | openssl s_server -accept 8443 -cert /cert.pem -key /key.pem -debug -state -HTTP'
```

`/http-responses/cpestatus` dosyasının tam içeriği aşağıdadır. Header
satırlarının sonu ve boş header/body ayıracı gerçek dosyada CRLF'dir; body
sonunda newline yoktur:

```http
HTTP/1.1 200 OK
Content-Type: application/xml
Content-Length: 53
Connection: close

<?xml version="1.0"?><response code="0" status="ok"/>
```

### OpenSSL 1.0.1t query-string davranışı

Bu sürümde `-HTTP`, query string'i yoldan ayırmıyor. Örneğin cihazın
`/cpestatus?serial=REDACTED&pass=REDACTED&lan=Z` isteği için doğrudan
`cpestatus?serial=REDACTED&pass=REDACTED&lan=Z` adlı dosyayı açmaya çalışıyor; yalnız
`cpestatus` dosyasının bulunması yeterli değil. Yukarıdaki komut bu nedenle
query'li dosya adını canonical `cpestatus` dosyasına symlink ediyor. Gerçek
cihaz değerleri production container'ına environment değişkenleriyle verilmeli;
özellikle pass değeri bu repoya yazılmamalıdır.

### Container içinden canlı doğrulama

Kullanılan komut:

```sh
docker exec goflex-legacy-ssl-http-test sh -c \
  "printf 'GET /cpestatus?serial=REDACTED&pass=REDACTED&lan=Z HTTP/1.1\r\nHost: cpestatus.seagateshare.com\r\n\r\n' | timeout 8 openssl s_client -connect 127.0.0.1:8443 -quiet 2>&1"
```

Doğrulanan uygulama yanıtı:

```http
HTTP/1.1 200 OK
Content-Type: application/xml
Content-Length: 53
Connection: close

<?xml version="1.0"?><response code="0" status="ok"/>
```

İstemci exit code'u `0` oldu. Sertifika self-signed olduğu için `s_client`
önce beklenen `verify error:num=18:self signed certificate` uyarısını yazdı;
TLS bağlantısı ve HTTP yanıtı yine başarıyla tamamlandı.

### Production'a geçiş (yalnız komut; burada çalıştırılmadı)

Aşağıdaki değerleri shell'de gerçek cihaz değerleriyle doldurun. Komut mevcut
container'ı silmez; rollback için zaman damgalı bir adla saklar. Environment
değerleri `docker inspect` ile görülebileceğinden host erişimini buna göre
sınırlayın.

```sh
GOFLEX_SERIAL='<DEVICE_SERIAL>'
GOFLEX_PASS='<DEVICE_PASS>'
GOFLEX_LAN='<DEVICE_LAN_IP>'
GOFLEX_BACKUP="goflex-legacy-ssl-pre-http-$(date +%Y%m%d-%H%M%S)"

docker stop goflex-legacy-ssl
docker rename goflex-legacy-ssl "$GOFLEX_BACKUP"
docker run --name goflex-legacy-ssl \
  --network host \
  --restart unless-stopped \
  -e GOFLEX_SERIAL="$GOFLEX_SERIAL" \
  -e GOFLEX_PASS="$GOFLEX_PASS" \
  -e GOFLEX_LAN="$GOFLEX_LAN" \
  -d goflex-legacy-ssl-clean:test \
  sh -c 'set -eu; mkdir -p /http-responses; cd /http-responses; body='"'"'<?xml version="1.0"?><response code="0" status="ok"/>'"'"'; printf '"'"'HTTP/1.1 200 OK\r\nContent-Type: application/xml\r\nContent-Length: %s\r\nConnection: close\r\n\r\n%s'"'"' "${#body}" "$body" > cpestatus; ln -s cpestatus "cpestatus?serial=REDACTED}&pass=REDACTED}&lan=${GOFLEX_LAN}"; tail -f /dev/null | openssl s_server -accept 8443 -cert /cert.pem -key /key.pem -debug -state -HTTP'
```

Rollback gerekirse yeni container durdurulup farklı bir ada taşındıktan sonra
`"$GOFLEX_BACKUP"` tekrar `goflex-legacy-ssl` olarak adlandırılıp başlatılabilir.

## 7. Dinamik registration catcher test paketi (2026-09-25)

### Neden `s_server -HTTP` yeterli değil?

§6'daki statik dosya/symlink yaklaşımı bilinen `/cpestatus?...` isteğine doğru
HTTP framing ile cevap verebildi. Ancak OpenSSL 1.0.1t `-HTTP` modu query string'i
dosya adının parçası sayıyor ve yalnız önceden hazırlanmış GET yollarını sunuyor.
`reg.seagateshare.com` isteğinin path/query/body biçimi bilinmediği için olası her
dosya adını önceden üretmek mümkün değil; POST body'yi dinamik olarak kaydetmek de
bu modun görevi değil.

Bu nedenle `scripts/reg-catcher-test/` altında iki katmanlı, production'dan izole
bir test paketi hazırlandı:

1. Jessie/OpenSSL 1.0.1'e bağlı `stunnel4`, 8443'te TLS'i sonlandırıp şifresi
   çözülmüş HTTP akışını container içindeki `127.0.0.1:18080` adresine aktarır.
2. Python catcher GET/POST/PUT isteklerinin Host, path/query, header ve body
   biçimini JSON satırı olarak loglar; hassas alanları `<redacted>` yapar ve tüm
   geçerli isteklere genel XML `200 OK` yanıtı döndürür.

Bu ayrım eski TLS uyumluluğu ile HTTP/API gözlemini birbirinden bağımsız tutar.
Sertifika ve private key image'a alınmaz; runtime'da `/cert.pem` ve `/key.pem`
olarak salt-okunur mount edilir. Catcher'ın genel XML'i gerçek Seagate API şeması
olarak kabul edilmemelidir; yalnız ilk gözlem/probe yanıtıdır.

Dockerfile özellikle taze `debian:8` tabanını kullanır. Önceki
`goflex-legacy-ssl-clean:test` imajı oluşturulurken sertifika ve anahtar container'a
kopyalandıktan sonra `docker commit` yapılmıştı; o imajdan türemek bu dosyaları alt
image katmanında miras bırakabilirdi. Yeni test image'ı bu nedenle OpenSSL,
`stunnel4` ve Python'ı doğrudan Jessie arşivinden kurar; sertifika/anahtar yalnız
runtime mount olarak bulunur.

### Oluşturulan dosyalar

```text
scripts/reg-catcher-test/
  Dockerfile
  stunnel.conf
  catcher.py
  entrypoint.sh
  build-run-test.sh
  test_catcher.py
  README.md
```

`build-run-test.sh` yalnız `goflex-reg-catcher-test` adını kullanır ve portları
`127.0.0.1:18080`/`127.0.0.1:18443` üzerinde yayınlar. Aynı adlı test container'ı
varsa durur; otomatik `stop`, `rm`, `rename`, production container işlemi veya
host-network kullanmaz.

### Codex sandbox'ında doğrulananlar

Docker/socket erişimi olmayan Codex sandbox'ında şu kontroller çalıştırıldı:

```sh
python3 -m unittest discover -s scripts/reg-catcher-test -p 'test_*.py' -v
sh -n scripts/reg-catcher-test/entrypoint.sh
sh -n scripts/reg-catcher-test/build-run-test.sh
```

22 test geçti. Bunlar query/form/JSON/header redaksiyonu, binary ve bozuk body
güvenliği, doğru XML status/header/body framing'i, GET/POST/PUT, geçersiz/aşırı
`Content-Length`, mount kontrolleri, stunnel yönü ve test scriptinin mevcut
container'a zarar vermeden durmasını kapsıyor. Sandbox AF_INET ve bind işlemlerini
engellediği için HTTP handler ham in-memory HTTP akışıyla test edildi; gerçek port
bind'i bu kanıtın parçası değildir.

### Claude'un ayrı shell'de çalıştıracağı test

Repo kökünden tek komut:

```sh
sh scripts/reg-catcher-test/build-run-test.sh
```

Eşdeğer manuel build/run ve kanıt toplama komutları
`scripts/reg-catcher-test/README.md` içinde verilmiştir. Bu adımda özellikle
Jessie arşiv paketlerinin kurulması, `stunnel`ın sertifika ile başlaması, gerçek
TCP bind'leri, HTTP/HTTPS sentetik istekleri ve log redaksiyonu doğrulanmalıdır.

Bu paketi hazırlayan Codex oturumu Docker build/run yapmadı; mevcut
`goflex-legacy-ssl` container'ına, dnsmasq/iptables yapılandırmasına ve fiziksel
cihaza dokunmadı. Production geçişi ve Metehan'ın fiziksel reboot'u için ayrı
onay kapısı devam ediyor.

### İlk gerçek container denemesi: eksik Python stdlib

Claude'un ayrı shell'deki ilk `docker build` adımı başarıyla tamamlandı, fakat
container başlangıçta aşağıdaki hata ile durdu:

```text
ImportError: No module named 'json'
```

Kök neden Dockerfile'ın `python3-minimal` kurmasıydı. Jessie'de bu paket çıplak
yorumlayıcıyı sağlar; catcher'ın ilk import ettiği `json` dahil tam standart
kütüphane zincirini sağlamaz. Dockerfile `python3-minimal` yerine tam `python3`
meta-paketini kuracak şekilde düzeltildi. Statik runtime sözleşme testi artık hem
`openssl python3 stunnel4` paket dizisini zorunlu tutuyor hem de
`python3-minimal` kullanımını reddediyor.

Başarısız test container'ı Claude tarafından kaldırıldı. Production container,
host ağı ve cihaz bu denemeden etkilenmedi; aynı izole build/run scripti yeniden
çalıştırılabilir.

### İkinci gerçek container denemesi: tüm izole kontroller başarılı

`python3` paket düzeltmesinden sonra Claude ayrı shell'de
`build-run-test.sh` scriptini yeniden çalıştırdı ve şu sonuçları bildirdi:

- HTTP GET ve POST kontrolleri geçti.
- stunnel üzerinden HTTPS GET ve POST kontrolleri geçti.
- `goflex-reg-catcher-test` çalışır durumda kaldı; yalnız localhost'ta
  `127.0.0.1:18080 -> 8080` ve `127.0.0.1:18443 -> 8443` portları yayınlandı.
- Runtime OpenSSL sürümü `1.0.1t`, stunnel sürümü `5.06` oldu.
- stunnel `1.0.1k` ile derlenmiş, runtime'da `1.0.1t` kullanıyor uyarısı verdi;
  buna rağmen iki HTTPS isteği de tamamlandı. Aynı uyarı önceki çalışan production
  deneyinde de görülmüştü; bu aşamada bloklayıcı kabul edilmedi.
- Query, form ve JSON örneklerindeki tüm sentetik `pass`/`token`/`password`
  değerleri loglarda `<redacted>` olarak göründü; açık sentetik secret bulunmadı.

Bu sonuçlar dinamik catcher, normal TLS istemcisiyle stunnel yönlendirmesi, HTTP
framing ve redaksiyon zincirini gerçek container içinde doğrular. GoFlex cihazının
SSLv2 çerçeveli TLS 1.0 ClientHello'su ise henüz bu yeni stunnel container'ına
gelmedi; onun nihai kanıtı production geçişinden sonraki fiziksel boot olacaktır.

İzole `goflex-reg-catcher-test` container'ı kanıt toplandıktan sonra çalışır
durumda bırakıldı. Production host-network container'ı da iç catcher için
`127.0.0.1:18080` bağlayacağından, production geçişinden önce bu test container'ı
en azından durdurulmalı; silinmesi gerekmez.

### İlk production geçiş denemesi: host 8080 çakışması ve rollback bulgusu

Claude'un ayrı shell'de çalıştırdığı ilk production geçişi, yeni dinamik catcher
container'ının sağlık kontrolünde başarısız oldu. Container logundaki hata:

```text
OSError: [Errno 98] Address already in use
```

Kök neden Docker veya yeni entrypoint değildi. Host'ta önceki Faz 1 gözleminden
kalmış çıplak bir `python3 catcher.py` süreci 8080'i tutuyordu. Bu süreç kapatıldı
ve portun boşaldığı ayrıca doğrulandı. Bundan sonraki geçişlerde `docker run`
öncesi 8080, 8443 ve iç stunnel hedefi olan 18080'in dinleyen süreç/container
sahipliği açıkça kontrol edilmelidir.

Otomatik rollback eski production container'ını yeniden başlatınca ikinci ve
bağımsız bir legacy sorun görünür oldu. Eski Faz 1 başlangıç komutundaki
`ln -s cpestatus "cpestatus?..."` işlemi, önceki başlangıçtan kalan symlink ile
karşılaşıp `File exists` verdi; `set -eu` nedeniyle container restart-loop'a
girdi. Bu komutun restart-safe biçimi `ln -sf` oldu. Claude eski production'ı
aynı image/env ile, yalnız bu idempotency düzeltmesini kullanarak taze container
olarak yeniden oluşturdu. Ardından gerçek TLS handshake ve query'li
`/cpestatus` isteğinde `HTTP/1.1 200 OK` ile beklenen XML doğrulandı. Cihaz reboot
edilmedi ve etkilenmedi.

Dinamik catcher'ın `entrypoint.sh` dosyası aynı sınıfta bir kalıcı-state sorunu
taşımıyor: startup sırasında symlink veya response dosyası üretmiyor; yalnız
Python catcher ve stunnel süreçlerini başlatıyor. Container restart edildiğinde
önceki process namespace'i sonlandığından socket bind'leri de yeniden kuruluyor.
Bu nedenle entrypoint'e `ln -sf` benzeri bir işlem eklenmesine gerek yoktur.
Container adı çakışması da farklı bir katmandır: `docker run --name` mevcut ada
sessizce yazmaz, yeni container'ı oluşturmadan hata verir. Production geçiş
prosedürü eski container'ı önce zaman damgalı ada taşımalı ve rollback sırasında
geri getirilen container'ın gerçekten sağlıklı olduğunu ayrıca doğrulamalıdır.

Başarısız yeni catcher container'ı ve önceki backup container'ları inceleme için
silinmeden tutuldu. Production şu anda restart-safe legacy komutla sağlıklıdır;
ikinci geçişten önce izole test container'ı durdurulmalı ve host port preflight'ı
tekrarlanmalıdır.

### İkinci production geçişi: dinamik catcher aktif

Claude 2026-09-25'te ikinci geçişi ayrı shell erişimiyle tamamladı. Geçiş
scriptine ilk denemeden çıkan şu güvenlik kapıları eklendi ve canlı çalıştırmada
geçti:

- İzole `goflex-reg-catcher-test` container'ı silinmeden durduruldu.
- 8080 ve 18080'de beklenmeyen host dinleyicisi olmadığı doğrulandı.
- Rollback adayı legacy container'ın restart komutunda `ln -sf` bulunduğu
  doğrulandı.
- Eski production durdurulduktan sonra yeni container başlamadan önce 8080,
  8443 ve 18080 tekrar kontrol edildi.

Yeni production durumu Claude'un canlı shell raporuna göre şöyledir:

- Container adı: `goflex-legacy-ssl`
- Image: `goflex-reg-catcher:test`
- Ağ: host network
- Restart policy: `unless-stopped`
- Sertifika ve private key: salt-okunur runtime mount
- HTTP `:8080/health`: `200 OK` ve beklenen genel XML
- HTTPS `:8443/health`: `200 OK` ve beklenen genel XML
- stunnel: gerçek TLS negotiation tamamlandı (`TLSv1.2`,
  `ECDHE-RSA-AES256-GCM-SHA384`)
- Açık HTTP yönü: stunnel'dan `127.0.0.1:18080` catcher hedefine ulaştı

Rollback container'ı `goflex-legacy-ssl-pre-reg-20260925-212619` adıyla durmuş
hâlde saklanıyor. İlk başarısız geçişin
`goflex-legacy-ssl-failed-reg-20260925-211706` container'ı ve durmuş
`goflex-reg-catcher-test` test container'ı da inceleme/geri dönüş kanıtı olarak
silinmedi.

Bu Docker kanıtları Codex sandbox'ında bağımsız çalıştırılmadı; Claude'un canlı
host çıktısına dayanır. Production hâlâ Faz 1 gözlem modundadır: her geçerli HTTP
isteğine genel `<response code="0" status="ok"/>` döner ve request metadata/body
alanlarını redakte ederek loglar. Bu yanıtın gerçek registration şeması olduğu
henüz kabul edilmemelidir.

### Fiziksel boot gözlem protokolü

Dinamik catcher zinciri fiziksel cihaz boot'una hazırdır. Reboot'u yalnız Metehan
fiziksel olarak yapacaktır. Reboot'tan önce yeni bir terminalde log takibi
başlatılmalı ve ilk satırdaki zaman gözlem sınırı olarak saklanmalıdır:

```sh
OBS_START=$(date --iso-8601=seconds)
printf 'OBS_START=%s\n' "$OBS_START"
printf '%s\n' "$OBS_START" > /tmp/goflex-observation-start
docker logs --since "$OBS_START" --timestamps --follow goflex-legacy-ssl \
  2>&1 | tee "/tmp/goflex-boot-$(date +%Y%m%d-%H%M%S).log"
```

İkinci terminalde DNS olayları izlenebilir:

```sh
OBS_START=$(cat /tmp/goflex-observation-start)
sudo journalctl -u dnsmasq --since "$OBS_START" --follow --no-pager
```

`dnsmasq` query logging kapalıysa bu terminalin sessiz kalması tek başına DNS
arızası kanıtı değildir. İsteğe bağlı üçüncü terminalde payload yazdırmadan cihaz
bağlantı metadata'sı izlenebilir; `<DEVICE_IFACE>` mevcut MITM arayüzüyle
değiştirilmelidir:

```sh
sudo tcpdump -ni <DEVICE_IFACE> -tttt \
  'host 192.168.50.89 and (port 53 or port 80 or port 443)'
```

Log takipleri aktif olduktan sonra Metehan cihazı bir kez fiziksel olarak reboot
eder. İlk istekten sonra en az iki dakika sessizlik görülene kadar, toplamda en
fazla yaklaşık on dakika gözlem yapılmalıdır. Bu sırada yerel wizard Retry
butonuna basılmamalı ve production container değiştirilmemelidir; boot daemon'ının
tek başına ürettiği zincir korunmalıdır.

Gözlem raporunda şunlar bulunmalıdır:

1. Host/domain sırası ve her isteğin timestamp, method ve redakte edilmiş path'i.
2. Query veya body şeması; `pass`, `token`, `password`, cookie ve authorization
   değerleri yalnız `<redacted>` olarak paylaşılmalıdır.
3. Her isteğin ardından gelen sonraki domain/istek; özellikle
   `cpestatus -> reg -> axentraserver -> update` ilerlemesi veya durduğu nokta.
4. stunnel handshake protokol/cipher bilgisi ve varsa TLS/HTTP hataları.
5. Gözlem sonunda container'ın çalışır durumu ve restart sayacı.

Reboot sonrasında hiç catcher kaydı oluşmazsa yeniden reboot veya Retry denenmeden
önce DNS logu, NAT sayaçları, port dinleyicileri ve container logları birlikte
toplanmalıdır.
