# GoFlex Legacy TLS Registration Catcher Test Design

## Amaç

GoFlex Home cihazının boot sırasında yaptığı eski TLS bağlantılarını kabul eden,
şifresi çözülmüş HTTP isteklerini güvenli biçimde gözlemleyen ve başlangıçta tüm
geçerli isteklere genel bir XML başarı yanıtı dönen, production'dan tamamen ayrı
bir test servisi hazırlamak.

Bu aşamanın başarı ölçütü gerçek kayıt şemasını tahmin etmek değildir. Amaç,
`reg.seagateshare.com`, `axentraserver.<hipname>.seagateshare.com` ve
`update.seagateshare.com` isteklerinin gerçek Host, method, path, query ve body
biçimini bir sonraki fiziksel boot sırasında görebilecek bir gözlem noktası
oluşturmaktır.

## Sınırlar

### Kapsamda

- `scripts/reg-catcher-test/` altında yeniden üretilebilir test bileşenleri.
- Taze `debian:8` tabanından eski OpenSSL/stunnel paketlerini kuran test Dockerfile'ı.
- Eski OpenSSL'e bağlı `stunnel` ile legacy TLS sonlandırma.
- Düz HTTP'yi işleyen dinamik Python catcher.
- GET, POST ve PUT gözlemi; XML `200 OK` yanıtı.
- Hassas query/body/header alanlarının loglarda redaksiyonu.
- Yalnız localhost'a yayınlanan test container komutları.
- Sentetik HTTP/HTTPS doğrulama scripti ve çalıştırma talimatları.
- Deney, gerekçe, sınırlamalar ve sonuçların `scripts/mitm-setup-notes.md`
  içinde Türkçe belgelenmesi.
- Üretilen loglar ile yerel sertifika/anahtar dosyalarının Git dışında tutulması.

### Kapsam dışında

- Mevcut `goflex-legacy-ssl` container'ını durdurmak, yeniden adlandırmak veya
  değiştirmek.
- Host ağ ayarlarını, dnsmasq veya iptables kurallarını değiştirmek.
- Cihazdan fiziksel reboot istemek veya tetiklemek.
- Gerçek Seagate/Axentra yanıt şemasını kanıtsız biçimde kalıcılaştırmak.
- Commit veya push yapmak.

## Mimari

Test container'ı iki süreç çalıştırır:

1. Jessie paketindeki, OpenSSL 1.0.1 ile bağlı `stunnel`, container'ın 8443
   portunda TLS kabul eder ve şifresi çözülmüş akışı `127.0.0.1:18080` adresine
   iletir. Bu sınır, modern Python SSL katmanının SSLv2 çerçeveli TLS 1.0
   ClientHello'yu reddetmesini önler.
2. Python catcher, TLS arkasında `127.0.0.1:18080` ve düz HTTP testi için
   `0.0.0.0:8080` üzerinde dinler. Her istek için yapılandırılmış bir gözlem
   kaydı üretir ve genel XML yanıtını doğru `Content-Length` ve
   `Connection: close` başlıklarıyla döndürür.

Sertifika ve private key image içine kopyalanmaz. Çalıştırma sırasında salt-okunur
volume olarak `/cert.pem` ve `/key.pem` yollarına bağlanır.

## İstek ve Log Davranışı

Catcher aşağıdaki verileri kaydeder:

- Zaman damgası ve istemci adresi
- HTTP methodu
- Host
- Path ve query parametreleri
- Header'lar
- Desteklenen gövde uzunluğu ve redakte edilmiş gövde

`pass`, `password`, `token`, `authorization`, `cookie` ve benzeri kimlik bilgisi
alanları case-insensitive olarak `<redacted>` değerine çevrilir. Form-urlencoded
ve JSON gövdeleri yapısal olarak redakte edilir; tanınmayan metin gövdelerinde
bilinen hassas anahtar atamaları maskelemeden geçirilir. Ham binary gövde loga
yazılmaz; uzunluk ve sınırlı bir gösterim kaydedilir. İstek gövdesi için üst
sınır uygulanır; aşırı büyük veya geçersiz `Content-Length` kontrollü hata üretir.

