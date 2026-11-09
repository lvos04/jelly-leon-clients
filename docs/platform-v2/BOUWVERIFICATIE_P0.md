# Bouwverificatie P0 — jelly-leon-clients (2026-11-09)

Omgeving: gedeelde Linux-bouwomgeving (4 CPU's, 15 GB RAM), Docker, Python 3.12, JDK 21, uitgaand verkeer via een
beleidsproxy. Geen macOS/Xcode, geen Android-apparaat, geen tv, geen NAS. Alles hieronder is echt uitgevoerd; wat niet
kon staat als blokkade.

## 1. Forkregels en tooling (Sim-getest)

| Commando | Resultaat |
|---|---|
| `.venv/bin/pytest -q tools/clients/tests` | **39 passed** (nep-upstreams: schone sync, EX48-conflict, overgenomen patch, nieuwe/verdwenen submodule, gewijzigde mpvqt-pin, verse CI-clone, registerregels) |
| `.venv/bin/ruff check --config tools/clients/ruff.toml tools/clients` | All checks passed |
| `python3 tools/clients/check_clients.py` | in orde; afwijkingen van upstream: android 0, androidtv 0, desktop 1 (JLC-0001), swiftfin 0 |
| `python3 tools/clients/check_clients.py --ref 600830428` (stand vóór de mpvqt-fix) | 2 overtredingen: gitlink `desktop/external/mpvqt` en ontbrekende geneste subtree — de controle vangt het oorspronkelijke probleem |
| `python3 tools/clients/upstream_sync.py status` | alle vier `actueel` (v2.7.3, v0.19.10, v2.0.0, 1.6.1) |
| `actionlint .github/workflows/*.yml` (met shellcheck 0.11.0) | geen meldingen |

## 2. Upstream-basis gecontroleerd

`git ls-remote` op 2026-11-09: de `git-subtree-split`-commits van alle vier imports zijn exact de upstream-tags
(`v2.7.3` → `9a5f9be6`, `v0.19.10` → `984181a3`, `v2.0.0` → `1634d3d2`, `1.6.1^{}` → `5b794d2b`). Upstream-hoofdbranches
van android, androidtv en Swiftfin hebben geen submodules; desktop-master pint mpvqt nog steeds op `2ebbd38`.

## 3. Desktop — gebouwd in een container (Linux)

Bewijs: [`test-evidence/p0-desktop-container-build.json`](test-evidence/p0-desktop-container-build.json).

```
docker build --network host --build-arg HTTPS_PROXY --secret id=ca_bundle,src=<ca> \
  -f tools/clients/bouwverificatie/desktop.Dockerfile -t jelly-leon-clients/desktop-bouw:dev desktop/
nice -n 10 tools/clients/bouwverificatie/desktop_bouw.sh
```

- Ubuntu 24.04 (`@sha256:fe81560990fa…`), GCC 13.3, CMake 3.28, Qt 6.4.2, libmpv 0.37, mpvqt uit de vendored subtree.
- **62/62 bouwstappen, `ctest` 1/1 geslaagd**; compile zonder netwerk, 2 CPU's, uid 568, zonder capabilities.
- Zonder `-DUSE_STATIC_MPVQT=ON` (recept van upstream `test.yml`) faalt de configure: `MpvQtConfig.cmake` niet gevonden.
- Eerste poging van de bouwimage faalde (apt-gebruiker `_apt` kon de CA-secret niet lezen); opgelost met een tijdelijke
  leesbare kopie binnen dezelfde stap (komt niet in een laag).
- **Niet gedaan:** de app starten, inloggen of afspelen (geen scherm/server) → NIET GEVALIDEERD (hardware);
  Windows/macOS-builds; Debian-pakket; Flatpak.

## 4. Android en Android TV — geblokkeerd

Bewijs: [`test-evidence/p0-android-bouwpoging.json`](test-evidence/p0-android-bouwpoging.json).

- `dl.google.com` (Android SDK command-line tools, platforms, build-tools) → proxy weigert (403, policy).
- `services.gradle.org` stuurt door naar `downloads.gradle.org` → proxy weigert (403). De wrappers vragen Gradle
  9.6.1 (android) en 9.1.0 (androidtv); lokaal staat alleen 8.14.3, ongeschikt voor AGP 9.3.1.
- Niet omzeild via andere bronnen (proxybeleid). **Blocker**: de builds draaien alleen in GitHub Actions
  (`clients-android.yml`, `clients-androidtv.yml`); tot een groene run daar NIET GEVALIDEERD.

## 5. Swiftfin — niet uitvoerbaar

Geen macOS/Xcode in deze omgeving. `clients-swiftfin.yml` (macos-26, Xcode 26.6, Carthage, `xcodebuild` voor iOS- en
tvOS-simulator zonder signing) is alleen statisch gecontroleerd (actionlint). **NIET GEVALIDEERD (Mac/Xcode).**

## 6. Syncproef op echte upstream-code

Bewijs: [`test-evidence/p0-syncproef-desktop-master.json`](test-evidence/p0-syncproef-desktop-master.json).
desktop v2.0.0 → jellyfin-desktop master `3fa72e5` (214 commits verder, lokaal getagd als proeftag `v2.0.1`) in een
verse `git clone --no-local`: exitcode 0, branch `sync/desktop-v2.0.1`, mpvqt-pin ongewijzigd, forkregels in orde.
Niets gepusht; wegwerpclone verwijderd. De gesynchroniseerde code is niet gebouwd.

## 7. Opruimen

Bouwmap `.bouw/` (genegeerd door git) en de bouwimage `jelly-leon-clients/desktop-bouw:dev` worden na de verificatie
verwijderd (`docker image rm`, `docker image prune -f`); de image is reproduceerbaar uit de Dockerfile.

## 8. Onafhankelijke review (QA), 2026-11-09

Bewijs: [`test-evidence/p0-review-qa.json`](test-evidence/p0-review-qa.json). Alles opnieuw uitgevoerd in dezelfde
bouwomgeving; wat niet kon staat er als niet gedaan.

| Controle | Resultaat |
|---|---|
| Inhoud subtrees tegen upstream (tags/commit opgehaald, tree-hashes vergeleken) | android, androidtv, desktop, swiftfin en mpvqt **byte-gelijk** aan upstream; desktop wijkt alleen af in `external/mpvqt` (JLC-0001) |
| Gepinde actie-SHA's tegen hun tags (`git ls-remote`) | alle gelijk |
| Base-digest `ubuntu:24.04` (`docker buildx imagetools inspect`) | gelijk aan `desktop.Dockerfile` |
| Desktop opnieuw gebouwd (bouwimage-lagen uit BuildKit-cache, compile vers) | 62/62 stappen, `ctest` 1/1 |
| Syncproef met de nieuwe tooling (desktop v2.0.0 → upstream master, verse clone) | exit 0, `upstream_tree` gelijk aan upstream, forkregels in orde, 92/92 tests op de syncbranch; niets gepusht |
| Android-blokkade nagemeten | `dl.google.com` en `downloads.gradle.org`: 403 via de proxy → blijft **Geblokkeerd** |
| Tests vóór / na de reparaties | 39 → **92 passed** (48 tooling + 44 workflowregels); ruff en actionlint zonder meldingen |

**Gevonden en gerepareerd** (zie de review-commits):

1. De forkregels vertrouwden alleen de trailer `git-subtree-split`; een commit met de juiste trailer en andere inhoud
   werd als upstream-basis geaccepteerd. Nu: `upstream_tree` in de basislijn en tree-controle van elke squashcommit.
2. `check_clients.py --ref` las basislijn en register uit de werkboom; nu uit de gecontroleerde commit (terugval op de
   werkboom alleen als ze daar ontbreken, en dan gemeld). De meting `--ref 600830428` hierboven gebruikt daarom de
   basislijn uit de werkboom (die bestond in die commit nog niet).
3. Beschermde licentiebestanden moesten alleen ongewijzigd zijn; nu moeten ze ook bestaan.
4. `upstream_sync.py` draaide alleen bij verwachte fouten terug; nu bij elke fout.
5. Sync-workflow: token niet meer in de git-config tijdens de sync; pushen alleen als de syncbranch aantoonbaar niet
   bestaat.
6. Client-CI op een syncbranch kon de Gradle-/Carthage-cache van de standaardbranch vullen met nog niet beoordeelde
   upstream-code; nu alleen-lezen.

**Blijft open (niet te repareren in deze omgeving):** Android/Android TV-build (proxy), Swiftfin
(**NIET GEVALIDEERD (Mac/Xcode)**), geen enkele workflow op GitHub gedraaid, niets op echte apparaten
(**NIET GEVALIDEERD (hardware)**). De door `git subtree` zelf gemaakte squashcommits (o.a. `b7cc2782c`) dragen niet de
twee vaste afsluitregels van §12; dat is inherent aan `git subtree` en is zonder history-herschrijving (force-push)
niet te herstellen.
