# ADR-0011 — Clientcompatibiliteit met de Jelly Leon 12.x-server (P4-0, JC3): harnas, controlegroep en meetregels

- **Status:** Aanvaard (2026-11-10, P4-0)
- **Context:** de server is in P4-0 naar Jellyfin 12.4 gegaan (`jelly-leon` 12.4.0-jl.0, met de web-client van
  `jelly-leon-web` 12.4; ADR-0027 en ADR-0011 in jelly-leon). `CONTRACT_1.2_CONFORMITEIT.md` §11 JC3 vraagt de
  Android-clients op compatibiliteit met 12.x te controleren en Swiftfin 1.6.1 te herbeoordelen; ADR-0009 legt het
  recept vast; B03 §8.2 punt 5 en §10.14 (clientmatrix) en B03-016/B03-019 vragen emulatortests, een desktoprun onder
  Xvfb en Swiftfin als **NIET GEVALIDEERD (Mac/Xcode)**. HARDE EIS van de gebruiker: de kijkgeschiedenis (gezien,
  hervatpunten, favorieten, spoorkeuzes) blijft behouden — elke clienttest moet laten zien dat een client die
  geschiedenis toont en op het juiste punt hervat.

## Besluiten

1. **Eigen harnas in deze repo** (`tools/clients/compat/`, opdrachtregel `tools/clients/client_compat.py`), niet een
   aanroep van het B03-016-harnas van jelly-leon: deze repo test haar eigen fork-builds en mag niet afhangen van code
   in een andere repo. De gemeten lessen van jelly-leon B03-016 zijn overgenomen (emulator in een container, adb-server
   vóór de emulator starten, kleiner scherm tegen OOM-kills, ruwe CDP voor de desktop).
2. **Fork-apps als release-build met de eigen applicationId** (`org.jellyfin.mobile.jellyleon`,
   `org.jellyfin.androidtv.jellyleon`, forkversies `2.7.3-jl.1` en `0.19.10-jl.1`), niet de debug-build met `.debug`:
   zo test de emulator de echte ID en de R8-build. Ondertekend met een **wegwerp-testsleutel** die per run ontstaat en
   daarna verdwijnt (geen releasesleutel; verspreiden blijft wachten op ADR-0008). De officiële release-APK (sha256
   gecontroleerd) wordt ernaast geïnstalleerd: zo is "naast de officiële app" (ADR-0004) voor het eerst gemeten.
3. **Server = de jelly-leon-image**, lokaal gebouwd met de productie-Dockerfile van jelly-leon uit een `git archive`
   van jelly-leon en jelly-leon-web (alleen gelezen, niets gepubliceerd); de image van de jelly-leon-CI wordt niet
   gepubliceerd. **Controlegroep:** stock `jellyfin/jellyfin:12.4` op dezelfde upstream-digest als de forkbasis. Een
   **regressie** is een stap die op stock slaagt en op Jelly Leon faalt; een stap die op beide faalt, is upstream-gedrag
   en staat zo in het bewijs.
4. **Per client een verse wegwerpserver** met dezelfde testbibliotheek (alleen vrij gelicentieerde corpusbestanden,
   per bestand alleen-lezen gekoppeld, BG-37) en dezelfde **gezaaide kijkgeschiedenis** van de kijker: hervatpunt
   300 s in Tears of Steel, hero 2× gezien, een favoriet. Bladeren slaagt pas als de app 'verder kijken' met het
   hervatitem toont; hervatten pas als de app via haar **eigen knop** binnen ± 10 s van 300 s begint.
5. **Oordeel aan de serverkant** (`GET /Sessions`, `UserData`): wat de client zelf meldt. Bediening zoals een gebruiker
   voor inloggen, bladeren en hervatten (aanraken op telefoon/tablet, D-pad op de tv, muis-events via CDP op de
   desktop); voor de overige stappen de officiële afstandsbedieningsroutes (`/Sessions/{id}/Playing`, `/Viewing`,
   `/Command`). De startpositie bij hervatten wordt geschat als eerste gemelde positie minus de tijd tot die melding.
6. **Transcode** met het eerste kandidaat-item dat de app niet direct kan spelen (AVI met MPEG-4 ASP, daarna MPEG-2/AC3
   in TS) — gemeten: android en androidtv spelen MPEG-2/AC3 direct dankzij hun ffmpeg-decoder. De desktop (mpv) speelt
   alles direct; daar gaat transcode via de gebruikersinstelling *maximale streamingbitrate* (400 kbit/s).