İlk gözlem modunda tüm geçerli Host/path kombinasyonları şu genel yanıtı alır:

```xml
<?xml version="1.0"?><response code="0" status="ok"/>
```

Bu yanıtın gerçek API şeması olduğu iddia edilmez. Host bazlı veya endpoint bazlı
şemalar ancak cihazdan alınan somut istek/tepki kanıtından sonra ayrı bir değişiklik
olarak eklenecektir.

## Repo Dosyaları

- `scripts/reg-catcher-test/Dockerfile`
- `scripts/reg-catcher-test/stunnel.conf`
- `scripts/reg-catcher-test/catcher.py`
- `scripts/reg-catcher-test/entrypoint.sh`
- `scripts/reg-catcher-test/build-run-test.sh`
- `scripts/reg-catcher-test/README.md`
- Gerekirse standart kütüphane ile çalışan catcher unit testleri
- `.gitignore` ekleri
- `scripts/mitm-setup-notes.md` deney ve kullanım bölümü

## İzole Çalıştırma

`build-run-test.sh` yalnız şu test kaynaklarını kullanır:

- image: `goflex-reg-catcher:test`
- container: `goflex-reg-catcher-test`
- HTTP: `127.0.0.1:18080 -> container:8080`
- HTTPS: `127.0.0.1:18443 -> container:8443`

Script mevcut aynı adlı container'ı otomatik silmez veya üzerine yazmaz. Çakışma
varsa durup operatöre açık hata verir. `goflex-legacy-ssl` adına veya host-network
moduna hiçbir komut içermez.

## Doğrulama

Claude ayrı shell'de aşağıdaki katmanları çalıştırır:

1. Image build ve container başlangıç kontrolü.
2. HTTP üzerinden sentetik GET ve form-urlencoded POST.
3. HTTPS üzerinden aynı istekler; HTTP status, content type, content length ve XML
   body kontrolü.
4. Hassas test değerinin `docker logs` içinde bulunmadığı ve `<redacted>`
   işaretinin bulunduğu kontrol.
5. Art arda bağlantılardan sonra container'ın ayakta kaldığı kontrol.
6. Container içindeki OpenSSL sürümü ve `stunnel` bağlantı logu.

Modern bir test istemcisinin TLS başarısı cihaz uyumluluğunu tek başına kanıtlamaz.
SSLv2 çerçeveli gerçek ClientHello için nihai kanıt yalnız cihazın sonraki fiziksel
boot gözlemidir. Bu boot, production geçişi ayrıca Claude tarafından onaylandıktan
sonra Metehan tarafından yapılır.

## Production Geçiş Kapısı ve Rollback

İzole testler tamamlandığında Codex yalnız şu kanıtları özetler: oluşturulan
artifact'lar, exact test komutları, sonuçlar, kalan belirsizlikler ve önerilen
production komutu. Mevcut `goflex-legacy-ssl` için stop/rename/run uygulanmaz.

Claude production geçişini ayrıca onaylarsa mevcut container zaman damgalı bir
backup adına taşınır ve yeni servis aynı host portlarında başlatılır. Rollback,
yeni container'ı durdurup farklı ada taşıdıktan sonra backup container'ı eski
adıyla yeniden başlatmaktır. Hiçbir adım container silmeyi gerektirmez.

## Bilinen Riskler

- Jessie arşivlerinden OpenSSL, `stunnel4` ve Python paketlerinin kurulabilirliği build
  zamanında doğrulanmalıdır.
- `stunnel` OpenSSL 1.0.1 kullanacak olsa da SSLv2 çerçeveli ClientHello uyumluluğu
  ancak gerçek cihaz boot'u ile kesinleşir.
- Genel başarı XML'i gerçek kayıt state machine'inin beklediği alanları içermeyebilir.
- İstek body formatı XML, form veya özel binary olabilir; catcher bilinmeyen/binary
  içeriği güvenli biçimde gözlemlemeli, ayrıştırma başarısızlığında çökmemelidir.
- Container logları hassas operasyonel veri sayılır; Git'e eklenmez ve paylaşılmadan
  önce ayrıca gözden geçirilir.
