# ADR-0006 — Upstream-workflows blijven staan maar zijn inert; eigen CI in de root

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** Elke client heeft eigen GitHub-workflows in `<map>/.github/workflows/` (build, test, lint, publish,
  TestFlight, stale-bot, …), vaak met upstream-geheimen (`KEYSTORE`, `JF_BOT_TOKEN`, Apple-sleutels, repo-server).
  GitHub voert alleen workflows uit `.github/workflows/` in de **root** uit.

## Besluit

- Upstream-workflows blijven ongewijzigd staan (minimale patch stack, schone syncs) en draaien **niet**; ook
  `renovate.json`, `CODEOWNERS` en `fastlane`-configuratie in submappen hebben geen effect.
- Eigen workflows in de root, met pad-filter per map:
  `clients-android.yml`, `clients-androidtv.yml` (ubuntu-24.04, JDK 21, wrapper-validatie,
  `./gradlew --max-workers=2 assembleDebug test`), `clients-desktop.yml` (ubuntu-24.04, `debian/control`,
  `-DUSE_STATIC_MPVQT=ON`, `ctest`), `clients-swiftfin.yml` (macos-26, Xcode 26.6, Brewfile, Carthage, `xcodebuild`
  voor iOS- en tvOS-simulator zonder signing), `clients-forkregels.yml` (altijd), `clients-upstream-sync.yml`.
- Acties op **commit-SHA** gepind (geverifieerd met `git ls-remote`), `permissions: contents: read` behalve de
  syncjob (`contents: write`, alleen een nieuwe `sync/*`-branch), `persist-credentials: false` bij **elke** checkout;
  de syncjob zet het token alleen in zijn pushstap (review P0).
- **Onbeoordeelde upstream-code schrijft geen cache.** De client-CI op een syncbranch draait via `workflow_call` in de
  cache-scope van de aanroepende (standaard)branch. Daarom: Gradle-cache alleen-lezen voor syncbranches en
  niet-standaardbranches (`cache-read-only`), Carthage-cache voor een syncbranch alleen lezen (`actions/cache/restore`).
- Deze regels zijn vastgezet in `tools/clients/tests/test_workflows.py` (SHA-pins, rechten, geen geheimen of
  `pull_request_target`, geen force-push/merge/tag/release/image, checkout zonder token, caches).
- Geen release-/publish-workflow in P0: geen ondertekende APK's/IPA's zonder besluit over identiteit (ADR-0004) en
  sleutelbeheer.

## Validatieniveaus

Eerst (P0, oude bouwomgeving met proxy) alleen statisch gecontroleerd; stand na de afronding van P0 (2026-11-09):

| Workflow | Lokaal (eigen machine, geen proxy) | Op GitHub (branch `ccr-c133d7a0-kuz1cv`) |
|---|---|---|
| alle | `actionlint` (met shellcheck) zonder meldingen; actie-SHA's tegen hun tags nagemeten (`git ls-remote`) | zie hieronder |
| forkregels | pytest (Sim-getest), ruff, `check_clients.py` in orde | groen (o.a. run 42620737949) |
| android | `assembleDebug test` geslaagd; upstream heeft geen unit-tests (`NO-SOURCE`) | groen (run 42608527216) |
| androidtv | `assembleDebug test` geslaagd, 15/15 unit-tests per variant | groen (run 42608527671) |
| desktop | Linux-build 62/62 + `ctest` 1/1 in een Ubuntu 24.04-container | groen (run 42600307251) |
| swiftfin | onmogelijk (geen macOS/Xcode) → **NIET GEVALIDEERD (Mac/Xcode)** | groen als simulatorbuild zonder signing (run 42608527121); app niet gestart |
| upstream-sync | Sim-getest met nep-upstreams (ook alle foutpaden) | groen, alleen het pad "geen update" (run 42620559306) |

Actuele run-ID's en wat er wel en niet mee bewezen is: `docs/platform-v2/EVIDENCE.json` en
`docs/platform-v2/BOUWVERIFICATIE_P0.md`. Geen van deze runs zegt iets over de apps op een echt apparaat
(**NIET GEVALIDEERD (hardware)**).
