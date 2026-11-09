# ADR-0007 — Licenties, credits en bronbeschikbaarheid

- **Status:** Aanvaard (P0, 2026-11-09); zichtbaarheid **besloten door de gebruiker** (2026-11-09, STATUS.md besluit 3), nog niet uitgevoerd
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

## Zichtbaarheid (besluit gebruiker 2026-11-09)

- Alle repos en GHCR-images worden **publiek**, maar pas **na een scan van de volledige historie** op geheimen en
  privégegevens; bevindingen gaan eerst naar de gebruiker. Daarmee is "bron beschikbaar" ook voor anderen geregeld.
- Stand 2026-11-09: `lvos04/jelly-leon-clients` is nog **privé**; scan en omzetting zijn een aparte, programmabrede
  stap en zijn in deze ronde niet uitgevoerd. Tot dan geen verspreiding van eigen builds buiten het eigen huishouden.
- Voor deze repo betekent "volledige historie" ook de geïmporteerde upstream-squashcommits (vier clients + mpvqt).
