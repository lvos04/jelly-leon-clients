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
