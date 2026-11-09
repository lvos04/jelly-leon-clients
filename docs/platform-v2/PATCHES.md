# Patchregister Jelly Leon clients (afwijkingen van upstream in `android/`, `androidtv/`, `desktop/`, `swiftfin/`)

Elke afwijking van de upstream-basis **binnen een clientmap** — gewijzigd, toegevoegd of verwijderd bestand, ook een
vervangen submodule-gitlink — is een patch en moet hier staan (ADR-0003). De basis per client is de jongste
subtree-squashcommit, die exact de upstream-tag uit `tools/clients/baseline.json` bevat.
`tools/clients/check_clients.py` controleert dat in CI (workflow *Clients / Forkregels*):

- een niet-geregistreerde afwijking → CI faalt;
- een geregistreerd bestand dat niet (meer) afwijkt → CI faalt (register verouderd, bv. na upstream-acceptatie);
- beschermde bestanden (licenties en credits: `android/LICENSE.md`, `androidtv/LICENSE`, `androidtv/CONTRIBUTORS.md`,
  `desktop/LICENSE`, `swiftfin/LICENSE.md`, de LGPL-teksten van mpvqt) mogen **nooit** afwijken of ontbreken;
- het register en de basislijn worden gelezen uit de gecontroleerde commit (een niet-gecommitte registratie telt niet);
- geen gitlinks/submodules: die zou `git subtree` leeg laten (ADR-0005).

Alles **buiten** de vier clientmappen (`README.md`, `docs/`, `tools/`, `.github/`, `Makefile`) is fork-eigen en
hoort niet in dit register.

**Vorm per patch** (de checker leest deze tabelvelden): `Status` ∈ `actief` | `upstream-aangeboden` | `vervallen`;
`Client` = sleutel uit de basislijn; `Bestanden` met elk pad (vanaf de repo-root) tussen backticks — een pad dat op
`/` eindigt dekt een hele map; verplicht ook `Doel`, `Waarom nodig`, `Upstream-PR-kans` en `Test`.

**Volgorde vóór een patch:** configuratie of build-optie → serverkant (Jelly Leon-plugin of web-client) → pas dan
een patch in de client. Branding is in P0 bewust **niet** gewijzigd (ADR-0004).

| ID | Titel | Client | Soort | Status |
|---|---|---|---|---|
| JLC-0001 | Submodule `external/mpvqt` als geneste subtree | desktop | bronvolledigheid (geen codewijziging) | actief |

Appcode (Kotlin, C++, Swift): **geen** patches in P0.

## JLC-0001 — Submodule `external/mpvqt` als geneste subtree

| Veld | Waarde |
|---|---|
| Status | actief |
| Client | desktop |
| Soort | bronvolledigheid: lege submodule-gitlink vervangen door de broncode van exact de gepinde commit; geen wijziging aan code van jellyfin-desktop of mpvqt |
| Sinds | 2026-11-09 (forkversie 2.0.0-jl.0) |
| Doel | jellyfin-desktop v2.0.0 pint `external/mpvqt` als git-submodule op `2ebbd38bf65d01be9c55d673ecd43c8bb9a6fc8e` (KDE MpvQt, `v1.1.1-1-g2ebbd38`). Bij de subtree-import bleef alleen een lege gitlink over: broncode ontbrak, `-DUSE_STATIC_MPVQT=ON` kon niet bouwen en de LGPL-bron van een meegeleverde bibliotheek was niet in de fork aanwezig. |
| Bestanden | `desktop/external/mpvqt` |
| Wijziging | gitlink (mode 160000) verwijderd; `git subtree add --squash --prefix desktop/external/mpvqt https://github.com/KDE/mpvqt.git 2ebbd38…` (officiële GitHub-spiegel van `invent.kde.org/libraries/mpvqt`, dezelfde commit-hash). `desktop/.gitmodules` blijft byte-gelijk aan upstream (in een submap heeft het geen effect). |
| Waarom nodig | Zonder deze bron is de desktop-client niet reproduceerbaar te bouwen op systemen zonder `libmpvqt-dev` en is de fork niet bronvolledig (GPL-2.0/LGPL). Een git-submodule in de root zou de subtree-indeling (ADR-0001) doorbreken. |
| Upstream-PR-kans | n.v.t. — upstream gebruikt bewust een submodule. |
| Test | `tools/clients/check_clients.py`: upstream-gitlink == geneste basislijn-commit, geneste squashcommit == dezelfde commit en dezelfde inhoud (`upstream_tree` `7d1a4c1bcc95…`, in de review tegen de bron nagemeten); `tools/clients/tests/test_check_clients.py` en `test_upstream_sync.py` (gitlink-pin gelijk/gewijzigd/nieuw); lokale container-build met `-DUSE_STATIC_MPVQT=ON` (zie `BOUWVERIFICATIE_P0.md`). |
| Bij upstream-sync | Ongewijzigde pin → schone merge. Gewijzigde pin → `upstream_sync.py` lost het gitlink-conflict op en zet de geneste subtree op de nieuwe pin. Nieuwe submodule → sync faalt bewust (handmatig beoordelen). |
