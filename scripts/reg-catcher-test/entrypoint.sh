#!/bin/sh
set -eu

if ! [ -r /cert.pem ]; then
    echo "HATA: salt-okunur sertifika mount'u bulunamadi: /cert.pem" >&2
    exit 1
fi

if ! [ -r /key.pem ]; then
    echo "HATA: salt-okunur private-key mount'u bulunamadi: /key.pem" >&2
    exit 1
fi

catcher_pid=""
stunnel_pid=""

cleanup() {
    trap - EXIT INT TERM
    if [ -n "$stunnel_pid" ]; then
        kill "$stunnel_pid" 2>/dev/null || true
    fi
    if [ -n "$catcher_pid" ]; then
        kill "$catcher_pid" 2>/dev/null || true
    fi
    if [ -n "$stunnel_pid" ]; then
        wait "$stunnel_pid" 2>/dev/null || true
    fi
    if [ -n "$catcher_pid" ]; then
        wait "$catcher_pid" 2>/dev/null || true
    fi
}

trap cleanup EXIT
trap 'exit 143' INT TERM

python3 /opt/goflex/catcher.py &
catcher_pid=$!

stunnel4 /etc/stunnel/stunnel.conf &
stunnel_pid=$!

while kill -0 "$catcher_pid" 2>/dev/null \
    && kill -0 "$stunnel_pid" 2>/dev/null; do
    sleep 1
done

if ! kill -0 "$catcher_pid" 2>/dev/null; then
    wait "$catcher_pid" || catcher_status=$?
    echo "HATA: catcher beklenmedik bicimde durdu (status=${catcher_status:-0})" >&2
else
    wait "$stunnel_pid" || stunnel_status=$?
    echo "HATA: stunnel beklenmedik bicimde durdu (status=${stunnel_status:-0})" >&2
fi

exit 1
