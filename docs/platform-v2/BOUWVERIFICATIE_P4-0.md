# Bouwverificatie P4-0 — clients tegen de Jelly Leon 12.x-server (JC3, 2026-11-10)

Omgeving: de eigen Ubuntu 26.04-machine van de gebruiker (22 CPU's, 14,5 GiB RAM, KVM), gedeeld met andere agents;
zware stappen onder de gedeelde locks (`docker-build.lock`, `gradle.lock`, `stack.lock`). Geen macOS/Xcode, geen echt
Android-apparaat, geen tv, geen NAS. Alles hieronder is echt uitgevoerd; wat niet kon, staat als blokkade.
Validatie: **Sim-getest** (emulator/container op de ontwikkelmachine); echte apparaten **NIET GEVALIDEERD (hardware)**;
Swiftfin **NIET GEVALIDEERD (Mac/Xcode)**. Besluiten: ADR-0011 (harnas en meetregels), ADR-0009 (Swiftfin, herbeoordeeld).

## 1. Wat getest is

| Onderdeel | Versie / herkomst |
|---|---|
| Server | **jelly-leon-image 12.4.0-jl.0**, lokaal gebouwd met `deploy/allinone/Dockerfile` van jelly-leon uit `git archive` van jelly-leon `e294f84ea` en jelly-leon-web `5ced8a246` (alleen gelezen); image-ID `sha256:4671a48ade85…2d76a9b`, 2,85 GB; labels `version 12.4.0-jl.0`, `revision e294f84…`, `web.revision 5ced8a2…`. Gebouwd in 2 min 25 s onder `docker-build.lock` met een begrensde builder (7 GiB, 8 CPU's), daarna verwijderd. De image van de jelly-leon-CI wordt niet gepubliceerd. |
| Controlegroep | stock `docker.io/jellyfin/jellyfin:12.4@sha256:fea863d0…1771` (dezelfde upstream-digest als de forkbasis) |
| android | fork 2.7.3-jl.1, `assembleLibreRelease -Pjellyfin.version=2.7.3-jl.1` (R8, BUILD SUCCESSFUL in 1 min 45 s, onder `gradle.lock`); ongetekend sha256 `07b9e65f…742511a`; ondertekend met een wegwerp-testsleutel per run; `aapt2`: `org.jellyfin.mobile.jellyleon`, versionCode 2070301 |
| androidtv | fork 0.19.10-jl.1, `assembleRelease -Pjellyfin.version=0.19.10-jl.1` (BUILD SUCCESSFUL in 1 min 13 s); ongetekend sha256 `f3b6bf39…a083334c`; `org.jellyfin.androidtv.jellyleon`, versionCode 191001 |
| Officiële apps ernaast | jellyfin-android 2.7.3 libre-release (sha256 `f9f4b3ab…`), jellyfin-androidtv 0.19.10 release (sha256 `8510a517…`) |
| desktop | 2.0.0-jl.0 uit `desktop/`, Release-build met `make desktop-bouw` (`JOBS=4 BUILD_TYPE=Release`): 62/62 stappen, `ctest` 1/1; gestart in het nieuwe doel `test` van `bouwverificatie/desktop.Dockerfile` |
| Swiftfin | 1.6.1 met jellyfin-sdk-swift 3.0.0 (`37a2f50`, API 12.0.0) — alleen de serverkant van het protocol en statisch |
| Testbibliotheek | uit `.lokaal/media-corpus` (sha256 per bestand in het bewijs), alleen vrij gelicentieerd, per bestand alleen-lezen: hero.mp4 (H.264/AAC), Tears of Steel (H.264/MP3, 734 s) met `TOS-nl.srt` en `TOS-en.srt` ernaast, sintel-60s-referentie.mkv (H.264/AC3 + ingebedde NL-srt), sintel-30s-mpeg4-mp3.avi, sintel-30s-mpeg2-ac3.ts en de B03 Testserie (5 afleveringen) |
| Kijkgeschiedenis (gezaaid) | kijker `jc3kijker`: hervatpunt 300 s in Tears of Steel, hero 2× gezien (met datum), een favoriet — zoals na een overname (HARDE EIS) |

## 2. Emulators (bewijs `test-evidence/p4-0-jc3-android-emulator.json` + schermafdrukken)

Commando (onder `stack.lock` en `gradle.lock`, één emulator tegelijk, container met `--device /dev/kvm`, 4 GiB =
swaplimiet, `--cap-drop ALL`, `no-new-privileges`, SDK alleen-lezen, headless):

```
python3 tools/clients/client_compat.py android --image jelly-leon-clients/jelly-leon-server:12.4.0-jl.0-e294f84 \
  --soorten telefoon,tablet,tv,tv36 --vergelijk-soorten telefoon,tv
python3 tools/clients/client_compat.py android --aanvullen … --soorten tablet --vergelijk-soorten ""   # herhaling tablet
```

AVD's: telefoon `system-images;android-35;google_apis;x86_64` (pixel_6 op 720x1600), tablet idem (pixel_tablet
1280x800), tv `android-34;android-tv;x86` (tv_720p), tv36 `android-36;android-tv;x86_64`. Per emulator een verse
wegwerpserver met dezelfde bibliotheek en kijkgeschiedenis.

Uitkomst per stap (✔ geslaagd, ✘ mislukt, n.v.t. = niet aanwezig op de server, — = niet bereikt; harnas op
`68e02ea`/`2a0e2b9`):

| Stap | telefoon (Jelly Leon) | tablet (Jelly Leon) | tv API 34 (Jelly Leon) | tv API 36 (Jelly Leon) | telefoon (stock 12.4) | tv API 34 (stock 12.4) |
|---|---|---|---|---|---|---|
| naast de officiële app geïnstalleerd | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| inloggen | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| bladeren (incl. 'verder kijken' met het hervatitem) | ✔ | ✘ | ✔ | ✔ | ✔ | ✔ |
| hervatten op 300 s (eigen knop) | ✔ | — | ✔ | ✔ | ✔ | ✔ |
| hervatpunt na stoppen bewaard | ✔ | — | ✔ | ✔ | ✔ | ✔ |
| Direct Play (hero.mp4) | ✔ | — | ✔ | ✔ | ✔ | ✔ |
| transcode (AVI) | ✔ | — | ✔ | ✔ | ✔ | ✔ |
| ondertitel volgens voorkeur (NL) | ✔ | — | ✔ | ✔ | ✔ | ✔ |
| externe NL-ondertitel | ✔ | — | ✔ | ✔ | ✔ | ✔ |
| wisselen op afstand (informatief) | ✘ | — | (in extern) | (in extern) | ✘ | (in extern) |
| skipknoppen | n.v.t. | — | n.v.t. | n.v.t. | n.v.t. | n.v.t. |
| **oordeel** | **Sim-geslaagd** | **Sim-mislukt** | **Sim-geslaagd** | **Sim-geslaagd** | Sim-geslaagd | Sim-geslaagd |

Gemeten waarden: geschatte startpositie bij hervatten 299,99 s op alle geslaagde emulators (eerste melding 300,0 s);
bewaard hervatpunt 306,6–308,1 s; boot 20–22 s (tablet tot 33 s); `memory.peak` op de limiet van 4 GiB zonder
OOM-kill behalve de tablet.

Toelichting (gemeten):

- **Naast de officiële app:** op elke emulator staan `org.jellyfin.mobile` + `org.jellyfin.mobile.jellyleon` (resp.
  `org.jellyfin.androidtv` + `org.jellyfin.androidtv.jellyleon`) tegelijk geïnstalleerd; alleen de fork-app wordt
  bediend. De server ziet `Jellyfin for Android 2.7.3-jl.1` en `Jellyfin Android TV 0.19.10-jl.1` (technische
  identiteit ongewijzigd, ADR-0004).
- **Inloggen:** telefoon/tablet in de web-client van de server (jelly-leon-web 12.4) met naam en wachtwoord; tv in de
  native app via *Add account → Use a password*. Geen legacy-aanmeldkoppen nodig.
- **Bladeren:** startscherm met *My Media* (Films, Series) en *Continue Watching / Continue watching* met het gezaaide
  hervatitem; de filmbibliotheek (telefoon: alle 5 titels; tv: statusregel *"Showing All items from 'Films'"* en teller
  *1 | 5*); de seriepagina met twee seizoenen. Op de telefoon toont de bibliotheek ook het vinkje bij het gezaaide
  *gezien* en de voortgangsbalk bij het hervatpunt (schermafdruk).
- **Hervatten:** met de eigen knop van de app (*Resume* in de web-client, *Resume from 5:00* op de tv): de eerste
  gemelde positie is 300,0 s; na stoppen bewaart de server het nieuwe punt (306–308 s).
- **Direct Play:** hero.mp4 (DirectPlay). **Transcode:** de AVI (MPEG-4 ASP/MP3) wordt op alle emulators getranscodeerd
  (`ContainerNotSupported`, `VideoCodecNotSupported`, `AudioCodecNotSupported`; software, H.264/MP3 in TS). Gemeten:
  MPEG-2/AC3 in TS en H.264/AC3 in MKV spelen beide apps **direct** (ingebouwde ffmpeg-decoder van media3).
- **Ondertitels:** met de voorkeur NL/altijd kiest de server het ingebedde NL-spoor en de app speelt dat (index 2, ook
  in beeld). De externe `.nl.srt`: android volgt de spoorindex van *PlayNow* (index 1, in beeld); androidtv negeert die
  (`SocketHandler.onPlayMessage`) maar volgt `SetSubtitleStreamIndex` (EN → NL, in beeld).
- **Wisselen op afstand (informatief):** de native speler van android volgt `SetSubtitleStreamIndex` niet (de opdracht
  gaat naar de webweergave); **op stock 12.4 precies zo** — upstream-gedrag, geen regressie.
- **Skipknoppen:** niet beproefd: 12.4 heeft geen ingebouwde segmentprovider en de plugin 12.4.0-jl.0 levert er geen
  (`GET /MediaSegments/{id}` leeg voor alle 5 afleveringen) → capability_unavailable.
- **Geheugen:** telefoon, tv en tv36 binnen 4 GiB zonder OOM-kill (`memory.peak` op de limiet door de paginacache).
  **Tablet (pixel_tablet, 1280x800) is niet stabiel en staat op Sim-mislukt.** Geteld uit het bewijs bij de review:
  drie runs (07:20, 07:29 en 07:45 UTC) kregen binnen 4 GiB een OOM-kill van de container (tijdens het afspelen) en
  liepen daarna met 5 GiB (afwijking van B03 §10.14): één keer volledig geslaagd (`p4-0-jc3-android-tablet-herhaling-1.json`)
  en twee keer verloor de app haar sessie op de seriepagina (geen bestuurbare sessie meer binnen 30 s;
  `…-herhaling-2.json` en het hoofdbewijs). Daarnaast verloor de eerste run (06:55 UTC, onder `vervangen` in het
  hoofdbewijs) ook haar sessie op de seriepagina; of die run binnen 4 of 5 GiB liep, is niet meer na te gaan (het
  vervangen resultaat bewaarde geen geheugenmeting; sinds de review bewaart `--aanvullen` die wel). Oorzaak niet vastgesteld (vermoedelijk geheugendruk in de gast of op de gedeelde
  machine — tijdens twee pogingen draaide er een zware run van een andere agent); de telefoon met dezelfde app en
  hetzelfde systeemimage slaagde in alle drie de runs.
- **Vergelijking met stock 12.4** (telefoon en tv): elke stap gelijk, **0 regressies**.

## 2a. De officiële apps als stock-native client (JLT-63, rooktestdeel; bewijs `test-evidence/p4-0-jc3-android-officieel.json`)

Zelfde scenario's, maar nu bedient het harnas de **officiële** release (`--bediend officieel`; jellyfin-android 2.7.3 en
jellyfin-androidtv 0.19.10, naast de fork-app geïnstalleerd), tegen de Jelly Leon-image en tegen stock 12.4:

| Stap | telefoon (Jelly Leon) | tv API 34 (Jelly Leon) | telefoon (stock) | tv API 34 (stock) |
|---|---|---|---|---|
| inloggen, bladeren, hervatten, hervatpunt bewaard, Direct Play, transcode, ondertitels (voorkeur en extern) | ✔ | ✔ (herhaling, zie onder) | ✔ | ✔ |
| wisselen op afstand (informatief) | ✘ | (in extern) | ✘ | (in extern) |
| skipknoppen | n.v.t. | n.v.t. | n.v.t. | n.v.t. |
| **oordeel** | Sim-geslaagd | Sim-geslaagd | Sim-geslaagd | Sim-geslaagd |

**Eén intermitterende afwijking (eerlijk vermeld):** in de eerste run van de officiële tv-app tegen Jelly Leon meldde de
app bij hervatten eerst 300,0 s, daarna 1,0 s en 2,0 s en pas toen 302,6 s — de speler begon kort bij 0 en sprong dan
naar het hervatpunt. Die run staat als Sim-mislukt onder `vervangen` in het bewijs; de herhaling slaagde. Om te zien of
het aan de server ligt, is het hervatten daarna **6× op Jelly Leon en 6× op stock** herhaald met de officiële tv-app
(`client_compat.py hervatproef --soort tv --bediend officieel -n 6`, `test-evidence/p4-0-jc3-hervatproef-tv-officieel.json`):
**6/6 en 6/6**, telkens begonnen op 299,0–300,0 s. Samen: Jelly Leon 7 van 8 (officieel) en 3 van 3 (fork-app,
zelfde code), stock 7 van 7. Niet reproduceerbaar en past bij een race in de app (de speler past het startpunt toe na
de eerste voortgangsmelding); als uitzondering vastgelegd in ADR-0011 en een vervolgpunt om te blijven meten.

