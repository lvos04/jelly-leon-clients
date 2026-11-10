# Changelog — jelly-leon-clients

Alleen fork-eigen wijzigingen; de clients zelf volgen hun upstream-releases (zie `tools/clients/baseline.json`).

## P0 — 2026-11-09 (ontwikkelstand, niets gepubliceerd)

- Import als git subtree (squash): jellyfin-android v2.7.3, jellyfin-androidtv v0.19.10, jellyfin-desktop v2.0.0,
  Swiftfin 1.6.1. Forkversies `<upstream>-jl.0`.
- Desktop: lege submodule-gitlink `external/mpvqt` vervangen door de KDE MpvQt-bron op de door upstream gepinde commit
  `2ebbd38` (geneste subtree, JLC-0001).
- Fork-tooling: basislijn, forkregels/patchregister-controle, upstream-sync per client in `sync/<client>-<tag>`;
  39 tests.
- CI per client (pad-filters), forkregels en wekelijkse upstream-sync (toen nog niet op GitHub gedraaid; zie de
  afronding hieronder).
- Bouwverificatie: desktop (Linux) gebouwd en unit-getest in een container; Android geblokkeerd in de bouwomgeving;
  Swiftfin NIET GEVALIDEERD (Mac/Xcode).
- Docs: README, forkstrategie, inventaris, patchregister, ADR-0001…0009. Branding en app-identiteit ongewijzigd.
- Review P0: inhoud (tree-hash) van elke squashcommit gecontroleerd tegen de basislijn; forkregels lezen basislijn en
  register uit de gecontroleerde commit; beschermde licentiebestanden moeten bestaan; sync draait bij elke fout terug;
  sync-workflow zonder opgeslagen token en zonder schrijfbare cache voor onbeoordeelde upstream-code;
  workflowregels als tests. 92 tests.
- Afronding P0 (eigen machine, geen proxy): android en androidtv lokaal gebouwd (`assembleDebug test`; androidtv 15/15
  tests per variant, android heeft upstream geen tests), desktop opnieuw gebouwd (62/62, ctest 1/1); Gradle-wrappers
  tegen gradle.org gecontroleerd; GitHub-runs van alle client-workflows groen. `make android-bouw`/`androidtv-bouw`
  en optionele `GRADLE_LOCK`/`DOCKER_LOCK`.
- Besluiten gebruiker vastgelegd: ADR-0004 (eigen applicationId/bundle-id naast de officiële apps, patch in P4) en
  ADR-0009 (Swiftfin 1.6.1 blijft, server vóór P4 naar Jellyfin 12.x). Nieuw: `tools/clients/server_api_compat.py`
  (routes van twee serverversies tegen de SDK-endpoints van de clients) met 7 tests; voorlopige meting v10.11.11 ↔
  v12.4: geen door android/androidtv gebruikte route weg. 99 tests.
- Review P0-afronding: Dockerfile-frontend op digest (`docker/dockerfile:1.7.1@sha256:…`), proxyrestanten uit de
  Makefile en de bouwdocs; drie extra negatieve sync-tests; nieuwe tests voor de bouwcontainer en voor
  `EVIDENCE.json` (§11); verouderde teksten in workflowcommentaar en ADR-0002/0005/0006 rechtgezet; ADR-0008 met
  toetsing per contractparagraaf. Android, Android TV en desktop opnieuw gebouwd: artefacten byte-gelijk. 115 tests.

## Contract 1.2 — 2026-11-09 (ontwikkelstand, niets gepubliceerd)

- Kopie van `PLATFORM_CONTRACTEN.md` (`contracts 1.2`) en `CONTRACT_1.2_CONFORMITEIT.md`, byte-gelijk aan
  ai-server-manager `8b54f39`, met drifttest (vaste SHA-256; met de bronrepo ernaast ook byte-vergelijking).
- **Eigen app-identiteit naast de officiële apps** (besluit van de gebruiker, ADR-0004; JC1/JC2), als geregistreerde
  patches zonder codewijziging: JLC-0002 android `org.jellyfin.mobile.jellyleon`, JLC-0003 androidtv
  `org.jellyfin.androidtv.jellyleon` (ook `app_id`, zoek-authority/-data uit de applicationId en de back-upregels),
  JLC-0004 Swiftfin `org.jellyfin.swiftfin.jellyleon` (xcconfig én de doelinstelling iOS-Release; NIET GEVALIDEERD
  (Mac/Xcode)). Forkversies `2.7.3-jl.1`, `0.19.10-jl.1`, `1.6.1-jl.1`.
