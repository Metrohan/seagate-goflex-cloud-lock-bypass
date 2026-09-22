#!/usr/bin/env python3
"""GoFlex Home'un (ya da benzer bir Axentra HipServ cihazının) seagateshare.com'a
atmaya çalıştığı istekleri yakalayıp loglayan basit bir HTTP + HTTPS sunucusu.
Sadece gözlem amaçlı - her isteğe 200 OK dönüyor.

Kullanım notu: cihazlar genelde çok eski TLS istemcileri (SSLv2-uyumlu ClientHello)
kullanıyor. Modern OpenSSL (1.1.0+) bunu konuşamıyor - bkz. README §6.3. Bu script
gerçek bir el sıkışma denemesi için değil, temel HTTP/DNS/DHCP zincirini doğrulamak
için kullanıldı.

Ortam değişkenleri:
  BIND_IP    - dinlenecek IP (varsayılan: 0.0.0.0)
  HTTP_PORT  - varsayılan 8080
  HTTPS_PORT - varsayılan 8443
  CERTFILE   - self-signed sertifika+key birleşik PEM dosyası
  LOGFILE    - istek loglarının yazılacağı dosya
"""
import http.server
import ssl
import threading
import datetime
import os

BIND_IP = os.environ.get("BIND_IP", "0.0.0.0")
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8080"))
HTTPS_PORT = int(os.environ.get("HTTPS_PORT", "8443"))
CERTFILE = os.environ.get("CERTFILE", "selfsigned.pem")
LOGFILE = os.environ.get("LOGFILE", "requests.log")


def log(msg):
    line = f"[{datetime.datetime.now().isoformat()}] {msg}"
    print(line, flush=True)
    with open(LOGFILE, "a") as f:
        f.write(line + "\n")


class Handler(http.server.BaseHTTPRequestHandler):
    def _handle(self):
        body = b""
        length = int(self.headers.get("Content-Length", 0))
        if length:
            body = self.rfile.read(length)
        log(f"{self.command} {self.path} from {self.client_address}")
        log(f"  Headers: {dict(self.headers)}")
        if body:
            log(f"  Body: {body[:2000]!r}")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle

    def log_message(self, format, *args):
        pass  # kendi log() fonksiyonumuzu kullanıyoruz


def run_http():
    srv = http.server.HTTPServer((BIND_IP, HTTP_PORT), Handler)
    log(f"HTTP yakalayıcı {BIND_IP}:{HTTP_PORT} üzerinde dinliyor")
    srv.serve_forever()


def run_https():
    srv = http.server.HTTPServer((BIND_IP, HTTPS_PORT), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=CERTFILE)
    # Not: bu ayar eski TLS 1.0/1.1 istemcilerine biraz tolerans tanır, ama
    # SSLv2-uyumlu ClientHello'yu ANLAMAZ - onun için README §6.4'teki eski
    # OpenSSL (container içinde) yöntemi gerekiyor.
    ctx.set_ciphers("ALL:@SECLEVEL=0")
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    log(f"HTTPS yakalayıcı {BIND_IP}:{HTTPS_PORT} üzerinde dinliyor")
    srv.serve_forever()


if __name__ == "__main__":
    open(LOGFILE, "w").close()
    t1 = threading.Thread(target=run_http, daemon=True)
    t1.start()
    try:
        run_https()
    except Exception as e:
        log(f"HTTPS başlatılamadı: {e} - sadece HTTP ile devam ediliyor")
        t1.join()
