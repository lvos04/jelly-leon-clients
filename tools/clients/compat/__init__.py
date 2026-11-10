"""Compatibiliteitsharnas van de clients met de Jelly Leon 12.x-server (P4-0, JC3; ADR-0011).

Alleen voor ontwikkeling en CI, nooit op de NAS en nooit een installatiemethode. Onderdelen:

- ``jfapi``     — kleine Jellyfin-API-client (alleen stdlib) voor inrichten, kijkgegevens zaaien en sessies volgen;
- ``server``    — wegwerpserver (jelly-leon-image of stock 12.x op digest) met het mediacorpus alleen-lezen;
- ``emulator``  — Android-/Android TV-emulator in een container met ``--device /dev/kvm`` (één tegelijk, gradle.lock);
- ``scenario``  — pure beoordelingsregels (afspelen, hervatten, ondertitels, segmenten, eindstatus), unit-getest;
- ``android``   — de UI- en afstandsbedieningsstappen per app (telefoon/tablet en tv);
- ``desktop``   — jellyfin-desktop 2.0.0 onder Xvfb in een container, bestuurd via ruwe CDP (``desktop_cdp.mjs``);
- ``bewijs``    — het bewijsdocument (zonder tokens of wachtwoorden).

Eerlijkheid: alles hier is **Sim-getest** (emulator/container op de ontwikkelmachine). Echte apparaten blijven
NIET GEVALIDEERD (hardware); Swiftfin NIET GEVALIDEERD (Mac/Xcode).
"""