## 2b. Na de upgrade 10.11.11 → 12.4 (JLT-60, clientdeel; bewijs `test-evidence/p4-0-jc3-android-na-upgrade.json`)

HARDE EIS (kijkgeschiedenis blijft): dezelfde bibliotheek en dezelfde kijkgeschiedenis, nu eerst gezaaid op **stock
10.11.11** (`jellyfin/jellyfin:10.11.11@sha256:aefb67e6…`, incl. de ondertitelvoorkeur NL/altijd); server gestopt en
**dezelfde datamap** met de jelly-leon-image 12.4.0-jl.0 gestart (de server migreert zelf, zonder handwerk):

```
python3 tools/clients/client_compat.py android --migratie-van docker.io/jellyfin/jellyfin:10.11.11@sha256:aefb67e6… \
  --image jelly-leon-clients/jelly-leon-server:12.4.0-jl.0-e294f84 --soorten telefoon,tv --vergelijk-soorten "" \
  --uit docs/platform-v2/test-evidence/p4-0-jc3-android-na-upgrade.json
```

| Controle | telefoon | tv API 34 |
|---|---|---|
| kijkgegevens vóór (10.11.11) = na (12.4) per veld: hervatpunt 300 s, gezien (2×, met datum), favoriet + vind-ik-leuk, hervatlijst, ondertitelvoorkeuren | ✔ 0 verschillen | ✔ 0 verschillen |
| daarna in de fork-app: inloggen, 'verder kijken', hervatten op 300 s (eigen knop), Direct Play, transcode, ondertitels | ✔ alle stappen | ✔ alle stappen |
| **oordeel** | **Sim-geslaagd** | **Sim-geslaagd** |

Het serverdeel van JLT-60 (vijf gebruikers, rechten, apparaten, controle-run tegen stock) staat in jelly-leon
(`upgrade_proef.py`, 18/18); dit is het clientdeel ("daarna … de Android-emulator: inloggen en hervatten").

## 3. Desktop 2.0.0 onder Xvfb (bewijs `test-evidence/p4-0-jc3-desktop.json`)

```
make desktop-image desktop-test-image DOCKER_LOCK=…/docker-build.lock
JOBS=4 BUILD_TYPE=Release OUT=<werkmap>/desktop-bouw tools/clients/bouwverificatie/desktop_bouw.sh   # 62/62, ctest 1/1
python3 tools/clients/client_compat.py desktop --met-stock --image jelly-leon-clients/jelly-leon-server:12.4.0-jl.0-e294f84 \
  --build <werkmap>/desktop-bouw
```

**De eerdere blokkade is opgelost:** in de spike van jelly-leon (B03-016) bleef de app op `find-webclient.html`
staan. Gemeten oorzaak: met de standaard `/dev/shm` van Docker (64 MiB) geeft QtWebEngine
`net::ERR_INSUFFICIENT_RESOURCES` op elke bundle van de serverweb (`main.jellyfin.bundle.js`, `serviceworker.js`, …).
Met `--shm-size 1g` laadt de app de web-client van de Jelly Leon-server (jellyfin-web 12.4.0, titel *Jelly Leon*) en
werkt alles hieronder. Video via libmpv in software; schermafdrukken van het X-scherm met `xwd`.

