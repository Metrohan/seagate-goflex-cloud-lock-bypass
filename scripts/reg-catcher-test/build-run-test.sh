#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
IMAGE_NAME="goflex-reg-catcher:test"
CONTAINER_NAME="goflex-reg-catcher-test"
EXPECTED_XML='<?xml version="1.0"?><response code="0" status="ok"/>'

if ! [ -r "$REPO_ROOT/cert.pem" ]; then
    echo "HATA: sertifika bulunamadi: $REPO_ROOT/cert.pem" >&2
    exit 1
fi

if ! [ -r "$REPO_ROOT/key.pem" ]; then
    echo "HATA: private key bulunamadi: $REPO_ROOT/key.pem" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "HATA: docker komutu PATH icinde bulunamadi" >&2
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "HATA: curl komutu PATH icinde bulunamadi" >&2
    exit 1
fi

if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    echo "HATA: $CONTAINER_NAME zaten var; otomatik silme veya uzerine yazma yapilmadi" >&2
    exit 1
fi

docker build -t "$IMAGE_NAME" "$SCRIPT_DIR"

docker run --name "$CONTAINER_NAME" \
    -p 127.0.0.1:18080:8080 \
    -p 127.0.0.1:18443:8443 \
    -v "$REPO_ROOT/cert.pem:/cert.pem:ro" \
    -v "$REPO_ROOT/key.pem:/key.pem:ro" \
    -d "$IMAGE_NAME"

attempt=0
while :; do
    if readiness_body=$(curl --silent --show-error --fail --max-time 2 \
        "http://127.0.0.1:18080/health" 2>/dev/null) \
        && [ "$readiness_body" = "$EXPECTED_XML" ]; then
        break
    fi
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 20 ]; then
        echo "HATA: catcher 20 saniye icinde hazir olmadi" >&2
        echo "Inceleme: docker logs $CONTAINER_NAME" >&2
        exit 1
    fi
    sleep 1
done

assert_response() {
    label=$1
    shift
    if ! response_body=$(curl --silent --show-error --fail --max-time 5 "$@"); then
        echo "HATA: $label istegi basarisiz" >&2
        exit 1
    fi
    if [ "$response_body" != "$EXPECTED_XML" ]; then
        echo "HATA: $label beklenmeyen body dondurdu: $response_body" >&2
        exit 1
    fi
    echo "OK: $label"
}

assert_response "HTTP GET" \
    "http://127.0.0.1:18080/cpestatus?serial=TEST-SERIAL&pass=QUERY_TEST_SECRET"
assert_response "HTTP POST" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data "serialnum=TEST-SERIAL&token=BODY_TEST_SECRET&subdomain=test-device" \
    "http://127.0.0.1:18080/register"
assert_response "HTTPS GET" \
    --insecure \
    "https://127.0.0.1:18443/register?token=TLS_QUERY_TEST_SECRET"
assert_response "HTTPS POST" \
    --insecure \
    -H "Content-Type: application/json" \
    --data '{"serialnum":"TEST-SERIAL","password":"TLS_BODY_TEST_SECRET"}' \
    "https://127.0.0.1:18443/device"

running=$(docker container inspect --format '{{.State.Running}}' "$CONTAINER_NAME")
if [ "$running" != "true" ]; then
    echo "HATA: test container'i isteklerden sonra calismiyor" >&2
    exit 1
fi

container_logs=$(docker logs "$CONTAINER_NAME" 2>&1)
for secret in QUERY_TEST_SECRET BODY_TEST_SECRET \
    TLS_QUERY_TEST_SECRET TLS_BODY_TEST_SECRET; do
    if printf '%s' "$container_logs" | grep -F "$secret" >/dev/null; then
        echo "HATA: sentetik secret container logunda acik gorundu: $secret" >&2
        exit 1
    fi
done
if ! printf '%s' "$container_logs" | grep -F '<redacted>' >/dev/null; then
    echo "HATA: loglarda redaksiyon kaniti bulunamadi" >&2
    exit 1
fi

echo "OK: sentetik HTTP/HTTPS istekleri, redaksiyon ve container canliligi dogrulandi"
echo "Loglari incele: docker logs $CONTAINER_NAME"
echo "OpenSSL: docker exec $CONTAINER_NAME openssl version -a"
echo "stunnel: docker exec $CONTAINER_NAME stunnel4 -version"
