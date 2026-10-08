FROM debian:8

RUN printf '%s\n' \
      'deb [trusted=yes] http://archive.debian.org/debian jessie main' \
      'deb [trusted=yes] http://archive.debian.org/debian-security jessie/updates main' \
      > /etc/apt/sources.list \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -o Acquire::Check-Valid-Until=false \
      -o Acquire::AllowInsecureRepositories=true update \
    && apt-get -o Acquire::Check-Valid-Until=false \
      -o Acquire::AllowInsecureRepositories=true \
      install -y --allow-unauthenticated --no-install-recommends \
      openssl python3 stunnel4 \
    && rm -rf /var/lib/apt/lists/*

COPY catcher.py /opt/goflex/catcher.py
COPY stunnel.conf /etc/stunnel/stunnel.conf
COPY entrypoint.sh /opt/goflex/entrypoint.sh

RUN chmod 0755 /opt/goflex/catcher.py /opt/goflex/entrypoint.sh

EXPOSE 8080 8443

ENTRYPOINT ["/opt/goflex/entrypoint.sh"]
