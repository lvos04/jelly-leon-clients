# ADR-0007 — Licenties, credits en bronbeschikbaarheid

- **Status:** Aanvaard (P0, 2026-11-09); één **open gebruikersbesluit** (zichtbaarheid)
- **Context:** B03-001 vraagt GPL-2.0-naleving. De clients hebben verschillende licenties: android, androidtv en desktop
  **GPL-2.0**, Swiftfin **MPL-2.0**, mpvqt **LGPL-2.1-only/LGPL-3.0-only**. Daarnaast zitten er componenten van derden in
  builds (Google Play Services/Cast in android *proprietary*, VLCKit LGPL-2.1 in Swiftfin, Qt/libmpv op desktop).

## Besluit

- Licentiebestanden en credits blijven **byte-gelijk** aan upstream; `check_clients.py` weigert elke wijziging aan
  `android/LICENSE.md`, `androidtv/LICENSE`, `androidtv/CONTRIBUTORS.md`, `desktop/LICENSE`, `swiftfin/LICENSE.md` en de
  LGPL-teksten van mpvqt — ook met registratie — en eist dat ze bestaan (verdwijnt er upstream een, dan faalt de
  sync en beoordeelt een mens). Geen extra licentiebestand in de root zonder vraag aan de gebruiker.
- Fork-eigen code (`tools/`, workflows, docs) krijgt in P0 **geen** eigen licentie (contract §10: niet zonder vraag).
- **Wijzigingen herkenbaar** (GPL-2.0 §2a, MPL-2.0 §3.3): elke afwijking staat met datum en doel in `PATCHES.md`.
- **Bron beschikbaar** voor elke verspreide build: de exacte commit van deze repo (inclusief vendored mpvqt) hoort bij
  elke APK/IPA/installer; release-artefacten (later) krijgen commit-hash en forkversie in de naam/metadata.
- "Gebaseerd op Jellyfin/Swiftfin" blijft zichtbaar; geen upstream-logo als eigen merk; geen schijn van een officiële
  Jellyfin-release (ADR-0004).
- Voor verspreiding buiten het eigen huishouden de *libre*-flavor van android overwegen (geen Google-binaries).

## Open gebruikersbesluit

- Zichtbaarheid van `lvos04/jelly-leon-clients` (publiek/privé) vóór de eerste verspreide build: met een privé-repo is
  "bron beschikbaar" alleen voor de gebruiker zelf geregeld; bij verspreiding aan anderen moet de bron hen ook
  bereiken (zelfde vraag als bij `jelly-leon`, ADR-0004 daar).