7. **Ondertitels:** (a) de taalvoorkeur van de gebruiker (NL, altijd) moet tot het NL-spoor leiden — net als een
   overgenomen voorkeur; (b) een externe `.nl.srt` naast de film, via de route die de app ondersteunt (gemeten:
   android volgt de spoorindex van `PlayNow`; androidtv en de desktop negeren die maar volgen
   `SetSubtitleStreamIndex`). Zichtbaarheid alleen via schermafdrukken (geen OCR).
8. **Skipknoppen:** Jellyfin 12.4 heeft geen ingebouwde segmentprovider en de Jelly Leon-plugin 12.4.0-jl.0
   implementeert er geen; de server levert dus geen segmenten → `niet_aanwezig` (capability_unavailable), nooit
   "geslaagd". Wordt beproefd zodra F6 segmenten levert (B03-07x).
9. **Geheugen:** emulator binnen 4 GiB (geheugen = swap, B03 §10.14); bij een OOM-kill één herhaling met 5 GiB, beide
   pogingen in het bewijs en als afwijking gemeld (zelfde beleid als jelly-leon B03-016).
10. **Desktop:** container met `--shm-size 1g`. Gemeten oorzaak van de eerdere blokkade (jelly-leon B03-016,
    desktop-spike): met de standaard `/dev/shm` van Docker (64 MiB) geeft QtWebEngine `net::ERR_INSUFFICIENT_RESOURCES`
    op elke bundle van de serverweb en blijft de app op `find-webclient.html` staan. Het doel `test` van
    `bouwverificatie/desktop.Dockerfile` voegt Xvfb, `xwd` en de QML-runtimemodules uit `debian/control` toe; zonder
    `--target` blijft de bouwomgeving ongewijzigd.
11. **Swiftfin:** de app zelf blijft **NIET GEVALIDEERD (Mac/Xcode)**. Wel gemeten: (a) statisch alle routes van
    jellyfin-sdk-swift 3.0.0 die Swiftfin gebruikt tegen de 12.4-servercode (`server_api_compat.py --sdk-taal swift`);
    (b) de serverkant van het protocol met de exacte vormen uit de bron (ongequote `MediaBrowser`-kop, websocket met
    `api_key` én kop, statische stream zonder token, `TranscodingUrl` met `ApiKey`, serverlog met `api_key`).
12. **Rollen:** de fork-app (eigen applicationId) en de officiële app (rol *stock-native*, JLT-63) worden apart
    bediend (`--bediend fork|officieel`); de desktop telt als *officiële app met serverweb*. Bij een afwijking die maar
    één keer optreedt, wordt de stap herhaald op Jelly Leon én stock (`client_compat.py hervatproef`) voordat er een
    oordeel over de server valt.
13. **Uitzondering (B03-019: een afwijking alleen met een ADR):** één run van de officiële tv-app tegen Jelly Leon
    begon bij hervatten kort bij 0 en sprong daarna naar het hervatpunt. Niet reproduceerbaar (daarna 6/6 op Jelly Leon
    en 6/6 op stock; de fork-app met dezelfde code 3/3) en passend bij een race in de app. Geaccepteerd als
    intermitterend clientgedrag, níet als serverregressie; de run blijft in het bewijs (`vervangen`) en de herhaalproef
    draait bij elke volgende module-oplevering mee.
14. **CI:** de statische controle draait als workflow *Clients / Compat 12.x (statisch)*; de SDK-versies komen uit de
    clientbronnen. Het dynamische deel draait alleen lokaal: het mediacorpus komt nooit in een repo of CI-image
    (BG-37/BG-38) en de jelly-leon-image wordt (nog) niet gepubliceerd.

## Gevolgen

- Uitkomsten en exacte commando's: `docs/platform-v2/BOUWVERIFICATIE_P4-0.md` en `test-evidence/p4-0-jc3-*`.
  Validatie: **Sim-getest** (emulator/container op de ontwikkelmachine); echte apparaten **NIET GEVALIDEERD
  (hardware)**; Swiftfin **NIET GEVALIDEERD (Mac/Xcode)**.
- De matrix in `jelly-leon/docs/platform-v2/CLIENT_COMPAT_MATRIX.md` is van jelly-leon (alleen gelezen); de stand van de
  clients staat in `INVENTARIS.md` §3 van deze repo en in het bewijs; overnemen in de matrix is een vervolgpunt voor
  jelly-leon.
- Contract 1.3 verscheen in ai-server-manager tijdens deze ronde; deze taak volgt 1.2. De kopie blijft 1.2 (een nieuwe
  kopie overnemen is een stap van de orkestratie, C1.3-ALG-01/C1.3-JLC-01); de lokale byte-vergelijking van de
  drifttest meldt dat verschil zoals bedoeld (in CI wordt die laag overgeslagen).
