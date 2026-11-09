# ADR-0005 — Submodules van upstream als geneste subtree op exact de gepinde commit

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** `git subtree` neemt submodule-inhoud niet mee. Van de vier clients gebruikt alleen jellyfin-desktop
  v2.0.0 een submodule: `external/mpvqt` → `https://invent.kde.org/libraries/mpvqt.git`, gepind op
  `2ebbd38bf65d01be9c55d673ecd43c8bb9a6fc8e` (gemeten: android, androidtv en Swiftfin hebben geen `.gitmodules`, ook
  niet op hun upstream-hoofdbranch op 2026-11-09). Na de import stond er alleen een **lege gitlink** (mode 160000) en
  geen `.gitmodules` in de root: broncode ontbrak, `-DUSE_STATIC_MPVQT=ON` kon niet bouwen, en zonder die optie faalt de
  configure op Ubuntu 24.04 omdat `debian/control` geen `libmpvqt-dev` noemt (gemeten).

## Besluit

- Elke upstream-submodule wordt een **geneste subtree (squash)** op exact de door upstream gepinde commit:
  `git rm --cached desktop/external/mpvqt` + `git subtree add --squash --prefix desktop/external/mpvqt
  https://github.com/KDE/mpvqt.git 2ebbd38…` (patch JLC-0001).
- Bron: de officiële GitHub-spiegel van KDE (`github.com/KDE/mpvqt`), omdat `invent.kde.org` in de oude
  bouwomgeving door de proxy geweigerd werd. Git-commits zijn inhoudsadressen: dezelfde hash = dezelfde inhoud. De
  oorspronkelijke URL staat in de basislijn (`upstream_repo_volgens_gitmodules`).
- **Opnieuw gemeten op de eigen machine (2026-11-09, geen proxy):** `invent.kde.org/libraries/mpvqt.git` is bereikbaar;
  commit `2ebbd38` daar opgehaald heeft tree `7d1a4c1bcc95…` (gelijk aan de basislijn en aan de spiegel) en is een
  voorouder van de huidige `master` op invent.kde.org. De spiegel blijft de bron (geen wijziging nodig; bij een
  nieuwe pin kan `upstream_sync.py --geneste-url external/mpvqt=<invent-URL>` de oorspronkelijke bron gebruiken).
- De basislijn legt per geneste subtree de commit én de tree-hash vast; `check_clients.py` eist dat (a) upstream op die
  plek een gitlink met precies die commit heeft, (b) de geneste squashcommit naar diezelfde commit verwijst en exact
  die inhoud heeft, en (c) er nergens gitlinks of een root-`.gitmodules` staan.
- Gemeten in de review (2026-11-09): de mpvqt-commit `2ebbd38` opgehaald van de GitHub-spiegel heeft tree
  `7d1a4c1bcc95…`, gelijk aan de geneste squashcommit en aan `HEAD:desktop/external/mpvqt`.
- Upstream-sync (ADR-0002): ongewijzigde pin → schone merge; gewijzigde pin → het gitlink-conflict wordt opgelost en de
  geneste subtree volgt naar de nieuwe pin; **nieuwe of verdwenen submodule → sync faalt bewust** (nieuwe code van
  derden eerst door een mens laten beoordelen).
- CI en lokale builds bouwen desktop met `-DUSE_STATIC_MPVQT=ON` (vendored bron, exact de gepinde versie).

## Gevolgen

- `desktop/.gitmodules` blijft byte-gelijk aan upstream (in een submap zonder effect).
- Gemeten: desktop-build 62/62 en `ctest` 1/1 met de vendored mpvqt (`test-evidence/p0-desktop-container-build.json`).
