# Seagate GoFlex Home Recovery — Field Notes

Bu depo, Seagate'in bulut servisini (seagateshare.com) 2018/2019'da kapatması nedeniyle
"kilitli" kalmış bir Seagate GoFlex Home NAS cihazını kurtarma sürecinin notlarıdır.
Cihaz, sahibi tarafından şifresi hatırlanmayan ve Seagate desteğinin
sonlandırılmış olduğu bir durumda elimize ulaştı. Tüm işlemler cihazın gerçek
sahibinin izniyle, kendi donanımımız üzerinde, izole bir noktadan-noktaya
Ethernet bağlantısıyla yapıldı.

**Son durum (2026-10-02):** Cihaz üzerinde salt okunur yönetim arayüzü yetenek incelemesi
**NO-GO** ile durduruldu. Eski HTTPS yığını güncel istemcilerle uyumlu değil; bağımsız
kimlik doğrulama, yeniden başlatma sonrası uygulama depolaması ve web sürecine verilebilecek
dar yetkili işlem yolu kanıtlanmadı. Cihaza bu incelemede dosya, hesap, paylaşım, servis veya
ayar yazılmadı. Karar, bakımı yapılan TLS özellikli bir sunucu sağlanana kadar standart SMB
kullanımına devam etmek. Ayrıntı ve kanıt: [2026-10-02 yetenek kapısı](docs/superpowers/evidence/2026-10-02-goflex-ui-capability-gate.md).

Daha önce cihaz yeniden flaşlanarak FTP/SMB dosya erişimi geri kazanıldı. Eski bulut kaydını
taklit etme ve yönetim arayüzü çalışmaları tamamlanmış özellikler değildir. Cihazın bugünkü
canlı durumu bu depodaki kayıtlarla doğrulanmış sayılmaz.

---

## 1. Başlangıç durumu

- Cihaz: Seagate GoFlex Home (board: `EHDUL4 7D28UL44001R1 REV.01`), Marvell Kirkwood
  (ARM926EJ-S) SoC, Axentra HipServ OS üzerinde çalışıyor.
- Sorun: Web arayüzü girişte `seagateshare.com`'a yönlendiriyor, bu servis artık yok.
  Kurulum sihirbazı "cannot reach seagateshare.com" hatasıyla takılı kalıyor.
- Admin şifresi bilinmiyor, SSH/web erişimi yok.
- Hedef: Önce dosyalara erişim, sonra mümkünse cihazı genel amaçlı bir Linux
  sunucusuna (lab server) çevirmek.

## 2. İlk teşhis

`nmap`/`curl`/`smbclient`/`ftp` ile port taraması: HTTP(80/443), SSH(22), FTP(21),
SMB(139/445) açık. SSH banner: `OpenSSH_4.3-HipServ`. HTTP `X-Axentra-Version: 10.2.0`
başlığı ve `Location: https://www.seagateshare.com/?hipname=...` yönlendirmesi
cihazı ve sorunu doğruladı.

## 3. Reflash — üç deneme, bir kritik eksik adım

Topluluk tarafından belgelenmiş bir USB kurtarma mekanizması var: cihaz kapalıyken
reset pinine basılı tutup güç verilince, bootloader FAT32 bir USB bellekten
firmware arıyor.

