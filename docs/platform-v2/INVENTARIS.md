# Inventaris clients (B03-001 / B03-003, fase P0)

Peildatum 2026-11-09 · repo `lvos04/jelly-leon-clients` · branch `ccr-c133d7a0-kuz1cv`.
Alle gegevens hieronder zijn **gelezen uit de broncode in deze repo** of **gemeten** (aangegeven). Niets is op een echt
apparaat getest; daarvoor is D15 (welke tv's, telefoons, Apple TV, Android TV in huis) nodig.

## 1. Upstream-basis (gemeten met `git ls-remote`, 2026-11-09)

| Map | Upstream | Tag | Upstream-commit = `git-subtree-split` | Nieuwste stabiele tag upstream | Licentie |
|---|---|---|---|---|---|
| `android/` | `jellyfin/jellyfin-android` | `v2.7.3` | `9a5f9be6a76d…` | `v2.7.3` (actueel) | GPL-2.0 (`LICENSE.md`) |
| `androidtv/` | `jellyfin/jellyfin-androidtv` | `v0.19.10` | `984181a3d6ab…` | `v0.19.10` (actueel) | GPL-2.0 (`LICENSE`, `CONTRIBUTORS.md`) |
| `desktop/` | `jellyfin/jellyfin-desktop` | `v2.0.0` | `1634d3d263b8…` | `v2.0.0` (actueel) | GPL-2.0 (`LICENSE`) |
| `desktop/external/mpvqt/` | KDE MpvQt (submodule van desktop) | — | `2ebbd38bf65d…` (`v1.1.1-1-g2ebbd38`) | door upstream desktop gepind | LGPL-2.1-only/LGPL-3.0-only |
| `swiftfin/` | `jellyfin/Swiftfin` | `1.6.1` (zonder `v`) | `5b794d2b7d4b…` | `1.6.1` (actueel) | MPL-2.0 (`LICENSE.md`) |

Elke import is een `git subtree add --squash`; de squashcommit bevat exact de upstream-boom van de tag: in de review
nagemeten (upstream-tag opgehaald, tree-hashes gelijk, `test-evidence/p0-review-qa.json`) en sindsdien bewaakt door
`tools/clients/check_clients.py` (`upstream_tree` in de basislijn). Bron van waarheid: `tools/clients/baseline.json`.

## 2. Per client

### 2.1 `android/` — Jellyfin Android 2.7.3 (telefoon/tablet)

| Onderwerp | Waarde (bron) |
|---|---|
| Soort app | WebView-schil om de **web-client van de server** (`WebViewFragment` laadt `<server>/`) + native speler (AndroidX Media3/ExoPlayer), downloads, Chromecast (alleen *proprietary*). Wat de gebruiker ziet is grotendeels `jelly-leon-web`. |
| Taal / build | Kotlin (+ wat Java), Gradle-wrapper **9.6.1** (`distributionSha256Sum` vastgezet), Android Gradle Plugin **9.3.1**, Kotlin **2.4.10**, KSP, Compose, Room, Koin (`gradle/libs.versions.toml`) |
| Toolchain | JDK **21** (`.tools-versions`), bytecode-doel Java 11 met desugaring |
| SDK | `compileSdk` 36, `targetSdk` 36, **`minSdk` 21** (Android 5.0) |
| Varianten | flavors `libre` (zonder Google-diensten) en `proprietary` (standaard; Google Cast + Play Services); build types `debug` (`.debug`-suffix) en `release` (minify, ondertekening via `KEYSTORE_*`-variabelen) |
| Identiteit | `applicationId` = `namespace` = **`org.jellyfin.mobile`** (debug: `org.jellyfin.mobile.debug`); appnaam `Jellyfin` (`strings_donottranslate.xml`) |
| Server-API | jellyfin-sdk-kotlin **1.7.1**: API gegenereerd tegen server **10.10.7**, minimum **10.10.0** → past bij Jelly Leon 10.11.11 |
| Tests | **geen** unit- of instrumentatietests in v2.7.3 (geen `src/test`, `src/androidTest`); gemeten: `testLibreDebugUnitTest` en `testProprietaryDebugUnitTest` zijn `NO-SOURCE` (testframeworks JUnit 6/Kotest/MockK zijn wel geconfigureerd). Upstream-CI: build, test, lint+detekt, wrapper-validatie. |
| Submodules | geen |
| Lokaal gebouwd? | **Ja (2026-11-09, Ubuntu 26.04, JDK 21.0.12, Android SDK platform 36 + build-tools 36.0.0)**: `./gradlew --no-daemon --max-workers=4 assembleDebug test` → BUILD SUCCESSFUL; 2 debug-APK's (`libre`, `proprietary`), pakket `org.jellyfin.mobile.debug`, minSdk 21, targetSdk 36 (`aapt2`). Ook groen op GitHub (run 42608527216). Niet geïnstalleerd/gestart (geen apparaat/emulator) → gebruik NIET GEVALIDEERD (hardware). Bewijs: `test-evidence/p0-afronding-lokale-bouw.json` (de eerdere blokkade: `p0-android-bouwpoging.json`). |

### 2.2 `androidtv/` — Jellyfin Android TV 0.19.10 (Android TV / Google TV / Fire TV)

| Onderwerp | Waarde (bron) |
|---|---|
| Soort app | **Native** tv-app (Leanback + Compose), eigen speler (Media3), praat rechtstreeks met de server-API via de SDK; geen web-client |
| Taal / build | Kotlin, Gradle-wrapper **9.1.0** (sha256 vastgezet), AGP **8.11.1**, Kotlin **2.2.21**; modules `app`, `playback:{core,jellyfin,media3:exoplayer,media3:session}`, `preference` |
| Toolchain | JDK **21** (Gradle-toolchain `java-jdk = 21`), bytecode Java 1.8 |
| SDK | `compileSdk` 36, `targetSdk` 36, **`minSdk` 21** |
| Identiteit | `applicationId` = `namespace` = **`org.jellyfin.androidtv`** (debug `.debug`); appnaam `Jellyfin` / `Jellyfin Debug`. Let op: `app_id` (accounttype van de authenticator) en de zoeksuggestie-authority worden in `app/build.gradle.kts` uit **`namespace`** afgeleid, niet uit `applicationId` (zie ADR-0004). |
| Server-API | jellyfin-sdk-kotlin **1.7.1** (API 10.10.7); app-minimum `Jellyfin.minimumVersion` = 10.10.0, met aangekondigd minimum 10.11.0 en een 10.11-specifiek apparaatprofiel → past bij 10.11.11 |
| Tests | 4 testklassen met 15 testgevallen (Kotest `FunSpec`): `TimeUtilsTests` (2), `CustomSeekProviderTests` (3), `VideoSpeedControllerTests` (8), `PreferenceStoreTests` (2). **Lokaal gedraaid:** 15/15 geslaagd in `testDebugUnitTest` én 15/15 in `testReleaseUnitTest` (JUnit-XML); de vier `playback`-modules hebben geen tests (`NO-SOURCE`). |
| Submodules | geen |
| Lokaal gebouwd? | **Ja (2026-11-09)**: `./gradlew --no-daemon --max-workers=4 assembleDebug test` → BUILD SUCCESSFUL; debug-APK pakket `org.jellyfin.androidtv.debug` met `app_id` en zoek-authority consistent op `.debug` (`aapt2`). Ook groen op GitHub (run 42608527671). Niet geïnstalleerd/gestart → gebruik NIET GEVALIDEERD (hardware). |

### 2.3 `desktop/` — Jellyfin Desktop 2.0.0 (Windows / macOS / Linux)

| Onderwerp | Waarde (bron) |
|---|---|
| Soort app | Qt 6 **WebEngine**-venster dat de **web-client van de server** toont, met ingebouwde **mpv**-speler (audio-passthrough), MPRIS, CEC, SDL-invoer |
| Taal / build | C++17 + QML, **CMake ≥ 3.10…3.31**, Ninja/Make |
| Toolchain Linux (gemeten) | Ubuntu 24.04: GCC 13.3, CMake 3.28, Qt **6.4.2** (base/declarative/webengine/wayland), libmpv 0.37; afhankelijkheden volgens `debian/control` (`REQUIRED_QT_VERSION` 6.0.0) |
| Toolchain Windows/macOS (upstream) | Qt 6.8.0 + MSVC 2019/2022, libmpv van SourceForge, WiX; macOS: Homebrew `qt@6`, `mpv` (macOS 12+/14+) |
| Identiteit | binary `jellyfin-desktop`, app-id `org.jellyfin.JellyfinDesktop` (desktop-/appdata-bestand), Debian-pakket `jellyfin-desktop` |
| Server-API | geen eigen API-versiecheck; gebruikt de web-client die de server levert (`jelly-leon-web` 10.11.11) + `client-api.md` (native shell) |
| Tests | 1 Qt-test (`tests/test_systemcomponent.cpp`, via `ctest`) |
| Submodules | **ja: `external/mpvqt`** (KDE, `https://invent.kde.org/libraries/mpvqt.git`, gepind op `2ebbd38`). Na de subtree-import bleef alleen een **lege gitlink** over → opgelost met een geneste subtree op exact die commit (JLC-0001, ADR-0005). Zonder die bron faalt de configure op Ubuntu 24.04 (`MpvQtConfig.cmake` ontbreekt; `debian/control` noemt geen `libmpvqt-dev`) — gemeten. |
| Lokaal gebouwd? | **Ja (Linux, container)**: 62/62 bouwstappen, `ctest` 1/1 geslaagd met `-DUSE_STATIC_MPVQT=ON` (`test-evidence/p0-desktop-container-build.json`; op 2026-11-09 opnieuw op de nieuwe machine: `test-evidence/p0-afronding-lokale-bouw.json`). Ook groen op GitHub (run 42600307251). Niet gestart (geen scherm), niet tegen een server, Windows/macOS niet gebouwd. |

### 2.4 `swiftfin/` — Swiftfin 1.6.1 (iPhone / iPad / Apple TV)

| Onderwerp | Waarde (bron) |
|---|---|
| Soort app | **Native** SwiftUI-app, eigen spelers (VLCKit "Swiftfin-speler" + AVKit "native"), praat rechtstreeks met de server-API via jellyfin-sdk-swift |
| Taal / build | Swift 5 (+ macro's), Xcode-project `Swiftfin.xcodeproj` met schema's `Swiftfin` en `Swiftfin tvOS`; Swift Package Manager (39 gepinde pakketten in `Package.resolved`), **Carthage** voor binaire VLCKit 3.7.2 (`MobileVLCKit`, `TVVLCKit` van `code.videolan.org`); build-fasen roepen `swiftgen`, `swiftformat`, `swiftlint` aan (Brewfile) |
| Toolchain | macOS 26 + **Xcode 26.6** (upstream-CI `macos-26`) |
| OS-minimum | **iOS 18.6**, **tvOS 26.1** (`*_DEPLOYMENT_TARGET`) |
| Identiteit | bundle-id **`org.jellyfin.swiftfin`** (`XcodeConfig/Shared.xcconfig`, ook in het project); `XcodeConfig/DevelopmentTeam.xcconfig` wordt optioneel ingevoegd en staat in `.gitignore` |
| Server-API | **jellyfin-sdk-swift 3.0.0 → gegenereerd tegen Jellyfin API 12.0.0.** Swiftfin markeert een server met major.minor < 12.0 als niet compatibel ("Update to Jellyfin 12.0 for the best experience"). Jelly Leon draait 10.11.11 → **waarschuwing en mogelijk ontbrekende functies** (ADR-0009). Ter vergelijking: Swiftfin **1.5** gebruikte SDK 2.1.0 (API 10.11.8). |
| Tests | **geen** testtargets in het project (2 native targets, beide `application`) |
| Submodules | geen |
| Lokaal gebouwd? | **Nee — NIET GEVALIDEERD (Mac/Xcode)**: geen macOS/Xcode in deze bouwomgeving. Wel: de CI-workflow bouwt op een GitHub-macOS-runner voor de iOS- en tvOS-simulator zonder signing en is groen (run 42608527121); de app is daar niet gestart, niet getest en niet op een apparaat gezet. |

## 3. Servercompatibiliteit (verwachting, niet getest op apparaten)

| Client | Praat met | Verwacht met Jelly Leon 10.11.11 (nu) | Verwacht met Jellyfin 12.x (vóór P4, ADR-0009) | Validatie |
|---|---|---|---|---|
| android 2.7.3 | web-client van de server + REST via SDK 1.7.1 | compatibel (SDK ≥ 10.10, web-client 10.11.11) | onbekend: SDK 1.7.1 (API 10.10.7) laat 12.x door; geen gebruikte route weg (statisch), web-client/brug niet beoordeeld | NIET GEVALIDEERD (hardware) |
| androidtv 0.19.10 | REST via SDK 1.7.1 | compatibel (minimum 10.10, 10.11-profiel aanwezig) | onbekend: geen gebruikte route weg (statisch); DTO's/gedrag niet beoordeeld | NIET GEVALIDEERD (hardware) |
| desktop 2.0.0 | web-client van de server | compatibel (zelfde web-client als browser) | volgt de web-client van de server (`jelly-leon-web` 12.x) | Linux-build unit-getest; gebruik NIET GEVALIDEERD (hardware) |
| swiftfin 1.6.1 | REST via SDK 3.0.0 (API 12.0) | **waarschuwing "Update to Jellyfin 12.0"**, functionele compatibiliteit onbekend | past bij de SDK (API 12.0); waarschuwing naar verwachting weg | NIET GEVALIDEERD (Mac/Xcode) |

Besluit gebruiker (2026-11-09): Swiftfin 1.6.1 blijft, de server gaat vóór P4 naar de nieuwste stabiele 12.x
(gemeten 2026-11-09: `v12.4`); de Android-clients worden dan gecontroleerd volgens ADR-0009 (routevergelijking:
`test-evidence/p0-server-12x-routevergelijking.json`).

Het **protocol** van stock clients is aan serverkant nagebootst in `jelly-leon` (stock-client-smoketest 17/17,
`jelly-leon/docs/platform-v2/CLIENT_COMPAT_MATRIX.md`). Dat zegt niets over deze client-builds op echte apparaten.
Smart-tv-apps (Samsung/LG), Chromecast en AirPlay: **unknown** tot D15 bekend is.

## 4. Delta-matrix B03-003 "Beschikbaarheid van clients" (bestaand / onvolledig / ontbrekend)

| Eis (B03-003 / B03 §1) | Stand na P0 | Toelichting |
|---|---|---|
| Upstream-protocol behouden | **bestaand** | Geen enkele codewijziging; technische identiteit "Jellyfin" ongewijzigd (ADR-0004) |
| Web / PWA-shell | buiten deze repo | `jelly-leon-web` (web-client) en Hub-UI in `ai-server-manager` |
| Android-telefoon | **bestaand (upstream)**, build **gemeten** | lokaal en op GitHub: assemble + unit-tests (`NO-SOURCE`) groen; niet op een apparaat |
| Android TV | **bestaand (upstream)**, build **gemeten** | lokaal en op GitHub: assemble + 15/15 unit-tests per variant; niet op een apparaat |
| iOS / tvOS | **bestaand (upstream)**, build **onvolledig** | simulatorbuild zonder signing groen op GitHub-macOS-runner; lokaal NIET GEVALIDEERD (Mac/Xcode); server gaat vóór P4 naar 12.x (ADR-0009) |
| Desktop | **bestaand (upstream)**, Linux-build **gemeten** | Windows/macOS-builds ontbreken in onze CI |
| Tv-browser, smart-tv, Chromecast/AirPlay | **ontbrekend / unknown** | afhankelijk van D15; Chromecast alleen in android *proprietary* |
| Geteste matrix op echte apparaten (ondertitels, hervatten, afspelen) | **ontbrekend** | acceptatie B03-003 vraagt echte apparaten → Geblokkeerd |
| Branding "Jelly Leon" (zichtbare naam) | **ontbrekend (bewust)** | P0 wijzigt niets; besluit: eigen applicationId/bundle-id naast de officiële apps, patch in P4 (ADR-0004) |
| Distributie naar apparaten (APK/IPA/installers) | **ontbrekend** | geen TrueNAS-app (ADR-0008); kanaal is een gebruikersbesluit |
| Upstream-sync + patchregister | **bestaand (nieuw in P0)** | `tools/clients/`, workflows, 115 tests (Sim-getest) |

## 5. Bekende afhankelijkheden van derden (relevant voor licentie en distributie)

- android *proprietary*: Google Play Services / Cast (`playservices`, `media3-cast`) — niet vrij; *libre*-flavor heeft ze niet.
- swiftfin: VLCKit 3.7.2 (LGPL-2.1, binair via Carthage van `code.videolan.org`); Google Cast SDK staat in de repo maar is in de `Cartfile` uitgecommentarieerd.
- desktop: Qt 6 (LGPL-3/GPL), libmpv (LGPL/GPL), mpvqt (LGPL), CEC, SDL2 — systeembibliotheken op Linux.
- Alle clients halen bij het bouwen afhankelijkheden van internet (Maven/Google, SwiftPM/GitHub, Carthage/videolan, apt).