| Stap | Jelly Leon 12.4.0-jl.0 | stock 12.4 |
|---|---|---|
| inloggen (find-webclient → serverweb → naam/wachtwoord) | ✔ | ✔ |
| bladeren (My Media, Continue Watching met het hervatitem, 5 films, 2 seizoenen) | ✔ | ✔ |
| hervatten op 300 s (knop *Resume*, muis-events via CDP) | ✔ (start ≈ 299,0 s) | ✔ (≈ 299,0 s) |
| hervatpunt na stoppen bewaard | ✔ (307,2 s) | ✔ (307,0 s) |
| Direct Play (hero.mp4) | ✔ | ✔ |
| transcode (AVI, maximale streamingbitrate 400 kbit/s) | ✔ (`ContainerBitrateExceedsLimit` + codecs; H.264/AAC in TS) | ✔ |
| ondertitel volgens voorkeur (NL) | ✔ | ✔ |
| externe NL-ondertitel (`SetSubtitleStreamIndex` EN → NL) | ✔ (NL gemeld na 4 s) | ✔ |
| skipknoppen | n.v.t. | n.v.t. |
| **oordeel** | **Sim-geslaagd**, 0 regressies | Sim-geslaagd |

Gemeten: mpv speelt alle testbestanden direct (ook AVI/MPEG-2/AC3); transcode alleen via de gebruikersinstelling
*maximale streamingbitrate*. De spoorindex van *PlayNow* wordt door de web-client niet doorgegeven (gevraagd 1,
gemeld 0; op stock gelijk); `SetSubtitleStreamIndex` werkt. Geen webfouten (CDP `Runtime.exceptionThrown`/`Log`); geheugen
van de container ≤ 0,95 GiB. Een eerdere run (zelfde dag) gaf twee schijnfouten van het harnas, beide op stock en Jelly
Leon gelijk: het hervatten leek 13,8 s te laat omdat openstaande CDP-timers het Node-proces ~15 s in leven hielden
(gerepareerd in `2a0e2b9`), en het venster van 10 s voor het wisselen naar NL was te kort (nu 20 s, gemeld na 4 s).

## 4. Swiftfin 1.6.1 (bewijs `test-evidence/p4-0-jc3-swiftfin-protocol.json` en `p4-0-jc3-routevergelijking-12.4.json`)

De app zelf: **NIET GEVALIDEERD (Mac/Xcode)**. Gemeten is de serverkant van haar protocol (exacte vormen uit de bron)
tegen de Jelly Leon-image en stock 12.4 (`python3 tools/clients/client_compat.py swiftfin --image …`):

| Stap | Jelly Leon 12.4.0-jl.0 | stock 12.4 |
|---|---|---|
| `isVersionCompatible` (server 12.4.0 ≥ SDK 12.0) | ✔ — geen melding "Update to Jellyfin 12.0" | ✔ |
| Aanmelden met de **ongequote** `MediaBrowser`-kop van jellyfin-sdk-swift 3.0.0 | ✔ | ✔ |
| API met de kop (`/Users/Me` 200, hervatlijst met het gezaaide item) | ✔ | ✔ |
| Sessie herkend als `Swiftfin iOS 1.6.1` | ✔ | ✔ |
| Websocket `/socket?api_key=…&deviceId=…` mét kop | 101 ✔ (alleen `api_key`: 403) | 101 ✔ (403) |
| Direct Play-URL zonder token (`/Videos/{id}/stream?static=true…`) | 200 ✔ | 200 ✔ |
| `TranscodingUrl` van de server (met `ApiKey`, niet `api_key`), `master.m3u8` zonder kop | 200 ✔ | 200 ✔ |
| Beheer: serverlog met `?api_key=` (`LogFile.swift`, informatief) | **401** | **401** |
| **Oordeel** | Sim-geslaagd, 0 regressies | Sim-geslaagd |

Statisch (`server_api_compat.py --sdk-taal swift`): alle **364** endpoints van jellyfin-sdk-swift 3.0.0 bestaan in de
12.4-servercode van de fork; Swiftfin gebruikt er **85**, geen ontbreekt (tegen 10.11.11 ontbrak `GET /Items/{}/Collections`).

## 5. Statische routevergelijking (ADR-0009 recept 1) en CI

