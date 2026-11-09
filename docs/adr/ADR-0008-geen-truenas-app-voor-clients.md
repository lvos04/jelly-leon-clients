# ADR-0008 — Geen alles-in-één image, Custom App, OpenAPI of manifest voor de clients

- **Status:** Aanvaard (P0, 2026-11-09) — afwijking van de generieke kwaliteitseisen, gemeld als contractpunt
- **Context:** De opdracht vraagt "per onderdeel" o.a. OpenAPI-export, een alles-in-één image,
  `deploy/truenas/CUSTOM_APP.md`, een manifest met gepinde images en `.env.example` (contract §2, §9, §10). Die eisen
  gaan over **diensten op de NAS**. Deze repo bevat uitsluitend **apparaat-apps** (Android-APK, Android TV-APK,
  iOS/tvOS-app, desktopprogramma); die draaien niet op TrueNAS en bieden geen HTTP-API.

## Besluit (veiligste interpretatie)

- **Geen** container-image, Custom App, TrueNAS-manifest of `.env.example` voor de clients: een image zou niets zinnigs
  doen en een Custom App-formulier zou de gebruiker misleiden. Er is ook geen installatie via YAML of compose.
- **Geen OpenAPI** van deze repo: de clients consumeren de Jellyfin-API van `jelly-leon` (die exporteert
  `docs/openapi/jelly-leon.openapi.json`); ze leveren zelf geen API.
- De container in `tools/clients/bouwverificatie/` is **alleen** een bouwomgeving voor ontwikkeling/CI (base image op
  digest, geen publicatie), geen installatiemethode.
- Wat wél geldt: CI per client, tests, ADR's, patchregister, EVIDENCE.json, gepinde toolchains/acties, eerlijke
  validatieniveaus.

## Open punt voor het platform

- **Distributie naar apparaten** (APK's, IPA via TestFlight/ad-hoc, desktop-installers) is nog niet ontworpen. Opties
  voor later, door de gebruiker te kiezen: (a) APK's als release-artefact in deze repo, (b) een downloadpagina of
  F-Droid-achtige repository geleverd door `jelly-leon`/de Hub, (c) alleen sideloaden. Elke optie vraagt eerst het
  besluit over app-identiteit en ondertekening (ADR-0004).
