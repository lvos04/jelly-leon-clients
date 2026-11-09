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

| Workflow | Lokaal | Op GitHub |
|---|---|---|
| alle | `actionlint` + `shellcheck` geslaagd | **nog nooit gedraaid** |
| forkregels | pytest 92/92 (48 tooling + 44 workflowregels), `check_clients.py` in orde | — |
| desktop | zelfde stappen in Ubuntu 24.04-container geslaagd | — |
| android / androidtv | geblokkeerd (Android SDK, Gradle-distributie) | — |
| swiftfin | onmogelijk (geen macOS/Xcode) → **NIET GEVALIDEERD (Mac/Xcode)** | — |
