# Bouwverificatie P0 — jelly-leon-clients (2026-11-09)

Omgeving §1–§8: gedeelde Linux-bouwomgeving (4 CPU's, 15 GB RAM), Docker, Python 3.12, JDK 21, uitgaand verkeer via
een beleidsproxy (bestaat niet meer). §9–§10: afronding en review op de eigen Ubuntu 26.04-machine van de gebruiker
(geen proxy, geen eigen CA). Nergens macOS/Xcode, een
Android-apparaat, een tv of een NAS. Alles hieronder is echt uitgevoerd; wat niet kon staat als blokkade.

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

Toen gebouwd in de oude omgeving via de beleidsproxy (met een tijdelijke CA-secret). Die proxy en CA bestaan niet meer;
het huidige commando (zonder proxy, zonder hostnetwerk, zonder CA) is:

```
make desktop-bouw DOCKER_LOCK=<lockbestand>   # = docker buildx build --load … desktop.Dockerfile + desktop_bouw.sh
```

- Ubuntu 24.04 (`@sha256:fe81560990fa…`), GCC 13.3, CMake 3.28, Qt 6.4.2, libmpv 0.37, mpvqt uit de vendored subtree.
- **62/62 bouwstappen, `ctest` 1/1 geslaagd**; compile zonder netwerk, 2 CPU's, uid 568, zonder capabilities.
- Zonder `-DUSE_STATIC_MPVQT=ON` (recept van upstream `test.yml`) faalt de configure: `MpvQtConfig.cmake` niet gevonden.
- Eerste poging van de bouwimage faalde (apt-gebruiker `_apt` kon de CA-secret niet lezen); opgelost met een tijdelijke
  leesbare kopie binnen dezelfde stap (komt niet in een laag).
- **Niet gedaan:** de app starten, inloggen of afspelen (geen scherm/server) → NIET GEVALIDEERD (hardware);
  Windows/macOS-builds; Debian-pakket; Flatpak.

## 4. Android en Android TV — in de oude omgeving geblokkeerd (opgelost in §9)

Bewijs: [`test-evidence/p0-android-bouwpoging.json`](test-evidence/p0-android-bouwpoging.json).

- `dl.google.com` (Android SDK command-line tools, platforms, build-tools) → proxy weigert (403, policy).
- `services.gradle.org` stuurt door naar `downloads.gradle.org` → proxy weigert (403). De wrappers vragen Gradle
  9.6.1 (android) en 9.1.0 (androidtv); lokaal staat alleen 8.14.3, ongeschikt voor AGP 9.3.1.
- Niet omzeild via andere bronnen (proxybeleid). Toen: builds alleen in GitHub Actions. **Stand nu:** lokaal gebouwd
  en getest (§9) en groen op GitHub.

## 5. Swiftfin — niet uitvoerbaar

Geen macOS/Xcode in deze omgeving. `clients-swiftfin.yml` (macos-26, Xcode 26.6, Carthage, `xcodebuild` voor iOS- en
tvOS-simulator zonder signing) was in P0 alleen statisch gecontroleerd (actionlint); inmiddels is de workflow op een
GitHub-macOS-runner groen (§9). Dat is een simulatorbuild zonder signing: de app is niet gestart, niet getest en niet
op een apparaat gezet. **NIET GEVALIDEERD (Mac/Xcode).**

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

**Bleef toen open:** Android/Android TV-build (proxy) en de eerste GitHub-runs — beide inmiddels gedaan (§9).
**Blijft open:** Swiftfin (**NIET GEVALIDEERD (Mac/Xcode)**), niets op echte apparaten (**NIET GEVALIDEERD
(hardware)**). De door `git subtree` zelf gemaakte squashcommits (o.a. `b7cc2782c`) dragen niet de
twee vaste afsluitregels van §12; dat is inherent aan `git subtree` en is zonder history-herschrijving (force-push)
niet te herstellen.

## 9. Afronding P0 op de eigen machine van de gebruiker (2026-11-09)

Bewijs: [`test-evidence/p0-afronding-lokale-bouw.json`](test-evidence/p0-afronding-lokale-bouw.json). Ubuntu 26.04.1,
JDK 21.0.12, Android SDK in `~/android-sdk` (platform 36, build-tools 36.0.0; niets extra nodig), Docker 29; geen proxy.
Zware stappen één tegelijk, onder `flock` met de andere bouwers op de machine, `nice -n 10`.

| Stap | Commando (kort) | Resultaat |
|---|---|---|
| Gradle-wrappers | `sha256sum gradle-wrapper.jar` ↔ `services.gradle.org/…-wrapper.jar.sha256` | android (9.6.1) en androidtv (9.1.0): jar en `distributionSha256Sum` gelijk aan gradle.org |
| android | `make android-bouw` ≙ `./gradlew --no-daemon --max-workers=4 -Dorg.gradle.jvmargs=-Xmx2g assembleDebug test` | **BUILD SUCCESSFUL** (3 min); 2 debug-APK's (`libre`, `proprietary`), pakket `org.jellyfin.mobile.debug`, minSdk 21/targetSdk 36; unit-tests `NO-SOURCE` (upstream heeft er geen) |
| androidtv | `make androidtv-bouw` (idem) | **BUILD SUCCESSFUL** (2 min 48 s); 15/15 tests in `testDebugUnitTest` én 15/15 in `testReleaseUnitTest`; debug-APK `org.jellyfin.androidtv.debug`, `app_id`/zoek-authority consistent |
| desktop | `docker buildx build … desktop.Dockerfile` + `JOBS=4 desktop_bouw.sh` | bouwimage op base-digest `fe81560990fa…` (nagemeten), **62/62** stappen, 0 compilerwaarschuwingen, **ctest 1/1**; binary even groot als in P0 |
| `make androidtv-bouw` (tweede keer) | controle van het nieuwe make-doel | 317 taken up-to-date, exit 0; zonder `ANDROID_HOME` exit 2 met melding |
| fork-tooling | `pytest -q tools/clients/tests`, `ruff`, `actionlint`, `check_clients.py` | **99 passed** (92 + 7 voor `server_api_compat.py`), geen meldingen, forkregels in orde |

**GitHub Actions** (branch `ccr-c133d7a0-kuz1cv`, vóór deze ronde al gedraaid, nu nagekeken): Clients / Android
`42608527216`, Android TV `42608527671`, Swiftfin `42608527121` (iOS- en tvOS-simulatorbuild zonder signing),
Forkregels `42608527247` — alle groen op commit `f9daf172`; Desktop `42600307251` groen op `92373ce9`. Deze ronde:
Forkregels `42620416191` groen op `5ee6d91` (99 passed) en een handmatig gestarte **Clients / Upstream-sync**
`42620559306` (client `alle`): groen, alle vier `actueel`, geen syncbranch gepusht — het eerste echte draaien van de
sync-workflow (alleen het pad zonder update; de foutpaden blijven Sim-getest). Overige runs in `EVIDENCE.json`.

**12.x-voorbereiding (ADR-0009):** statische routevergelijking server v10.11.11 ↔ v12.4 tegen de endpoints van
jellyfin-sdk-kotlin 1.7.1 — 6 routes weg, geen ervan door android/androidtv gebruikt
([`test-evidence/p0-server-12x-routevergelijking.json`](test-evidence/p0-server-12x-routevergelijking.json)); dit is
geen compatibiliteitsbewijs.

**Niet gedaan:** APK's installeren of starten (geen apparaat/emulator), desktop-app starten, Windows/macOS-builds,
release-builds of ondertekening, iets publiceren. Swiftfin lokaal: **NIET GEVALIDEERD (Mac/Xcode)**; gebruik op
apparaten: **NIET GEVALIDEERD (hardware)**. Bouwmappen en bouwimage na afloop verwijderd (`make opruimen`).

## 10. Onafhankelijke review van de P0-afronding (2026-11-09)

Bewijs: [`test-evidence/p0-afronding-review-qa.json`](test-evidence/p0-afronding-review-qa.json). Opnieuw uitgevoerd
op dezelfde machine, onder dezelfde locks, één zware build tegelijk.

| Controle | Resultaat |
|---|---|
| Forkregels zoals de CI (verse venv) | ruff en actionlint zonder meldingen, 99 passed, forkregels in orde; na de reparaties **115 passed** |
| androidtv `assembleDebug test` | BUILD SUCCESSFUL; 15/15 per variant (JUnit-XML); debug-APK **byte-gelijk** aan §9 |
| android `make android-bouw` | BUILD SUCCESSFUL; tests `NO-SOURCE`; beide debug-APK's **byte-gelijk** aan §9 |
| desktop `make desktop-bouw` (nieuw: zonder proxy en hostnetwerk) | 62/62, 0 waarschuwingen, `ctest` 1/1; binary-sha256 gelijk aan §9 |
| Digests en pins | `ubuntu:24.04` en `docker/dockerfile:1.7.1` nagemeten; alle actie-SHA's gelijk aan hun tag |
| `invent.kde.org` (was geblokkeerd) | bereikbaar; mpvqt `2ebbd38` heeft daar dezelfde tree als de basislijn |
| Laatste GitHub-run per workflow | alle groen; op commit `14e591d` opnieuw: Forkregels `42622191685` en Swiftfin `42622191631` (simulatorbuild zonder signing) groen |

**Gevonden en gerepareerd:** (1) Dockerfile-frontend `docker/dockerfile:1.7` zonder digest → `1.7.1@sha256:…`;
(2) proxyrestanten in de Makefile (`--network host --build-arg HTTPS_PROXY`) en in de gebruikstekst → weg (JC4);
(3) drie ontbrekende negatieve sync-tests (bron van een geneste subtree onbereikbaar ná een opgelost gitlink-conflict,
ophalen faalt na `ls-remote`, time-out van `ls-remote`); (4) bouwcontainer- en EVIDENCE-regels (§11) nu als tests;
(5) verouderde teksten in `clients-swiftfin.yml`, ADR-0002, ADR-0005, ADR-0006 en `FORK_STRATEGIE.md` (android was
"Unit-getest" zonder tests); (6) ADR-0008 kreeg een toetsing per contractparagraaf.

**Blijft open:** niets op een apparaat (**NIET GEVALIDEERD (hardware)**), Swiftfin lokaal **NIET GEVALIDEERD
(Mac/Xcode)**, een echte sync met een nieuwe upstream-tag op GitHub (foutpaden alleen Sim-getest), de historiescan.