`python3 tools/clients/server_api_compat.py` tegen `Jellyfin.Api/Controllers` van jelly-leon `e294f84` (12.4) en
10.11.11 (`1fbd873`): Kotlin-SDK 1.7.1 — 5 van de 408 endpoints ontbreken in 12.4
(`/Environment/NetworkShares`, `/Items/{}/CriticReviews`, `/LiveTv/Recordings/Groups/{}`, `/System/WakeOnLanInfo`,
`/Tmdb/ClientConfiguration`), **geen** ervan gebruikt door android (24 SDK-functies) of androidtv (76); exitcode 0.
Bewijs: `test-evidence/p4-0-jc3-routevergelijking-12.4.json` (bronnen, commits en commando's).

Nieuwe workflow **Clients / Compat 12.x (statisch)** (`.github/workflows/clients-compat.yml`): haalt server (upstream-tag
van de forkbasis, `v12.4`), de Kotlin-SDK (versie uit `libs.versions.toml`) en de Swift-SDK (revisie uit
`Package.resolved`) op en faalt als een gebruikte route ontbreekt. Run 42772580831 groen op `fc4b263`; Forkregels
42772580827 groen (217 passed, 2 skipped). Op `3101e90` (met al het bewijs en de docs): Forkregels 42782635549
(224 passed, 2 skipped — de byte-vergelijking met de contractbron, die op de runner niet naast de repo staat) en
Clients / Compat 12.x 42782635849, beide groen.

## 6. Tests en controles (lokaal)

| Commando | Uitkomst |
|---|---|
| `.venv/bin/python -m pytest -q tools/clients/tests` | 224 passed, 2 failed — de 2 = de byte-vergelijking met de actuele contractbron (1.3, zie hieronder); met `JLC_CONTRACT_BRON` = bron-commit 8b54f39: **226 passed** |
| `.venv/bin/ruff check --config tools/clients/ruff.toml tools/clients` | All checks passed |
| `actionlint .github/workflows/*.yml` | geen meldingen |
| `python3 tools/clients/check_clients.py`; `python3 tools/clients/app_identiteit.py bron` | in orde |
| `JLC_CONTRACT_BRON=<kopie van ai-server-manager 8b54f39> pytest tools/clients/tests/test_contract_kopie.py` | 5 passed (de kopie is byte-gelijk aan de vastgezette bron-commit) |

De byte-vergelijking met de **actuele** bron faalde lokaal bewust: ai-server-manager staat sinds 2026-11-10 op contract
1.3 (`02b119c`). Deze taak volgt 1.2; een nieuwe kopie overnemen is een stap van de orkestratie (C1.3-ALG-01/JLC-01).
In CI wordt die laag overgeslagen (bron niet naast de repo). *Stand vóór de review; sinds de review vergelijkt de test
met de bron op de bron-commit en is een nieuwere bron een waarschuwing (§8).*

## 7. Wat NIET gevalideerd is of ontbreekt

- Echte telefoons, tablets, tv's, Chromecast en DLNA (D15): **NIET GEVALIDEERD (hardware)**; JLT-69 Geblokkeerd.
- Swiftfin op iPhone/iPad/Apple TV: **NIET GEVALIDEERD (Mac/Xcode)**; alleen serverkant en statisch gemeten.
- Skipknoppen: geen segmenten op de server (F6 volgt); SyncPlay, downloaden en de MediaGuard-afspeeltest zijn niet in
  deze ronde (JLT-63 vraagt ze "met alle modules aan", P4).
- Echte NAS: **NIET GEVALIDEERD (echte NAS)**. De jelly-leon-image is lokaal gebouwd; een gepubliceerde image met
  digest volgt met de release 12.4.0-jl.1 (gebruiker, BG-02).
- Het dynamische deel draait niet in CI: het mediacorpus komt nooit in een repo of CI-image (BG-37/BG-38).

## 8. Onafhankelijke review P4-0 (2026-11-10)

Een tweede agent heeft het werk hierboven nagelopen: alle CI-stappen opnieuw gedraaid, het bewijs nagerekend en een
deel van de emulatortests **zelf opnieuw uitgevoerd** op dezelfde machine. Niets daarvan is op een echt apparaat:
**Sim-getest**; echte apparaten **NIET GEVALIDEERD (hardware)**, Swiftfin **NIET GEVALIDEERD (Mac/Xcode)**.

### 8.1 Opnieuw gebouwd en gedraaid

| Stap | Uitkomst |
|---|---|
| jelly-leon-image uit `git archive` van jelly-leon `e294f84ea` + jelly-leon-web `5ced8a246` (productie-Dockerfile, `BUILD_JOBS=2`, `WEB_BUILD_JOBS=2`, onder `docker-build.lock`, standaard-builder met gedeelde cache) | gebouwd; image-ID `sha256:ccd8de58f155…` (een andere ID dan `4671a48a…` van de bouwer: tijdstempels in de lagen), labels `12.4.0-jl.0`, revisies `e294f84…`/`5ced8a2…`; na de proef verwijderd |
| `make release-apks GRADLE_LOCK=…/gradle.lock` | BUILD SUCCESSFUL (2 min 9 s en 1 min 29 s); de ongetekende release-APK's zijn **byte-gelijk** aan die van de bouwer (`07b9e65f…742511a`, `f3b6bf39…a083334c`); `aapt2`: `org.jellyfin.mobile.jellyleon` 2070301 en `org.jellyfin.androidtv.jellyleon` 191001 |
| `client_compat.py android --soorten telefoon --vergelijk-soorten telefoon` (fork-app, `test-evidence/p4-0-review-android-telefoon.json` + schermafdrukken) | Jelly Leon en stock 12.4 beide **Sim-geslaagd**, 0 regressies: `org.jellyfin.mobile` 2.7.3 en `org.jellyfin.mobile.jellyleon` 2.7.3-jl.1 naast elkaar geïnstalleerd, sessie `Jellyfin for Android 2.7.3-jl.1`; hervatten met de eigen knop: eerste melding 300,0 s na 0,02 s (geschat 299,98 s), bewaard 306,97 s; Direct Play, transcode (AVI), ondertitels voorkeur en extern geslaagd; `memory.peak` op de 4 GiB-limiet zonder OOM-kill |
| `client_compat.py hervatproef --soort tv --bediend officieel -n 4` (harnas vóór reparatie, `…-hervatproef-tv-officieel-voor-reparatie.json`) | Jelly Leon 2/4, stock 2/4 — zie 8.2: een **schijnfout van het harnas**, op beide servers gelijk |
| idem `-n 5` na de reparatie (`49ca9d4`, `test-evidence/p4-0-review-hervatproef-tv-officieel.json`) | Jelly Leon **5/5**, stock **5/5**; start 298,98–299,99 s |

### 8.2 Gevonden en gerepareerd

1. **Hervatten: schijnfout bij een 0-melding (harnas).** De officiële tv-app 0.19.10 meldt bij hervatten soms eerst
   positie 0 en een seconde later 300,0 s (de speler staat dan al op het hervatpunt: 300,0 → 301,0 → 302,0 …). Het
   stopcriterium van het volgen telde die sprong als "opgelopen" en stopte na 3 meldingen; het oordeel zag dan maar 2
   positieve meldingen en gaf *positie liep niet op*. Gemeten in de review op **Jelly Leon én stock** (2/4 en 2/4 vóór de
   reparatie; na de reparatie 1 van 5 en 2 van 5 pogingen met zo'n 0-melding, alle geslaagd). Gerepareerd in `49ca9d4`
   (alleen de spelende staart telt; de 0-melding blijft zichtbaar als `eerst_een_melding_op_0`). Vanaf het begin spelen
   of terugspringen blijft mislukt. Het geval uit §2a (300,0 → 1,0 → 2,0 → 302,6: de speler speelde echt even vanaf 0)
   is een ander patroon; dat is in de review niet teruggezien (10 van 10 pogingen geslaagd).
2. **`--aanvullen` bewaarde van een vervangen run alleen oordeel en fout** — de gemelde posities van de mislukte
   tv-run uit §2a zijn daardoor niet meer in het bewijs (alleen als tekst hierboven) en de geheugenmeting van de eerste
   tabletrun ontbreekt. Nu blijven stappen en geheugen bewaard, hoort elk vervangen resultaat bij de juiste sessie en
   noemt het document de vervangen mislukte runs (`vervangen_mislukt`, `81ac69f`).
3. **Regressie telde een ontbrekende stap op Jelly Leon niet mee** (`1dfe0e8`): nu is "geslaagd op stock, níet
   geslaagd op Jelly Leon" een regressie. Het bestaande bewijs blijft op 0 regressies (herberekend).
4. **Migratievergelijking (JLT-60) kon leeg = leeg als geslaagd tellen** (`38511cd`): nu eerst de gezaaide
   kijkgeschiedenis op de oude server aantonen (hervatpunt tick-exact, hervatlijst, gezien 2×, favoriet). Het bestaande
   bewijs voldoet (offline herberekend uit de opgeslagen vóór/na-gegevens).
5. **Geheugen fail-closed** (`1143b21`): zonder leesbare geheugenmeting is de stap `geheugen` mislukt.
6. **Hervatproef** (`97a39a7`): n = gevraagd aantal; een fout per poging telt als mislukt en de proef gaat door.
7. **Drifttest contractkopie** (`d451087`): vergelijkt met de bron op de bron-commit; contract 1.3 in de bron is een
   waarschuwing, geen rode test.
8. **Docs:** de tablet werd in INVENTARIS §3, README en ADR-0009 als geslaagd meegeteld; dat is rechtgezet (tablet
   **Sim-mislukt**), en de telling van de tabletpogingen in §2 komt nu uit het bewijs (`39889ce`).

Nieuwe tests: 251 passed lokaal (was 224 + 2 failed), zie §8.3.

### 8.3 Controles van de review

| Commando | Uitkomst |
|---|---|
| `.venv/bin/ruff check --config tools/clients/ruff.toml tools/clients` | All checks passed |
| `.venv/bin/python -m pytest -q tools/clients/tests` | 251 passed, 2 waarschuwingen (contract 1.3 in de bron, bewust) |
| `JLC_CONTRACT_BRON=/bestaat-niet pytest -q tools/clients/tests/test_contract_kopie.py` | 4 passed, 2 skipped (zoals in CI) |
| `python tools/clients/check_clients.py`; `python tools/clients/app_identiteit.py bron` | in orde |
| `actionlint -color .github/workflows/*.yml`; `shellcheck` op de fork-eigen scripts | geen meldingen |
| GitHub Actions op `20318b4`: Clients / Forkregels 42788330886; Clients / Compat 12.x (statisch) 42788463957 (handmatig gestart) | beide success (249 passed, 2 skipped: de drifttestlaag zonder bronrepo) |

Niet opnieuw gedaan in de review (tijd en geheugen op de gedeelde machine): tablet, Android TV API 34/36 met de
fork-app, de migratieproef 10.11.11 → 12.4, de desktop onder Xvfb en het Swiftfin-protocol; daarvoor geldt het bewijs
van de bouwer (§2–§4), nagerekend maar niet herhaald.


## 9. Harnas veiliger: eigen testnetwerk, willekeurige testwachtwoorden, controle op buildbestanden (S-P40-72, 2026-11-16)

Drie verbeteringen uit de review van P4-0 (ADR-0011, besluit 15). Alles **Sim-getest** op de ontwikkelmachine; echte
apparaten **NIET GEVALIDEERD (hardware)**, Swiftfin **NIET GEVALIDEERD (Mac/Xcode)**.

1. **Geen hostnetwerk meer.** Emulator en desktop hangen alleen aan een eigen Docker-netwerk per testserver
   (`compat/netwerk.py`: `--internal` en `com.docker.network.bridge.inhibit_ipv4=true`); de app gebruikt
   `http://testserver:8096`. Gemeten (Docker 29.1.3): met alleen `--internal` bereikte een container een luisteraar
   op de host via het gateway-adres; de afschermingsproef gaf daar terecht *mislukt* (de host heeft dan een adres in
   het subnet, twee verbindingen bij de luisteraar). Met `inhibit_ipv4`: elk hostadres "Network is unreachable", de
   testserver bereikbaar. Die proef draait nu vóór elke emulator- en desktopstart (fail-closed) en staat per run in
   het bewijs (`netwerkafscherming`, zonder adressen of interfacenamen). CDP van de desktop luistert alleen in de
   container; het harnas gebruikt een doorgifte via `docker exec`.
2. **Testwachtwoorden per server willekeurig** (24 letters en cijfers); `bewijs.schrijf` krijgt de wachtwoorden van
   de run mee en weigert elk document waar er een in staat.
3. **`check_clients.py` faalt op een getrackt buildbestand in een clientmap** (`.kotlin`, `.gradle`, `build/`, APK,
   klassebestand, crashlog, `local.properties` …), ook als het in PATCHES.md geregistreerd is. De controle leest de
   commit (`--ref`, `git ls-tree`/`git diff`), niet de index.

Vergelijkingsrun met dezelfde serverbron als het vorige bewijs (besluit van de regisseur):

| Stap | Uitkomst |
|---|---|
| jelly-leon-image uit `git archive` van jelly-leon `e294f84ea` + jelly-leon-web `5ced8a246` (Dockerfile van die commit, `BUILD_JOBS=2`, `WEB_BUILD_JOBS=2`, onder `docker-build.lock`) | gebouwd; image-ID `sha256:36d2bec6b653…` (andere ID dan eerder: tijdstempels in de lagen), labels `12.4.0-jl.0`, revisies `e294f84…`/`5ced8a2…`; na de proef verwijderd |
| `make release-apks`, `make emulator-image`, `make desktop-test-image`, `make desktop-image`; desktop `JOBS=4 BUILD_TYPE=Release` met `desktop_bouw.sh` | BUILD SUCCESSFUL (2 min 1 s en 1 min 28 s); desktop 62/62, `ctest` 1/1 |
| `client_compat.py android --soorten telefoon --vergelijk-soorten telefoon` (`test-evidence/p4-0-s-p40-72-android-telefoon.json` + schermafdrukken) | Jelly Leon en stock **Sim-geslaagd**, 0 regressies; afscherming op beide geslaagd; hervatten eerste melding 300,0 s na 0,01 s, bewaard 306,59 s; elke stap dezelfde uitkomst als in `p4-0-review-android-telefoon.json` (ook `ondertitel_wisselen_op_afstand` blijft op beide servers *mislukt*, zoals eerder; geen verplichte stap) |
| `client_compat.py desktop --met-stock` (`test-evidence/p4-0-s-p40-72-desktop.json` + schermafdrukken) | Jelly Leon en stock **Sim-geslaagd**, 0 regressies; afscherming geslaagd; elke stap dezelfde uitkomst als in `p4-0-jc3-desktop.json`; nieuw: één webfout `net::ERR_NAME_NOT_RESOLVED` voor het Cast-script van gstatic.com — gevolg van het afgeschermde netwerk (geen internet in de container), geen stap afhankelijk |

Geen scenario ging van geslaagd naar mislukt. Niet herhaald in deze stap: tablet, Android TV, de migratieproef,
de hervatproef en het Swiftfin-protocol (de stap vraagt telefoon en desktop); hervatproef en Swiftfin gebruiken
dezelfde gewijzigde code en zijn alleen met unit-tests gedekt.

### 9.1 Herstel na de review van S-P40-72 (2026-11-17)

De reviews vonden acht bevindingen (vijf van R-VEILIG, drie van R-TECH) en één vervolgpunt; alles is hersteld, elk
met een test die zonder het herstel faalt (mutatieproef: 22 mutaties in een kopie, alle rood). ADR-0011 besluit 15
is bijgewerkt. Alles **Sim-getest**; echte apparaten **NIET GEVALIDEERD (hardware)**.

1. **CDP vertrouwt geen adres uit de container (R-VEILIG-1).** Een nep-CDP in de desktopcontainer liet het harnas op
   de host een dienst openen die alleen op 127.0.0.1 luistert (via `webSocketDebuggerUrl` en via een doorverwijzing
   van `/json/list`). `desktop_cdp.mjs` volgt nu geen doorverwijzing, neemt van `webSocketDebuggerUrl` alleen een pad
   `/devtools/page/<id>` en verbindt altijd met `ws://127.0.0.1:<doorgiftepoort><pad>`; al het andere geeft
   `ok: false`. Test: `tools/clients/tests/test_compat_cdp.py` (echte Node tegen een nep-CDP en een lokker op
   127.0.0.1; de lokker krijgt niets). De Forkregels-workflow zet daarvoor Node 22.22.1 klaar.
2. **IPv6 dicht en getoetst (R-VEILIG-2).** Het testnetwerk is expliciet zonder IPv6 (`--ipv6=false`). De
   afschermingsproef luistert dual-stack (`::`), probeert ook elk IPv6-adres van de host en eist dat de container
   geen IPv6-adres buiten `lo` heeft. Een netwerk met IPv6 geeft nu *mislukt* (eerder *geslaagd*).
3. **Desktop: eerst de proef, dan de app (R-VEILIG-3).** De desktopcontainer start met `sleep infinity`; Xvfb en de
   app starten pas na de afschermingsproef met `docker exec -d`.
4. **Wachtwoordweigering per schrijfpad (R-VEILIG-4, R-TECH-2).** Tests voor desktop, hervatproef en Swiftfin (naast
   Android) en een test dat de desktop- en de telefoon-app `http://testserver:8096` krijgen, niet het hostadres.
5. **Meer buildbestanden (R-VEILIG-5).** `.hprof`, `.ninja_log`, `compile_commands.json`,
   `release/output-metadata.json`; mapnamen zonder hoofdlettergevoeligheid. De source set `src/release` blijft
   toegestaan.
6. **Mislukte serverstart ruimt zelf op (R-TECH-1).** Faalt `TestServer.start` (bv. `docker run`, ontbrekend
   corpusbestand, time-out), dan gaan container, netwerk en map weg.
7. **Verwijderd buildbestand van upstream (R-TECH-3).** Echte test: upstream trackt `app/build/x.apk`, de fork
   verwijdert het en registreert dat; geen melding.
8. **Opruimen na een afgebroken proces (vervolgpunt R-TECH).** Dit punt beschrijft de stand van efe0daa en is
   daarna gewijzigd; de huidige regels staan in §9.2 en in ADR-0011 besluit 15.

Opnieuw gedraaid met dezelfde serverbron als het vorige bewijs:

| Stap | Uitkomst |
|---|---|
| jelly-leon-image uit `git archive` van jelly-leon `e294f84ea` + jelly-leon-web `5ced8a246` (zelfde Dockerfile en argumenten als in §9, onder `docker-build.lock`); emulator- en desktop-testimage | gebouwd (uit de buildcache); image-ID `sha256:7c389e15a00e…`, labels `12.4.0-jl.0`, revisies `e294f84…`/`5ced8a2…`; na de proef verwijderd |
| release-APK's en desktop-build | niet opnieuw gebouwd: de ongetekende APK's zijn byte-gelijk aan die van de review (`07b9e65f…`/`f3b6bf39…`); de desktop-build (Release) is die van §9, uit dezelfde bron `desktop/` |
| `client_compat.py android --soorten telefoon --vergelijk-soorten telefoon` (`test-evidence/p4-0-s-p40-72-herstel-android-telefoon.json` + schermafdrukken) | Jelly Leon en stock **Sim-geslaagd**, 0 regressies; afscherming op beide geslaagd (IPv6 in de container: alleen `lo`; 0 verbindingen bij de dual-stack-luisteraar); hervatten op Jelly Leon eerste positie 300,02 s, bewaard 306,99 s; elke stap dezelfde uitkomst als in `p4-0-review-android-telefoon.json` en `p4-0-s-p40-72-android-telefoon.json` |
| `client_compat.py desktop --met-stock` (`test-evidence/p4-0-s-p40-72-herstel-desktop.json` + schermafdrukken) | Jelly Leon en stock **Sim-geslaagd**, 0 regressies; afscherming geslaagd (zelfde metingen); elke stap dezelfde uitkomst als in `p4-0-jc3-desktop.json` en `p4-0-s-p40-72-desktop.json`; dezelfde ene webfout voor het Cast-script van gstatic.com als in §9 |

Geen scenario ging van geslaagd naar mislukt. Na de runs: geen testnetwerk en geen testcontainer over. Niet herhaald:
tablet, Android TV, de migratieproef, de hervatproef en het Swiftfin-protocol (alleen unit-tests, zoals in §9).

### 9.2 Herstelrondes na de herreviews van S-P40-72 (38ae5fb..a4f8ce0, 2026-11-17)

De herreviews (R-HERREV-1, R-HERREV-2, R-HERREV2-1, R-HERREV2-2) en twee aanvullingen van de regisseur leidden tot
vier commits: `38ae5fb`, `7f576bb`, `a5881cc` en `a4f8ce0`. Elk herstel heeft een test die zonder het herstel faalt.
De volledige regels staan in ADR-0011 besluit 15. Alles **Sim-getest**; echte apparaten **NIET GEVALIDEERD
(hardware)**.

1. **Eigenaarlabel met PID-namespace, onder een nieuwe sleutel.** Het label heeft de vorm
   `<pid>:<starttijd>:<PID-namespace>` en staat onder de sleutel `jelly-leon-clients.compat.eigenaar2`. Opgeruimd wordt
   alleen bij een dode eigenaar in dezelfde PID-namespace. Een object uit een andere of onbekende namespace blijft
   staan, en ook als het eigen `/proc` niet leesbaar is. Een oudere harnasversie (381ad53 t/m efe0daa) las de oude
   sleutel `jelly-leon-clients.compat.eigenaar` en kon zo het netwerk van een levende nieuwe run weghalen; onder de
   nieuwe sleutel laat die versie het object staan. De nieuwe versie leest de oude sleutel niet: een object met alleen
   de oude sleutel blijft staan en moet met de hand weg.
2. **Labels ook op containers.** Server-, emulator- en desktopcontainers krijgen een eigen label
   (`jelly-leon-clients.compat=server`, `=emulator` of `=desktop`) en het eigenaarlabel. Vóór een nieuwe start gaat een
   achtergebleven container van die soort weg, met dezelfde regels (alleen bij een dode eigenaar in dezelfde
   PID-namespace).
3. **Unieke containernamen.** Server, emulator en desktop krijgen per run een naam met een willekeurig achtervoegsel
   (`jlc-jc3-server-<pid>-<n>-<12 hex>`, `jlc-jc3-emulator-<willekeurig>`, `jlc-jc3-desktop-<willekeurig>`). De vaste
   namen `jlc-jc3-emulator` en `jlc-jc3-desktop` zijn vervallen, zodat `docker rm -f` alleen de eigen container raakt.
4. **Datamap van een opgeruimde server.** De datamap gaat alleen mee weg als die precies `<werkmap>/<servernaam>` is:
   een naam die `TestServer` zelf kiest, geen symlink, na `resolve` direct onder de werkmap, en met alleen `config` en
   `cache` erin. Elk ander pad blijft staan.
5. **Terugval bij `hidepid`.** Is `/proc/<pid>` niet leesbaar terwijl het eigen `/proc` dat wel is, dan beslist
   `os.kill(pid, 0)`. Alleen `ProcessLookupError` betekent dood; `PermissionError` of geen fout betekent levend. Een
   pid van 0 of lager telt als levend.
6. **AVD gedeeld onder `gradle.lock`.** De AVD-map (`<werkmap>/avd`) en de AVD-naam `jlc-jc3-<soort>` blijven gedeeld
   tussen runs. Dat is veilig omdat een emulator alleen binnen `gradle.lock` draait (machinebreed één tegelijk; met een
   test). Voorwaarde: runs met dezelfde werkmap (`JLC_WERK`) gebruiken ook dezelfde `.lokaal` voor de sloten.

Rooktests in deze rondes, met dezelfde serverbron als het vorige bewijs (jelly-leon `e294f84` + jelly-leon-web
`5ced8a2`; images uit de buildcache):

| Rooktest | Uitkomst |
|---|---|
| desktop (`client_compat.py desktop --met-stock`), ronde 38ae5fb | Jelly Leon en stock **Sim-geslaagd**; afscherming geslaagd (0 verbindingen); uitkomsten gelijk aan het vorige desktopbewijs |
| telefoon (`client_compat.py android --soorten telefoon --vergelijk-soorten telefoon`), ronde 7f576bb, zelfde APK (`07b9e65f…`) | Jelly Leon en stock **Sim-geslaagd**; afscherming geslaagd (0 verbindingen); 24 van 24 uitkomsten gelijk aan het vorige telefoonbewijs |
| desktop (`client_compat.py desktop --met-stock`), ronde a4f8ce0 | Jelly Leon en stock **Sim-geslaagd**; afscherming geslaagd (0 verbindingen); tijdens de run droegen netwerk, server- en desktopcontainer alleen de sleutel `eigenaar2` |

Vergeleken per uitkomstveld: desktop 22 van 22 en telefoon 24 van 24 gelijk aan het vorige bewijs, 0 verschillen.
Na de runs: geen testnetwerk en geen testcontainer over. De uitvoer van deze rooktests (bewijs-JSON's en
schermafdrukken) staat lokaal op de ontwikkelmachine, niet in deze repo; `test-evidence/` heeft geen nieuwe bestanden.
Niet herhaald: tablet, Android TV, de migratieproef, de hervatproef en het Swiftfin-protocol (alleen unit-tests).
