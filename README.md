# Jelly Leon clients

Apparaat-apps voor het universele mediaplatform van **TrueNAS Home Platform V2** (bouwplan B03): forks van de officiële
Jellyfin-clients, bijgehouden met upstream en later met de zichtbare naam **"Jelly Leon"**. De technische identiteit en
het protocol blijven "Jellyfin", zodat alles blijft werken met de server [`jelly-leon`](https://github.com/lvos04/jelly-leon)
(Jellyfin 10.11.11) en met gewone Jellyfin-servers.

> **Stand contract 1.2 (2026-11-09):** inventaris, bouw- en syncbasis (P0); android, androidtv en desktop lokaal
> gebouwd en getest. **Eigen app-identiteit naast de officiële apps** (besluit van de gebruiker, ADR-0004): android
> `org.jellyfin.mobile.jellyleon`, androidtv `org.jellyfin.androidtv.jellyleon`, Swiftfin
> `org.jellyfin.swiftfin.jellyleon` (geregistreerde patches JLC-0002…0004, alleen build-configuratie). Zichtbare naam,
> pictogram, protocol en Kotlin-/Swift-code zijn ongewijzigd. Niets is op een echt apparaat getest.

## Inhoud

| Map | Upstream | Versie | Platform | Licentie |
|---|---|---|---|---|
| [`android/`](android/) | [jellyfin-android](https://github.com/jellyfin/jellyfin-android) | v2.7.3 | Android-telefoon/tablet (Android 5.0+) | GPL-2.0 |
| [`androidtv/`](androidtv/) | [jellyfin-androidtv](https://github.com/jellyfin/jellyfin-androidtv) | v0.19.10 | Android TV / Google TV / Fire TV | GPL-2.0 |
| [`desktop/`](desktop/) | [jellyfin-desktop](https://github.com/jellyfin/jellyfin-desktop) | v2.0.0 | Windows, macOS, Linux | GPL-2.0 |
| [`swiftfin/`](swiftfin/) | [Swiftfin](https://github.com/jellyfin/Swiftfin) | 1.6.1 | iPhone/iPad (iOS 18.6+), Apple TV (tvOS 26.1+) | MPL-2.0 |

Elke map is een `git subtree` (squash) van exact de upstream-tag; `desktop/external/mpvqt/` is de door upstream als
submodule gepinde KDE MpvQt-bron (LGPL), als geneste subtree toegevoegd. Alles daarbuiten is van deze fork:

- [`docs/platform-v2/FORK_STRATEGIE.md`](docs/platform-v2/FORK_STRATEGIE.md) — samenvatting van de aanpak
- [`docs/platform-v2/INVENTARIS.md`](docs/platform-v2/INVENTARIS.md) — per client: taal, build, toolchain, minimale
  SDK/OS, tests, servercompatibiliteit, delta-matrix
- [`docs/platform-v2/PATCHES.md`](docs/platform-v2/PATCHES.md) — patchregister (elke afwijking van upstream)
- [`docs/platform-v2/BOUWVERIFICATIE_P0.md`](docs/platform-v2/BOUWVERIFICATIE_P0.md) — wat echt gebouwd/getest is
- [`docs/platform-v2/EVIDENCE.json`](docs/platform-v2/EVIDENCE.json) — status per Excel-taak
- [`docs/platform-v2/PLATFORM_CONTRACTEN.md`](docs/platform-v2/PLATFORM_CONTRACTEN.md) — kopie van `contracts 1.2`
  (met `CONTRACT_1.2_CONFORMITEIT.md`; drifttest `tools/clients/tests/test_contract_kopie.py`)
- [`docs/adr/`](docs/adr/) — architectuurbesluiten
- [`tools/clients/`](tools/clients/) — basislijn, forkregels, upstream-sync, bouwverificatie, tests
- [`.github/workflows/`](.github/workflows/) — eigen CI (`clients-*.yml`)

## Bouwen

De officiële bouwinstructies staan in de README van elke client. Onze CI (GitHub Actions) bouwt:

| Client | Workflow | Wat |
|---|---|---|
| android | `Clients / Android` | JDK 21, `./gradlew --max-workers=2 assembleDebug test` + release-resources, `aapt2`-controle app-identiteit, debug-APK's als artefact |
| androidtv | `Clients / Android TV` | JDK 21, idem (ook `app_id` en zoek-authority), debug-APK als artefact |
| desktop | `Clients / Desktop` | Ubuntu 24.04, afhankelijkheden uit `debian/control`, `-DUSE_STATIC_MPVQT=ON`, `ctest` |
| swiftfin | `Clients / Swiftfin` | macOS 26 + Xcode 26.6, Carthage, `xcodebuild` voor iOS- en tvOS-simulator zonder signing, bundle-id uit de build-instellingen |

Lokaal voor ontwikkelaars (Linux): `make help`. `make android-bouw` / `make androidtv-bouw` (JDK 21 en `ANDROID_HOME`
met platform 36) bouwen de debug-APK's, draaien de unit-tests en controleren met `aapt2` de eigen app-identiteit
(debug en release); `make check` controleert die ook in de bron; de desktop-client is in een container te bouwen met
`make desktop-bouw` (alleen ontwikkeling; geen installatiemethode). Op een gedeelde machine: `GRADLE_LOCK=<bestand>` en
`DOCKER_LOCK=<bestand>` serialiseren de zware stappen met `flock`. Debug-APK's hebben de upstream-suffix `.debug` en
(`org.jellyfin.*.jellyleon.debug`) zijn alleen bedoeld om te testen.

**Validatie:** android, androidtv (15/15 unit-tests per variant) en desktop-Linux (ctest 1/1) zijn lokaal gebouwd en
getest en de vier client-workflows zijn groen op GitHub; Swiftfin bouwt in CI voor de simulator maar is **NIET
GEVALIDEERD (Mac/Xcode)**; niets is op een apparaat gestart (**NIET GEVALIDEERD (hardware)**). Zie
`BOUWVERIFICATIE_P0.md`.

## Upstream bijhouden

```
make sync-status                                   # per client: actueel | update_beschikbaar | unknown
python3 tools/clients/upstream_sync.py sync android
```

Een sync is `git subtree pull --prefix <map> --squash <upstream> <tag>` in een eigen branch `sync/<client>-<tag>`;
bij een conflict of overtreding wordt alles teruggedraaid. De workflow `Clients / Upstream-sync` doet dit wekelijks,
pusht alleen de syncbranch en draait daarop de CI. Overnemen in de hoofdbranch is altijd een menselijke stap.

## Installeren op apparaten

Nog niet: deze clients zijn geen TrueNAS-apps en er worden nog geen eigen APK's of iOS-builds verspreid. Gebruik tot
de pilot de officiële Jellyfin-apps. De eigen app-ID's staan er nu (naast de officiële apps te installeren); eigen
builds wachten nog op een besluit over ondertekening en verspreidingskanaal (ADR-0008).

## Besluiten van de gebruiker (2026-11-09)

1. **App-identiteit:** eigen `applicationId` voor Android en Android TV (naast de officiële app), eigen bundle-id voor
   iOS; concreet `org.jellyfin.mobile.jellyleon` en `org.jellyfin.androidtv.jellyleon` (keuzemenu). Uitgevoerd als
   JLC-0002/0003; Swiftfin volgt hetzelfde patroon (JLC-0004). (ADR-0004, ADR-0010)
2. **Swiftfin 1.6.1 blijft**; de server gaat vóór P4 naar de nieuwste stabiele Jellyfin 12.x (.NET 10), in een aparte
   fase in `jelly-leon`/`jelly-leon-web`; de Android-clients worden dan op 12.x gecontroleerd. (ADR-0009)
3. **Zichtbaarheid:** repos en images worden publiek na een scan van de volledige historie op geheimen en
   privégegevens (bevindingen eerst aan de gebruiker). (ADR-0007)

## Open vragen voor de gebruiker

1. **Swiftfin-bundle-id** `org.jellyfin.swiftfin.jellyleon` bevestigen (afgeleid van het Android-besluit) en een
   **Apple-account** voor builds op echte apparaten.
2. **Welke apparaten** (D15): tv-modellen, telefoons, Android TV/Apple TV — nodig voor de echte testmatrix.
3. **Verspreidingskanaal** voor eigen APK's/IPA's/installers (ADR-0008).

## Licentie en credits

Elke client valt onder zijn eigen upstream-licentie (zie de tabel en de licentiebestanden in de mappen, die
ongewijzigd blijven). Jellyfin, Jellyfin Android, Jellyfin Android TV, Jellyfin Desktop en Swiftfin zijn projecten van
de [Jellyfin-gemeenschap](https://jellyfin.org); MpvQt is van KDE. Dit is geen officiële Jellyfin-release. Voor de
fork-eigen bestanden is (nog) geen aparte licentie gekozen.
