# Changelog — jelly-leon-clients

Alleen fork-eigen wijzigingen; de clients zelf volgen hun upstream-releases (zie `tools/clients/baseline.json`).

## P0 — 2026-11-09 (ontwikkelstand, niets gepubliceerd)

- Import als git subtree (squash): jellyfin-android v2.7.3, jellyfin-androidtv v0.19.10, jellyfin-desktop v2.0.0,
  Swiftfin 1.6.1. Forkversies `<upstream>-jl.0`.
- Desktop: lege submodule-gitlink `external/mpvqt` vervangen door de KDE MpvQt-bron op de door upstream gepinde commit
  `2ebbd38` (geneste subtree, JLC-0001).
- Fork-tooling: basislijn, forkregels/patchregister-controle, upstream-sync per client in `sync/<client>-<tag>`;
  39 tests.
- CI per client (pad-filters), forkregels en wekelijkse upstream-sync; nog niet op GitHub gedraaid.
- Bouwverificatie: desktop (Linux) gebouwd en unit-getest in een container; Android geblokkeerd in de bouwomgeving;
  Swiftfin NIET GEVALIDEERD (Mac/Xcode).
- Docs: README, forkstrategie, inventaris, patchregister, ADR-0001…0009. Branding en app-identiteit ongewijzigd.
