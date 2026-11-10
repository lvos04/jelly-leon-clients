# ADR-0009 — Swiftfin 1.6.1 blijft; de server gaat vóór P4 naar Jellyfin 12.x

- **Status:** Aanvaard — **besluit van de gebruiker 2026-11-09** (STATUS.md, besluit 2). De serverupgrade is een
  **aparte fase vóór P4** in `jelly-leon` en `jelly-leon-web`; in deze repo en in deze ronde wordt niets geüpgraded.
  **Herbeoordeeld op 2026-11-10 (P4-0, JC3)** tegen de Jelly Leon-server 12.4.0-jl.0: zie het slot van dit document.
- **Context (gemeten in de broncode, P0):** Swiftfin 1.6.1 pint `jellyfin-sdk-swift` **3.0.0** (`Package.resolved`),
  gegenereerd tegen **Jellyfin API 12.0.0** (`Sources/Extensions/Info.swift`). Swiftfin noemt een server met
  major.minor lager dan de SDK-versie niet compatibel (`isVersionCompatible`) en toont dan
  *"Update to Jellyfin 12.0 for the best experience."* De Jelly Leon-server is nu **Jellyfin 10.11.11**. De
  Android-clients gebruiken jellyfin-sdk-kotlin **1.7.1** (API 10.10.7, minimum 10.10.0) en passen bij 10.11.11.

## Besluit

1. **Swiftfin blijft op 1.6.1** (optie A uit P0); geen downgrade naar 1.5, geen patch.
2. **De server (`jelly-leon` + `jelly-leon-web`) gaat vóór P4 naar de nieuwste stabiele Jellyfin 12.x (.NET 10)**,
   zodat B03 direct op 12.x gebouwd wordt. Die upgrade is een eigen fase met eigen gates; niet in deze ronde.
3. **De Android-clients worden in die fase op 12.x-compatibiliteit gecontroleerd** (recept hieronder). Tot dan
   verandert er aan android/androidtv/desktop niets.
4. Tot de serverupgrade blijft in de compatibiliteitsmatrix Swiftfin ↔ 10.11.11 op *"waarschuwing; functionele
   compatibiliteit onbekend — NIET GEVALIDEERD (Mac/Xcode)"* staan, nooit op compatibel.

## Gemeten stand 2026-11-09 (alleen gelezen: `git ls-remote`, ondiepe clones)

| Gegeven | Waarde |
|---|---|
| Nieuwste stabiele Jellyfin-server | `v12.4` (`83d0d0e7f76e…`); daarvoor `v12.3`, `v12.2`, `v12.1`, `v12.0`. Bij de upgradefase opnieuw meten. |
| jellyfin-sdk-kotlin 1.7.1 (android 2.7.3, androidtv 0.19.10) | API **10.10.7**, `minimumVersion` 10.10.0 → de versiecheck van de SDK laat een 12.x-server door |
| jellyfin-sdk-kotlin 1.8.12 | API 10.11.11, minimum 10.11.0 — gebruikt door upstream `jellyfin-android` master (`afebde6`) en `jellyfin-androidtv` master (`aa24978`) / `v0.20.0-beta.4` |
| jellyfin-sdk-kotlin 1.9.4 (nieuwste) | API **12.4.0**, minimum **12.0.0** — nog door geen upstream-Android-client gebruikt |
| Swiftfin 1.6.1 | SDK 3.0.0 / API 12.0.0 → past bij 12.x (verwacht; NIET GEVALIDEERD (Mac/Xcode)) |

**Voorlopige statische routevergelijking** (`tools/clients/server_api_compat.py`,
`test-evidence/p0-server-12x-routevergelijking.json`): server v10.11.11 heeft 424 routes, v12.4 419; 6 routes zijn
weg (`GET /Environment/NetworkShares`, `GET /Items/{}/CriticReviews`, `GET /LiveTv/Recordings/Groups/{}`,
`GET /QuickConnect/Initiate` (de `POST` blijft), `POST /System/MediaEncoder/Path`, `POST /Users/{}/EasyPassword`). Van
de 408 endpoints in SDK 1.7.1 ontbreken er 5 in 12.4 (2 daarvan al in 10.11.11). **Geen** daarvan wordt in de bronnen
van android of androidtv aangeroepen.

Grenzen (daarom geen compatibiliteitsclaim): alleen routeniveau; gewijzigde parameters, DTO-velden, enums,
authenticatie en gedrag worden niet gezien, evenmin zelf samengestelde URL's. De android-app is grotendeels de
**web-client van de server** in een WebView met een native brug (`android/app/src/main/assets/native/`); die brug moet
met `jelly-leon-web` 12.x samenwerken — dat zegt deze vergelijking niet. Let op: de OpenAPI-specificatie van SDK 1.9.4
mist routes die in de 12.4-servercode nog bestaan (bv. `DELETE /Videos/ActiveEncodings`); vergelijk daarom met de
servercode, niet met de SDK-specificatie.

## Controle in de upgradefase (vóór P4)

1. `server_api_compat.py` opnieuw met de exact gekozen 12.x-tag (commando in de testbewijzen); elke gebruikte
   ontbrekende route → bevinding met client, bestand en SDK-functie (exitcode 1).