- `tools/clients/app_identiteit.py` (+ `app_identiteit.json`): controle in de bron, met `aapt2` op APK's en gelinkte
  release-resources, en op de Xcode-build-instellingen; in CI in Forkregels, Android, Android TV en Swiftfin;
  `make check` en `make android-bouw`/`androidtv-bouw` draaien hem ook. 159 tests.
- Lokaal gebouwd met de patches: android `assembleDebug assembleRelease test` (4 APK's), androidtv idem (15/15 tests
  per variant); `aapt2` 0 overtredingen; tegenproeven op een echte upstream-build en een "halve patch" falen zoals
  bedoeld.
- ADR-0010 (contract 1.2 in deze repo); ADR-0004 met de vastgezette ID's; ADR-0008 getoetst aan 1.2 (§13 N.v.t.).
- JC3 (clients tegen de 12.x-server) niet uitgevoerd: de server staat nog op 10.11.11 (wacht op JL1).
- Review contract 1.2: nieuwe test dat elke identiteitspatch minimaal blijft (vaste omvang per bestand t.o.v. de
  upstream-basis, alleen regels over de app-identiteit); syncproef met `upstream_sync.py` op de upstream-hoofdbranches
  (android schoon, gebouwd en `aapt2` 0 overtredingen; androidtv en Swiftfin falen bewust en draaien terug); upstream
  `detekt lint` zonder bevinding op een patchregel. 168 tests.

## P4-0 / JC3 — 2026-11-10 (ontwikkelstand, niets gepubliceerd)

- Compatibiliteitsharnas `tools/clients/compat/` (`tools/clients/client_compat.py`, `make compat-*`): wegwerpserver
  (jelly-leon-image of stock 12.4 op digest) met vrije corpusbestanden alleen-lezen en gezaaide kijkgeschiedenis;
  Android-/Android TV-emulator in een container (KVM, 4 GiB, onder `stack.lock` + `gradle.lock`); desktop onder Xvfb
  met ruwe CDP; serverkant van het Swiftfin-protocol; bewijs zonder geheimen, met stock als controlegroep.
- Fork-apps als release-build met de eigen applicationId, ondertekend met een wegwerp-testsleutel, naast de officiële
  APK op telefoon, tablet, Android TV API 34 en API 36: inloggen, bladeren, hervatten op 300 s, hervatpunt bewaard,
  Direct Play, transcode, ondertitels (voorkeur en extern) Sim-getest; 0 regressies tegen stock 12.4. Skipknoppen niet
  beproefd (geen segmentprovider in 12.4/plugin). Tablet alleen met 5 GiB (binnen 4 GiB OOM-kill, gemeld).
- Desktop 2.0.0 onder Xvfb werkt tegen de Jelly Leon-server: de blokkade van de spike in jelly-leon kwam door de
  standaard `/dev/shm` van Docker (`net::ERR_INSUFFICIENT_RESOURCES`); met `--shm-size 1g` opgelost. Doel `test` in
  `bouwverificatie/desktop.Dockerfile` (Xvfb, xwd, QML-runtime).
- Officiële apps als stock-native client (`--bediend officieel`) tegen Jelly Leon en stock: 0 regressies; één
  intermitterende hervatafwijking van de officiële tv-app, daarna `hervatproef` 6/6 op Jelly Leon en 6/6 op stock
  (ADR-0011 punt 13). Upgrade 10.11.11 → 12.4 van dezelfde datamap (`--migratie-van`): kijkgegevens per veld gelijk,
  telefoon en tv hervatten op 300 s (JLT-60, clientdeel).
- `server_api_compat.py --sdk-taal swift` (jellyfin-sdk-swift) en de CI-workflow *Clients / Compat 12.x (statisch)*.
- ADR-0011 (harnas en meetregels); ADR-0009 herbeoordeeld tegen 12.4 (Swiftfin: versiecontrole slaagt, protocol gelijk
  aan stock; serverlog met `api_key` → 401). `BOUWVERIFICATIE_P4-0.md`, INVENTARIS §3, README.
