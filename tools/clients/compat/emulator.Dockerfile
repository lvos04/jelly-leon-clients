# syntax=docker/dockerfile:1.7.1@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
# Jelly Leon clients — runner voor de Android-emulator in de compatibiliteitstests (P4-0, JC3; ADR-0011).
#
# ALLEEN voor ontwikkeling en CI: géén installatiemethode en géén image om te publiceren of op de NAS te draaien.
# Bevat uitsluitend de gedeelde bibliotheken die de emulator (uit ~/android-sdk, alleen-lezen gekoppeld) nodig heeft;
# de SDK, de systeemimages en de APK's komen er bij het draaien als koppeling in. Start altijd met
# `--device /dev/kvm --memory 4g --memory-swap 4g --cap-drop ALL --security-opt no-new-privileges` (compat/emulator.py).
#
#   docker buildx build --load -f tools/clients/compat/emulator.Dockerfile \
#     -t jelly-leon-clients/emulator-runner:dev tools/clients/compat
#
# Geen proxy en geen eigen CA nodig. De BuildKit-secret `ca_bundle` is optioneel en blijft hier leeg; als hij ooit gezet
# wordt, komt hij nooit in een laag terecht.

ARG DEBIAN_IMAGE=docker.io/library/debian:trixie-20261104-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
FROM ${DEBIAN_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive

RUN --mount=type=secret,id=ca_bundle,required=false \
    set -eu; \
    if [ -s /run/secrets/ca_bundle ]; then \
      install -m 0644 /run/secrets/ca_bundle /tmp/ca_bundle.crt; \
      echo 'Acquire::https::CAInfo "/tmp/ca_bundle.crt";' > /etc/apt/apt.conf.d/99-emulator; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      libx11-6 libpulse0 libnss3 libpng16-16t64 libexpat1 libdrm2 libxcb1 libxi6 libxext6 libdbus-1-3 libxkbfile1 \
      libgl1 libegl1 libxcomposite1 libxcursor1 libxdamage1 libxtst6 libxrender1 libxrandr2 libfontconfig1 \
      libfreetype6 libxkbcommon0 libasound2t64 procps; \
    rm -rf /var/lib/apt/lists/* /tmp/ca_bundle.crt /etc/apt/apt.conf.d/99-emulator

RUN useradd --uid 568 --create-home --shell /usr/sbin/nologin emulator
USER 568:568
WORKDIR /tmp