2. android- en androidtv-CI ongewijzigd groen (assemble + unit-tests).
3. Stock-client-smoketest van `jelly-leon` tegen de 12.x-build (serverkant, Sim).
4. Debug-APK's op een emulator tegen een 12.x-testserver: inloggen, bladeren, afspelen, ondertitel, hervatten
   (Sim-getest); android ook met de `jelly-leon-web`-12.x-web-client.
5. Echte apparaten uit D15 → tot dan **NIET GEVALIDEERD (hardware)**; Swiftfin op iPhone/Apple TV → **NIET
   GEVALIDEERD (Mac/Xcode)**.
6. Brengt upstream een Android-release op SDK 1.9.x uit, dan via `upstream_sync.py` overnemen (eigen syncbranch,
   menselijke review, ADR-0002).

## Gevolgen

- Swiftfin-waarschuwing tegen de huidige 10.11.11-server blijft bestaan tot de upgradefase; daarna naar verwachting
  weg (te bevestigen op een Mac/apparaat).
- Risico verschuift naar de Android-clients (SDK 1.7.1 tegen API 12.x): bewust geaccepteerd, met de controle hierboven
  als gate vóór P4.
- `INVENTARIS.md` §3 krijgt een kolom voor de verwachting met 12.x; alles blijft NIET GEVALIDEERD tot echte tests.

## Herbeoordeling 2026-11-10 (P4-0, JC3) — tegen de Jelly Leon-server 12.4.0-jl.0

De server staat nu op Jellyfin 12.4 (`jelly-leon` 12.4.0-jl.0, commit `e294f84`; web `jelly-leon-web` `5ced8a246`).
Uitgevoerd volgens het recept hierboven (ADR-0011 van deze repo; bewijs in `docs/platform-v2/test-evidence/p4-0-jc3-*`):

| Recept | Uitkomst | Validatie |
|---|---|---|
| 1. `server_api_compat.py` met de gekozen 12.x-tag | Kotlin (SDK 1.7.1): 5 van 408 SDK-endpoints ontbreken in 12.4, **geen** ervan gebruikt door android (24 SDK-functies) of androidtv (76). Swift (SDK 3.0.0, API 12.0): **alle 364** endpoints bestaan; Swiftfin gebruikt er 85. Nieuw: Swift-modus (`--sdk-taal swift`) en de CI-workflow *Clients / Compat 12.x (statisch)* | statisch |
| 2. android- en androidtv-CI | ongewijzigd groen (geen codewijziging in de clients) | CI |
| 3. Stock-client-smoketest van jelly-leon tegen 12.x | gedaan in jelly-leon P4-0 (25/25, compat-API 5/5) | Sim-getest (jelly-leon) |
| 4. APK's op een emulator tegen de 12.x-server | release-builds van de fork-apps (eigen applicationId, naast de officiële app) op telefoon- en twee Android TV-emulators: inloggen, bladeren met de gezaaide kijkgeschiedenis, hervatten op 300 s, Direct Play, transcode, ondertitels (voorkeur en extern); stock 12.4 als controlegroep; tablet-emulator niet stabiel (Sim-mislukt) | Sim-getest — zie `BOUWVERIFICATIE_P4-0.md` |
| 5. Echte apparaten (D15), Swiftfin op iPhone/Apple TV | niet mogelijk | **NIET GEVALIDEERD (hardware)**; **NIET GEVALIDEERD (Mac/Xcode)** |
| 6. Upstream-Android-release op SDK 1.9.x | nog niet uitgebracht (upstream-sync meldt "actueel") | — |

**Swiftfin 1.6.1 tegen 12.x (herbeoordeeld, de app zelf NIET GEVALIDEERD (Mac/Xcode)):**

- De versiecontrole `isVersionCompatible` (major.minor van de server ≥ 12.0) slaagt voor 12.4: de melding *"Update to
  Jellyfin 12.0 for the best experience."* verdwijnt naar verwachting (code gelezen; niet op een apparaat gezien).
- Serverkant van het protocol nagebootst met de exacte vormen uit de bron (`client_compat.py swiftfin`), tegen de
  Jelly Leon-image én stock 12.4 — beide gelijk, 0 regressies: aanmelden met de **ongequote** `MediaBrowser`-kop van
  jellyfin-sdk-swift 3.0.0 werkt; de websocket (`/socket?api_key=…` mét `Authorization`-kop) geeft 101 (alleen
  `api_key` → 403); de statische stream zonder token 200; de `TranscodingUrl` van de server bevat `ApiKey` (niet
  `api_key`) en geeft 200.
- **Bevinding (bron + meting):** Swiftfin opent een serverlog in de beheerweergave met `?api_key=<token>`
  (`Swiftfin/Extensions/LogFile.swift`, `queryAPIKey: true`). In 12.x telt `api_key` niet meer
  (`EnableLegacyAuthorization` uit, BG-01): 401 — op stock 12.4 precies zo. Alleen die beheerfunctie; kijken en afspelen
  gebruiken de kop. Geen patch in Swiftfin (ADR-0019 jelly-leon: geen patches in Swiftfin in v1); melden bij upstream
  is een vervolgpunt.
- Conclusie: geen reden om van besluit 1 (Swiftfin 1.6.1 blijft) af te wijken. In de matrix: **"past bij 12.x
  (statisch en protocol gemeten); NIET GEVALIDEERD (Mac/Xcode)"**, nooit "compatibel".
