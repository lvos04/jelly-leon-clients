# Forkstrategie Jelly Leon clients (B03-001 / B03-003 / B03-013)

Versie P0 · 2026-11-09 · repo `lvos04/jelly-leon-clients`.

Deze repo bevat de apparaat-apps van het universele mediaplatform: forks van **jellyfin-android v2.7.3**,
**jellyfin-androidtv v0.19.10**, **jellyfin-desktop v2.0.0** en **Swiftfin 1.6.1** (iOS/tvOS). Doel: zelf kunnen bouwen,
upstream bijhouden en later alleen de zichtbare naam "Jelly Leon" geven — **zonder** het Jellyfin-protocol of de
compatibiliteit met de server `jelly-leon` (Jellyfin 10.11.11) te breken. Besluiten: `docs/adr/` (ADR-0001…0009).
Inventaris per client: [`INVENTARIS.md`](INVENTARIS.md). Bouwverificatie: [`BOUWVERIFICATIE_P0.md`](BOUWVERIFICATIE_P0.md).

## 1. Indeling (ADR-0001, ADR-0005)

```
android/     ← git subtree --squash  jellyfin/jellyfin-android   v2.7.3   (GPL-2.0)
androidtv/   ← git subtree --squash  jellyfin/jellyfin-androidtv v0.19.10 (GPL-2.0)
desktop/     ← git subtree --squash  jellyfin/jellyfin-desktop   v2.0.0   (GPL-2.0)
  external/mpvqt/ ← geneste subtree  KDE MpvQt 2ebbd38 (door upstream gepinde submodule, LGPL)
swiftfin/    ← git subtree --squash  jellyfin/Swiftfin           1.6.1    (MPL-2.0)
tools/clients/  fork-tooling (basislijn, forkregels, upstream-sync, bouwverificatie, tests)
.github/workflows/clients-*.yml  eigen CI (upstream-workflows in de submappen draaien niet)
docs/        ADR's, inventaris, patchregister, bewijs
```

- Basislijn per client in `tools/clients/baseline.json` (tag, upstream-commit, tree-hash van die commit, tagpatroon,
  forkversie, licentie, beschermde bestanden, geneste subtrees). `check_clients.py` eist dat elke squashcommit exact
  die upstream-inhoud heeft (review P0: in de bouwomgeving tegen upstream nagemeten, alle vijf gelijk).
- **Submodules:** `git subtree` neemt submodule-inhoud niet mee. Alleen desktop heeft er één (`external/mpvqt`); die is
  als geneste subtree op exact de upstream-pin toegevoegd (JLC-0001). Elke nieuwe upstream-submodule laat de sync
  bewust falen.

## 2. Upstream-sync per client (ADR-0002, B03-013, EX48)

```
python3 tools/clients/upstream_sync.py status                 # actueel | update_beschikbaar | unknown
python3 tools/clients/upstream_sync.py sync android           # nieuwste stabiele tag
python3 tools/clients/upstream_sync.py sync desktop --tag v2.0.1
```

`sync` = `git subtree pull --prefix <map> --squash <upstream-url> <tag>` in branch **`sync/<client>-<tag>`**, met:
vorige upstream-commit ophalen (verse clone), gewijzigde mpvqt-pin volgen, basislijn bijwerken, forkregels controleren.
Conflict, nieuwe/verdwenen submodule of geschonden forkregel → alles terug en exitcode 2; niets gepusht.
Workflow `Clients / Upstream-sync` doet dit wekelijks en handmatig, pusht alleen de syncbranch (token alleen in de
pushstap) en draait daarop forkregels + client-CI met alleen leesrechten en zonder schrijfbare cache.
**Overnemen in de hoofdbranch en elke release zijn handmatige R2-stappen.**

Stand 2026-11-09: alle vier clients staan op de nieuwste stabiele upstream-tag (`status` → `actueel`). Syncproef op
echte code: desktop v2.0.0 → upstream master (214 commits) schoon in een verse clone.

## 3. Patchregister (ADR-0003)

Elke afwijking binnen een clientmap staat in [`PATCHES.md`](PATCHES.md) (`JLC-<nnnn>`); `check_clients.py` faalt op
niet-geregistreerde of verouderde registraties en op elke wijziging van licentie-/creditbestanden.
Stand P0: **één** patch (JLC-0001, mpvqt-bron; geen codewijziging). Appcode: geen patches.

## 4. Branding en app-identiteit (ADR-0004)

- Technische identiteit blijft "Jellyfin" (clientnaam in de `Authorization`-header, apparaatprofielen, API-gedrag).
- Alleen de **zichtbare** naam wordt later "Jelly Leon" — eerst via build-configuratie, anders als geregistreerde patch.
  Bij android en desktop komt het meeste zichtbare uit de web-client van de server (`jelly-leon-web`).
