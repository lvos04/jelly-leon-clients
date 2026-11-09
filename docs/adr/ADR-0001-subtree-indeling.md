# ADR-0001 — Eén repo met de vier clients als git subtree (squash)

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** B03-001 vraagt een fork met CI, GPL-naleving en upstream-review; B03-003 vraagt beschikbaarheid op
  Android, Android TV, iOS/tvOS en desktop. De gebruiker koos één repo `jelly-leon-clients` met de vier upstream-clients
  (jellyfin-android v2.7.3, jellyfin-androidtv v0.19.10, jellyfin-desktop v2.0.0, Swiftfin 1.6.1). Alternatieven:
  vier losse GitHub-forks, git-submodules, of subtrees met volledige historie.

## Besluit

- Elke client staat in een eigen map (`android/`, `androidtv/`, `desktop/`, `swiftfin/`) als
  `git subtree add --prefix <map> --squash <upstream-url> <tag>`. De squashcommit bevat exact de upstream-boom van de
  tag; de trailers `git-subtree-dir`/`git-subtree-split` leggen de upstream-commit vast.
- Alles **buiten** die mappen (`README.md`, `docs/`, `tools/`, `.github/`, `Makefile`) is fork-eigen.
- Bron van waarheid voor de basis is `tools/clients/baseline.json`; `tools/clients/check_clients.py` bewaakt dat
  basislijn en squashcommits overeenkomen (CI *Clients / Forkregels*).
- Geen submodules (zie ADR-0005), geen volledige upstream-historie in de repo.

## Waarom

- **Eén plek** voor CI, patchregister, licentie- en syncbeleid van alle clients; past bij de keuze van de gebruiker.
- **Squash** houdt de repo klein (geen ~tienduizenden upstream-commits per client) en maakt elke sync één reviewbare
  commit; upstream-historie blijft bij upstream (gelinkt via de split-commit).
- **Subtree i.p.v. submodule:** de broncode staat écht in de repo (GPL "bron beschikbaar", reproduceerbare builds,
  één `git clone`), en patches zijn gewone commits.

## Gevolgen

- `git subtree pull --squash` heeft de vorige upstream-commit nodig; in een verse clone ontbreekt die. De sync-tool haalt
  hem daarom expliciet op (ADR-0002).
- Upstream-bestanden die alleen in de upstream-root werken (o.a. `.github/workflows/`, `renovate.json`, `CODEOWNERS`)
  zijn in een submap inert (ADR-0006).
- Alle afwijkingen binnen een clientmap moeten in het patchregister (ADR-0003).
