# syntax=docker/dockerfile:1.7.1@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
# Jelly Leon clients — bouwomgeving voor de desktop-client (desktop/, jellyfin-desktop v2.0.0).
#
# ALLEEN voor lokale bouwverificatie en CI-reproductie. Dit is géén installatiemethode en géén image om te
# publiceren of op de NAS te draaien: de desktop-client is een programma voor Windows/macOS/Linux-pc's.
#
# Bevat alleen de build-afhankelijkheden uit desktop/debian/control (zoals upstream .github/workflows/test.yml),
# op Ubuntu 24.04 — dezelfde distributie als de GitHub-runner ubuntu-24.04. De broncode wordt bij het draaien
# read-only gekoppeld (zie desktop_bouw.sh), zodat de compile zonder netwerk en met CPU-limiet draait.
#
#   docker buildx build --load \
#     -f tools/clients/bouwverificatie/desktop.Dockerfile -t jelly-leon-clients/desktop-bouw:dev desktop/
#   (of: make desktop-image)
#
# Geen proxy en geen eigen CA nodig. De BuildKit-secret `ca_bundle` in de RUN-stap is optioneel en blijft hier leeg;
# als hij ooit gezet wordt, komt hij nooit in een laag terecht.

ARG UBUNTU_IMAGE=docker.io/library/ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852
FROM ${UBUNTU_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive

COPY debian/control /tmp/deps/debian/control

RUN --mount=type=secret,id=ca_bundle,required=false \
    set -eu; \
    if [ -s /run/secrets/ca_bundle ]; then \
      # apt downloadt als gebruiker _apt: tijdelijke leesbare kopie, verdwijnt aan het eind van deze stap.
      install -m 0644 /run/secrets/ca_bundle /tmp/ca_bundle.crt; \
      sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources; \
      echo 'Acquire::https::CAInfo "/tmp/ca_bundle.crt";' > /etc/apt/apt.conf.d/99-bouwverificatie; \
      if [ -n "${HTTPS_PROXY:-}" ]; then \
        echo "Acquire::https::Proxy \"${HTTPS_PROXY}\";" >> /etc/apt/apt.conf.d/99-bouwverificatie; \
      fi; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates devscripts equivs ninja-build; \
    cd /tmp/deps; \
    mk-build-deps --install --remove \
      --tool 'apt-get -y --no-install-recommends -o Debug::pkgProblemResolver=yes' debian/control; \
    rm -rf /tmp/deps /tmp/ca_bundle.crt /var/lib/apt/lists/* /etc/apt/apt.conf.d/99-bouwverificatie; \
    sed -i 's|https://|http://|g' /etc/apt/sources.list.d/ubuntu.sources

# Geen root nodig voor de build zelf.
RUN useradd --uid 568 --create-home --shell /usr/sbin/nologin bouwer
USER 568:568
WORKDIR /home/bouwer