Kullanılan dosya: `hipserv2_seagateplug_2.72_admin.zip` — **üçüncü parti**, orijinal
kaynağı [goflexhome.blogspot.com yazısı](http://goflexhome.blogspot.com/2019/01/firmware-reflash-without-seagateshare.html).
Yazarın notuna göre bu, orijinal Seagate stok firmware'inin küçük bir değişiklikle
(varsayılan bir `admin` hesabı önceden oluşturulmuş) yeniden paketlenmiş hali —
Seagateshare'e ihtiyaç duymadan ilk kurulumu atlamak için. **Bu depo bu dosyayı
içermez** — lisansı/sahipliği belirsiz olduğu için yeniden dağıtmıyoruz, sadece
kaynağını gösteriyoruz.

Dosya bütünlüğü indirmeden sonra doğrulandı: `file` ile her bileşenin
(`initrd`, `uImage`, `.ubi`) gerçek/geçerli u-boot/UBI formatında olduğu ve
CRC'lerinin bozulmadığı teyit edildi.

**İlk 3 reflash denemesi başarısız oldu** — cihaz sonsuz bir "açılış aşamasında"
LED durumunda kaldı, ağa hiç çıkmadı. Sebebi ancak
[BeyondLogic wiki'sindeki gerçek bir boot log'unu](https://web.archive.org/web/2020id_/https://wiki.beyondlogic.org/index.php/Seagate_FreeAgent_GoFlex_Home_Firmare_Recovery)
okuyunca anlaşıldı:

> "The hard disk should be removed from the dock, otherwise the hard disk may
> come up as /dev/sda rather than the USB stick and prevent the \*.ubi file
> being found."

Kurtarma ortamı `/dev/sda1`'i USB bellek sanıp bağlıyor — eğer dahili disk takılıysa
o `/dev/sda` olarak öne geçiyor ve gerçek USB bellek hiç bulunamıyor, `.ubi` dosyası
flaşlanmıyor. **Bu adımı atlamak 3 denemenin de sessizce hiçbir şey yapmamasına
neden olmuştu.**

**Düzeltilmiş prosedür:**
1. Cihazı kapat, dahili SATA diski dock'tan çıkar.
2. Hazırlanan USB belleği tak, reset pini + power ile kurtarma moduna gir.
3. ~3-5 dakika bekle (iki aşamalı süreç: önce u-boot `uImage`+`initrd`'yi NAND'a
   yazıyor, sonra o kernel içindeki kurtarma ortamı asıl `.ubi` dosya sistemini
   flaşlıyor).
4. Diski geri tak, normal aç.

Bu düzeltmeyle **4. deneme başarılı oldu**: sabit yeşil LED (= "ağ bağlantısı
normal", resmi [Seagate LED tablosu](https://www.seagate.com/support/kb/goflex-home-led-functionality-3205en/)),
`admin`/`admin1` ile FTP ve SMB erişimi doğrulandı.

## 4. Reflash sonrası doğrulanmış durum (önceki gözlem)

- ✅ Önceki gözlemde cihaz ağda erişilebilir ve stabil durumdaydı; bu kayıt güncel canlılık kontrolü değildir.
- ✅ `admin` / `admin1` ile FTP ve SMB üzerinden dosya erişimi çalışıyor.
- ✅ Dahili disk mount olmuş, tüm orijinal paylaşımlar (Personal/Backup/Public/
  External) SMB üzerinden listeleniyor.
- ⚠️ SMB'de görünür paylaşımların çoğu (Personal, Backup/TimeMachineBackup) **boş**
  görünüyor — ama `smbclient ... du` ile disk kullanımı kontrol edildiğinde diskte
  **~1.46 TB kullanılmış alan** olduğu görüldü. Yani eski kullanıcı verileri
  muhtemelen diskte duruyor, sadece reflash'ın oluşturduğu yeni `admin` hesabının
  klasör görünümüne bağlı değil (eski hesap veritabanı sıfırlanmış olabilir).
  Bu veriye erişmek için muhtemelen root/shell erişimi (bkz. §6) gerekiyor.
- ❌ SSH parola ile çalışmıyor: `admin` kullanıcısı için SSH tamamen reddediliyor,
  `root` için `password` auth yöntemi sunuluyor ama denenen aday şifrelerin
  (`root`, `admin1`, `toor`, `stxadmin`, boş, vb.) hiçbiri çalışmadı.

## 5. Web arayüzü / Flash bypass girişimi

Web arayüzü eski (2010-2012) bir Adobe Flash istemcisi kullanıyor — modern
tarayıcılarda Flash Player yok (2021'de kaldırıldı).

**Bulgu 1 — Flash'sız düz HTML giriş yolu:** `http://<ip>/?local=1` isteği,
buluta değil `/homebase/signin` gibi düz HTML sayfalarına yönlendiriyor. Bu ipucu
[openstora GitHub projesinden](https://github.com/Dees7/openstora) (ilişkili bir
Axentra HipServ cihazı olan Netgear Stora için belgelenmiş) geldi.

**Bulgu 2 — Kurulum sihirbazını atlatma:** Sihirbaz "Registration: cannot reach
seagateshare.com" adımında (sayfa 2/6) takılı kalıyor. Formdaki gizli
`wizardpageno` alanını doğrudan manipüle ederek (`wizardpageno=3` göndererek)
kayıt adımı tamamen atlanıp sonraki sayfaya (4/6, Software Update) geçilebiliyor.
Sihirbazın geri kalanı (5/6 bildirim ayarları, 6/6 "Congratulations!") normal
şekilde ilerletilebildi — **ama** "Finish" butonu aslında sadece sihirbaza geri
dönüyor ("Return to Setup"), kalıcı bir "kurulum tamamlandı" bayrağı set etmiyor;
bu bayrak yalnızca gerçek bir bulut kaydıyla set ediliyor gibi görünüyor.

**Bulgu 3 — Gizli REST API:** Flash istemcisinin (`MainStage.swf`, sıkıştırılmış
Flash dosyası, `zlib` ile açılıp `strings` ile incelendi) arkasında düz bir
`/api/2.0/rest/...` XML REST API'si var (`accounts/users`, `server/config` vb.).
Oturum çerezi ile doğrudan `curl` üzerinden GET/PUT çağrılabiliyor — ama şifre
değiştirme gibi yazma işlemleri için doğru XML alan adlarını (SWF string'lerinde
`<user email="" oldpass="" password=""/>` şablonu bulundu) bulmamıza rağmen
sunucu tutarlı şekilde `code 5 Invalid Parameter` / `code 4 I/O Error` döndürdü —
tam olarak çözülemedi.

## 6. "Sahte bulut sunucusu" (MITM) girişimi — kısmi başarı

Fikir: cihazın `seagateshare.com`'a erişim denemesini yakalayıp kendi sahte
sunucumuzla yanıtlamak, böylece kayıt adımının gerçekten "başarılı" görünmesini
sağlamak.

### 6.1 Altyapı

- Ana makinede statik IP (`192.168.50.1/24`), `NetworkManager` bu arayüzden çekildi.
- `dnsmasq`: hem DHCP sunucusu (cihaza gateway+DNS olarak kendimizi veriyor) hem
  DNS sunucusu (`*.seagateshare.com` → kendi IP'miz) olarak kullanıldı.
- `iptables` PREROUTING NAT: sadece cihazın arayüzünden (belirli bir interface)
  gelen 80/443 trafiğini yerel bir yakalayıcı porta yönlendiriyor. **Not:**
  Docker'ın kendi `DOCKER` NAT zinciri PREROUTING'in başında olduğu için,
  kurallarımızı `-I ... 1` ile zincirin en başına eklemek gerekti, yoksa Docker
  paketleri önce yakalıyordu.

### 6.2 Cihaz gerçekten bize geliyor

DHCP ile cihaza IP verildikten sonra `dnsmasq` loglarında cihazın aktif olarak
şu adresleri sorguladığı görüldü: `cpestatus.seagateshare.com`,
`reg.seagateshare.com`, `axentraserver.<hipname>.seagateshare.com`,
`update.seagateshare.com`. `iptables` sayaçları cihazın gerçekten TCP/443
bağlantı denemesi yaptığını doğruladı.

### 6.3 Engel: cihaz SSLv2-uyumlu bir TLS ClientHello gönderiyor

Python'un `ssl` modülüyle (modern OpenSSL 3.6.4) kurulan bir yakalayıcıya gelen
bağlantı `fatal alert: protocol_version` ile reddedildi. `tcpdump -X` ile ham
byte'lar incelendiğinde istemcinin `80 7c 01 03 01 ...` ile başlayan, klasik
**SSLv2 kayıt çerçevesi** kullandığı görüldü (içeriği TLS 1.0 istiyor — bu,
dönemin TLS istemcilerinde yaygın bir geriye-uyumluluk pratiğiydi). SSLv2
desteği güvenlik nedeniyle OpenSSL 1.1.0'dan (2016) itibaren tamamen kaldırıldı,
bu yüzden modern hiçbir sistem bunu konuşamıyor.

### 6.4 Çözüm: izole, eski bir OpenSSL container'ı

Ana sistemi hiç değiştirmeden, Docker ile eski bir Debian 8 (Jessie, EOL) imajı
içinde `OpenSSL 1.0.1t` kurulup kendi self-signed sertifikamızla `openssl
s_server` çalıştırıldı (`--network host`, apt kaynakları `archive.debian.org`'a
yönlendirildi çünkü Jessie ana mirror'lardan kaldırılmış).

**Bu çalıştı:** `s_server`, SSLv2-uyumlu ClientHello'yu doğru ayrıştırıp normal
bir TLS 1.0 ServerHello + sertifika zinciri gönderdi, cihaz da tam el sıkışmayı
tamamladı (ChangeCipherSpec + Finished), ardından **176 byte'lık şifreli bir HTTP
isteği gönderdi** ve sunucumuzun (varsayılan `-www` modu) yanıtını aldı (4506 byte).

**Tam olarak tamamlanamayan kısım:** Cihazın gönderdiği HTTP isteğinin gerçek
(şifresi çözülmüş) içeriğini yakalayıp, ona Axentra'nın gerçek kayıt API'sinin
beklediği yanıtı üretecek şekilde cevap vermeyi denedik. Bunun için `s_server`'ı
"düz mod"da (istekleri ekrana basan) tekrar başlattık, ama bu eski binary/Docker
kombinasyonu kararsız çıktı — dış bağlantı olmadan da kendi kendine sürekli
başlayıp kapanıyordu (sebebi netleştirilemedi: muhtemelen container içindeki çok
eski, statik bağlı OpenSSL binary'sinin container ortamında entropy/kaynak
sorunu). Zaman/emek dengesini gözeterek bu noktada durduk.

**Sonuç:** TLS/protokol uyumluluğu sorunu **kesin olarak çözüldü ve kanıtlandı**.
Gerçek Axentra kayıt API'sini tam olarak taklit etmek (böylece kurulum
sihirbazının "registered" bayrağını kalıcı olarak set etmesini sağlamak) ayrı,
daha büyük bir reverse-engineering çalışması gerektiriyor ve tamamlanmadı.

## 7. Kaynaklar ve provenance

Bu çalışma sırasında danışılan/kullanılan üçüncü parti kaynaklar:

| Kaynak | Ne için kullanıldı |
|---|---|
| [Seagate: GoFlex Home LED functionality](https://www.seagate.com/support/kb/goflex-home-led-functionality-3205en/) | Resmi LED renk kodları |
| [Seagate: Discontinuation of Remote Access](https://www.seagate.com/support/kb/what-to-know-about-goflex-home-and-the-discontinuation-of-remote-access-007867en/) | Factory reset'in neden tehlikeli olduğu |
| [goflexhome.blogspot.com — Firmware reflash without Seagateshare](http://goflexhome.blogspot.com/2019/01/firmware-reflash-without-seagateshare.html) | Kullanılan reflash paketinin kaynağı (üçüncü parti, dağıtılmıyor) |
| [BeyondLogic wiki (Wayback arşivi)](https://web.archive.org/web/2020id_/https://wiki.beyondlogic.org/index.php/Seagate_FreeAgent_GoFlex_Home_Firmare_Recovery) | Kritik "diski çıkar" bulgusu, gerçek boot log |
| [Doozan forum](https://forum.doozan.com/) | Reflash/kurtarma yöntemleri, u-boot kaynakları |
| [ArchLinuxARM forumu](https://archlinuxarm.org/forum/) | Root erişimi, header pinout tartışmaları |
| [judepereira.com — UART serial console](https://judepereira.com/blog/hacking-your-goflex-home-2-uart-serial-console/) | UART pin haritası (kullanılmadı, referans) |
| [wiki.scottn.us](http://wiki.scottn.us/doku.php?id=goflex:start) | Seri konsol + Debian kurulum notları (Public Domain), kullanılmadı |
| [CyanLabs — Recovering a Seagate GoFlex via serial](https://cyanlabs.net/tutorials/recovering-a-seagate-goflex-via-serial/) | Kasa açma + UART referansı, kullanılmadı |
| [GitHub: Dees7/openstora](https://github.com/Dees7/openstora) | `?local=1` bypass ipucu |
| [Ruffle (ruffle-rs/ruffle)](https://ruffle.rs/) | Flash emülatörü denemesi (Apache-2.0/MIT), tarayıcı erişim sorunuyla tamamlanamadı |

**Üçüncü parti firmware dosyası (`hipserv2_seagateplug_2.72_admin.zip`) bu depoya
dahil edilmemiştir** — kaynağı yukarıda belirtilen blog yazısı, lisansı/sahipliği
belirsiz (muhtemelen Seagate'in orijinal, telif hakkı korumalı firmware'inin
değiştirilmiş bir kopyası). İsteyen, kaynak bağlantısından kendisi temin
edebilir.

Bu depodaki kod (Python yakalayıcı, dnsmasq config) tarafımızca bu görev için
yazılmıştır.

## 8. İçindekiler

```
scripts/
  catcher.py           — HTTP/HTTPS istek yakalayıcı (Python, MITM aşaması için)
  dnsmasq_goflex.conf  — DHCP+DNS yapılandırması (örnek, IP'ler bu kuruluma özel)
```

## 9. Sorumluluk reddi

Bu notlar, **kendi sahip olduğumuz/yetkili olduğumuz bir cihaz** üzerinde,
izole bir laboratuvar ağında yapılan meşru bir veri kurtarma/yeniden kullanım
çalışmasını belgeler. Burada anlatılan teknikler (özellikle §6) başka birinin
cihazına veya ağına izinsiz erişim için kullanılmamalıdır.