- **In P0 is niets aan branding gewijzigd.**
- **Besluit gebruiker (2026-11-09) — app-identiteit:** eigen `applicationId` voor Android en Android TV, naast de
  officiële app installeerbaar; eigen bundle-id voor iOS (NIET GEVALIDEERD (Mac/Xcode)). De patch volgt in **P4** als
  geregistreerde patch (android: `applicationId` + back-upregels; androidtv daarnaast `app_id`,
  `app_search_suggest_authority` en `app_search_suggest_intent_data`, die upstream uit `namespace` afleidt). Patchplan
  en voorstel voor de waarde: ADR-0004. **Tot P4 blijft elke ID upstream.**

## 5. Licenties (ADR-0007)

GPL-2.0 (android, androidtv, desktop), MPL-2.0 (Swiftfin), LGPL (mpvqt). Licentie- en creditbestanden blijven
byte-gelijk (CI-controle); wijzigingen herkenbaar via `PATCHES.md`; bij elke verspreide build hoort de exacte bron
(commit van deze repo). Open besluit: zichtbaarheid van de repo vóór verspreiding aan anderen.

## 6. Versieschema

Forkversie per client `<upstream-versie>-jl.<N>`; nu `2.7.3-jl.0`, `0.19.10-jl.0`, `2.0.0-jl.0`, `1.6.1-jl.0`
(ontwikkelstand, nooit gepubliceerd). Bij een sync wordt `N` weer `0`. De apps zelf melden in P0 hun upstream-versie;
de forkversie staat in de basislijn (en later in release-metadata).

## 7. Bouwen en testen (ADR-0006)

| Client | CI-workflow | Lokaal (2026-11-09) | Validatie |
|---|---|---|---|
| android | `clients-android.yml` (JDK 21, `assembleDebug test`) | **gebouwd** (`make android-bouw`); upstream heeft geen unit-tests (`NO-SOURCE`); CI groen | alleen gebouwd (compileren + verpakken; geen tests om te draaien); app-gebruik NIET GEVALIDEERD (hardware) |
| androidtv | `clients-androidtv.yml` (JDK 21, `assembleDebug test`) | **gebouwd** (`make androidtv-bouw`), 15/15 tests per variant; CI groen | Unit-getest; app-gebruik NIET GEVALIDEERD (hardware) |
| desktop | `clients-desktop.yml` (Ubuntu 24.04, `ctest`) | **gebouwd**, ctest 1/1 (container, `make desktop-bouw`); CI groen | Unit-getest (Linux); app-gebruik NIET GEVALIDEERD (hardware) |
| swiftfin | `clients-swiftfin.yml` (macOS 26, Xcode 26.6, simulator) | onmogelijk (geen Mac); CI-simulatorbuild zonder signing groen | NIET GEVALIDEERD (Mac/Xcode) |
| fork-tooling | `clients-forkregels.yml` | 115/115 tests (58 tooling + 44 workflowregels + 5 bouwcontainer- + 8 EVIDENCE-regels), forkregels in orde, actionlint/shellcheck | Sim-getest |

Lokale zware builds op een gedeelde machine: `GRADLE_LOCK=<bestand>` / `DOCKER_LOCK=<bestand>` laten `make` de stap
onder `flock` draaien (standaard `--max-workers=4`, Gradle-heap 2 GiB).

## 8. Servercompatibiliteit

Android en Android TV (SDK 1.7.1, API 10.10.7) en desktop (web-client van de server) passen bij Jelly Leon 10.11.11.
**Swiftfin 1.6.1 verwacht Jellyfin 12.0** (SDK 3.0.0) en toont tegen 10.11 een updatewaarschuwing. **Besluit
gebruiker (2026-11-09, ADR-0009):** Swiftfin 1.6.1 blijft; de server gaat vóór P4 in een aparte fase naar de nieuwste
stabiele Jellyfin 12.x (.NET 10); dan worden de Android-clients op 12.x-compatibiliteit gecontroleerd
(`tools/clients/server_api_compat.py` + tests tegen een 12.x-server). Niets is op een echt apparaat getest; de matrix in [`INVENTARIS.md`](INVENTARIS.md) §3 staat volledig op
NIET GEVALIDEERD tot een echte sessie (inloggen, afspelen, ondertitel, hervatten) per apparaat uit D15.

## 9. Installatie en distributie (ADR-0008)

De clients zijn **geen TrueNAS-apps**: geen image, Custom App, manifest of compose. Hoe APK's/IPA's/installers op de
apparaten komen (release-artefacten, downloadpagina via de Hub/`jelly-leon`, sideloaden) is een later
gebruikersbesluit, ná het besluit over app-identiteit en ondertekening. De officiële Jellyfin-apps blijven tot dan de
apps in gebruik (I24 stap 6: oude player blijft intact).
