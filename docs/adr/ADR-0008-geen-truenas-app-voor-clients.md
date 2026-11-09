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

## Toetsing per contractparagraaf (contracts 1.1, review P0-afronding 2026-11-09)

Deze repo levert geen dienst, dus de dienst-eisen zijn **N.v.t.**; wat wél geldt, is gecontroleerd en waar mogelijk
met een test vastgezet.

| § | Eis | Stand in deze repo | Bewaakt door |
|---|---|---|---|
| 1 | Installatie alleen als standaard Custom App, nooit YAML/compose | N.v.t.: geen app op de NAS; nergens een installatie via YAML, compose of `install.sh` | dit ADR, README "Installeren op apparaten" |
| 1 | Geen `latest`, base-images op digest | bouwcontainer: Dockerfile-frontend `docker/dockerfile:1.7.1@sha256:…` en `ubuntu:24.04@sha256:…`; acties op commit-SHA; dev-hulpmiddelen op exacte versie | `tests/test_bouwverificatie.py`, `tests/test_workflows.py` |
| 1 | Geen shell/root voor AI, geen `sudo`, geen Docker-socket | geen AI-functies; compile in de container zonder netwerk, zonder capabilities, niet-root, bron alleen-lezen, zonder Docker-socket; `sudo` alleen in de CI-runner voor `apt-get` (GitHub-runner, niet in een container) | `tests/test_bouwverificatie.py` |
| 2 | Eén alles-in-één image, één poort, `/appdata`, 568 | N.v.t. (geen dienst); de bouwcontainer draait als 568 (of de eigen uid) | dit ADR |
| 3 | Geen geheimen in formulier/Git/logs; `/appdata/secrets` | geen formulier; geen geheimen in de repo of workflows (geen `secrets.*`, checkout zonder opgeslagen token); signing-sleutels pas bij een besluit over ondertekening (ADR-0004) | `tests/test_workflows.py` |
| 4 | Auth/enrollment/rollen, 401 bij ongeldige auth | N.v.t.: geen API; de apps loggen in bij de Jellyfin-server zoals upstream | — |
| 5 | Foutformaat, `Idempotency-Key`, `/healthz`, `/readyz`, OpenAPI-export | N.v.t.: geen HTTP-API; de clients gebruiken de API van `jelly-leon` | — |
| 6 | Connectorcontract | N.v.t.: de Hub kent geen connector voor apparaat-apps; ontbrekend is ontbrekend (geen nep-endpoints) | — |
| 7 | Event-envelope/outbox | N.v.t.: geen events | — |
| 8 | Risicobeleid en executor | N.v.t. voor de apps; de upstream-sync doet nooit merge/release/publicatie (R2 blijft een mens) | `tests/test_workflows.py`, `tests/test_upstream_sync.py` |
| 9 | Manifest | N.v.t.: geen catalogusapp | dit ADR |
| 10 | Repo-indeling, CI, CHANGELOG, geen licentie zonder vraag | eigen indeling voor een fork (ADR-0001), CI per client, CHANGELOG, geen eigen licentie (ADR-0007) | ADR-0001, ADR-0006 |
| 11 | EVIDENCE.json, nooit `Gereed`/`Geslaagd` | bijgehouden; statussen alleen `Bezig`/`Geblokkeerd` | `tests/test_evidence.py` (velden, statuslijsten, validatiewaarden, bestaande commits) |
| 12 | Branch, geen PR/force-push, NL-commits | gevolgd (afsluitregel volgens de lopende sessie, zie contract 1.2 A2) | — |
