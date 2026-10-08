# Legacy TLS registration catcher — izole test

Bu dizin, GoFlex Home'un eski TLS istemcisini Debian Jessie/OpenSSL 1.0.1 tabanlı
`stunnel` ile kabul edip şifresi çözülmüş HTTP isteklerini dinamik Python
catcher'a aktarır. Catcher GET/POST/PUT isteklerini redakte edilmiş JSON satırları
olarak container loguna yazar ve başlangıç gözlemi için her geçerli isteğe şu
genel yanıtı verir:

```xml
<?xml version="1.0"?><response code="0" status="ok"/>
```

Bu XML'in gerçek Seagate/Axentra API şeması olduğu iddia edilmez. Amaç bir sonraki
cihaz boot'unda gerçek Host, method, path, query ve body biçimini gözlemlemektir.

## Güvenlik sınırı

- Script yalnız `goflex-reg-catcher-test` adlı test container'ını oluşturur.
- Portlar yalnız `127.0.0.1:18080` ve `127.0.0.1:18443` üzerinde yayınlanır.
- `--network host`, restart policy veya production container adı kullanılmaz.
- Aynı adlı test container'ı zaten varsa script durur; onu silmez/değiştirmez.
- `cert.pem` ve `key.pem` image'a kopyalanmaz, salt-okunur mount edilir.
- Gerçek cihaz seri/token değerleri gerekmez ve komutlara yazılmaz.
- Bu test production geçişi veya cihaz reboot'u yapmaz.

## Önkoşullar

Repo kökünde yerel ve Git tarafından ignore edilen şu dosyalar bulunmalıdır:

```text
cert.pem
key.pem
```

Ayrıca Docker, `curl` ve `debian:8` image'ını çekebilmek için ağ erişimi (veya
image'ın yerel cache'de bulunması) gereklidir.

## Önerilen tek komut

Repo kökünden:

```sh
sh scripts/reg-catcher-test/build-run-test.sh
```

Script image'ı build eder, izole container'ı başlatır, HTTP/HTTPS üzerinden
sentetik GET+POST istekleri yollar, XML yanıtını ve container canlılığını kontrol
eder. Sentetik secret değerlerinin loga açık yazılmadığını ve `<redacted>`
işaretinin bulunduğunu da doğrular.

Başarılı çalıştırma sonunda dört `OK:` istek satırı ve son doğrulama özeti
görülmelidir. Script hata verirse test container'ını otomatik temizlemez; mevcut
durum inceleme için korunur.

## Eşdeğer manuel build/run komutları

Repo kökünden:

```sh
docker build -t goflex-reg-catcher:test scripts/reg-catcher-test

docker run --name goflex-reg-catcher-test \
  -p 127.0.0.1:18080:8080 \
  -p 127.0.0.1:18443:8443 \
  -v "$PWD/cert.pem:/cert.pem:ro" \
  -v "$PWD/key.pem:/key.pem:ro" \
  -d goflex-reg-catcher:test
```

Manuel sentetik kontroller:

```sh
curl --fail --silent --show-error \
  'http://127.0.0.1:18080/cpestatus?serial=TEST-SERIAL&pass=QUERY_TEST_SECRET'

curl --fail --silent --show-error \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'serialnum=TEST-SERIAL&token=BODY_TEST_SECRET&subdomain=test-device' \
  'http://127.0.0.1:18080/register'

curl --fail --silent --show-error --insecure \
  'https://127.0.0.1:18443/register?token=TLS_QUERY_TEST_SECRET'

curl --fail --silent --show-error --insecure \
  -H 'Content-Type: application/json' \
  --data '{"serialnum":"TEST-SERIAL","password":"TLS_BODY_TEST_SECRET"}' \
  'https://127.0.0.1:18443/device'
```

Her komut yalnız yukarıdaki genel XML satırını döndürmelidir.

## Claude'un toplaması gereken kanıt

```sh
docker ps --filter name='^/goflex-reg-catcher-test$'
docker logs goflex-reg-catcher-test
docker exec goflex-reg-catcher-test openssl version -a
docker exec goflex-reg-catcher-test stunnel4 -version
```

Log paylaşılmadan önce gözle kontrol edilmelidir. Sentetik `*_TEST_SECRET`
değerleri görünmemeli; ilgili query/body/header alanları `<redacted>` olmalıdır.
Claude aşağıdakileri geri bildirmelidir:

1. `docker build` dönüş kodu ve varsa son hata bloğu.
2. Scriptin dört HTTP/HTTPS kontrol sonucu.
3. Container'ın hâlâ çalışıp çalışmadığı.
4. Redakte edilmiş catcher logundan Host/method/path/body biçimi.
5. OpenSSL ve stunnel sürüm çıktısı.

Bu kanıtlar gelmeden production container değişimi önerilmez. Gerçek cihaz testi
ayrıca onaylandıktan sonra fiziksel reboot'u Metehan yapar.
