# Jelly Leon clients

Apparaat-apps voor het universele mediaplatform van **TrueNAS Home Platform V2** (bouwplan B03): forks van de officiële
Jellyfin-clients, bijgehouden met upstream en later met de zichtbare naam **"Jelly Leon"**. De technische identiteit en
het protocol blijven "Jellyfin", zodat alles blijft werken met de server [`jelly-leon`](https://github.com/lvos04/jelly-leon)
(Jellyfin 10.11.11) en met gewone Jellyfin-servers.

> **Stand P0 (2026-11-09):** inventaris, bouw- en syncbasis; android, androidtv en desktop lokaal gebouwd en getest,
> alle client-workflows groen op GitHub. **Aan de apps zelf is niets veranderd** — geen branding, geen andere app-ID's
> (eigen ID's volgen in P4, ADR-0004). Niets is op een echt apparaat getest.

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
- [`docs/adr/`](docs/adr/) — architectuurbesluiten
- [`tools/clients/`](tools/clients/) — basislijn, forkregels, upstream-sync, bouwverificatie, tests
- [`.github/workflows/`](.github/workflows/) — eigen CI (`clients-*.yml`)

## Bouwen

De officiële bouwinstructies staan in de README van elke client. Onze CI (GitHub Actions) bouwt:

| Client | Workflow | Wat |
|---|---|---|
| android | `Clients / Android` | JDK 21, `./gradlew --max-workers=2 assembleDebug test`, debug-APK's als artefact |
| androidtv | `Clients / Android TV` | JDK 21, `./gradlew --max-workers=2 assembleDebug test`, debug-APK als artefact |
| desktop | `Clients / Desktop` | Ubuntu 24.04, afhankelijkheden uit `debian/control`, `-DUSE_STATIC_MPVQT=ON`, `ctest` |
| swiftfin | `Clients / Swiftfin` | macOS 26 + Xcode 26.6, Carthage, `xcodebuild` voor iOS- en tvOS-simulator zonder signing |

Lokaal voor ontwikkelaars (Linux): `make help`. `make android-bouw` / `make androidtv-bouw` (JDK 21 en `ANDROID_HOME`
met platform 36) bouwen de debug-APK's en draaien de unit-tests; de desktop-client is in een container te bouwen met
`make desktop-bouw` (alleen ontwikkeling; geen installatiemethode). Op een gedeelde machine: `GRADLE_LOCK=<bestand>` en
`DOCKER_LOCK=<bestand>` serialiseren de zware stappen met `flock`. Debug-APK's hebben de upstream-suffix `.debug` en
zijn alleen bedoeld om te testen.

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
de pilot de officiële Jellyfin-apps. Eigen builds komen pas na de P4-patch voor de eigen app-ID's en een besluit over
het verspreidingskanaal.

## Besluiten van de gebruiker (2026-11-09)

1. **App-identiteit:** eigen `applicationId` voor Android en Android TV (naast de officiële app), eigen bundle-id voor
   iOS. De patch volgt in P4 als geregistreerde patch; tot dan alles upstream. (ADR-0004)
2. **Swiftfin 1.6.1 blijft**; de server gaat vóór P4 naar de nieuwste stabiele Jellyfin 12.x (.NET 10), in een aparte
   fase in `jelly-leon`/`jelly-leon-web`; de Android-clients worden dan op 12.x gecontroleerd. (ADR-0009)
3. **Zichtbaarheid:** repos en images worden publiek na een scan van de volledige historie op geheimen en
   privégegevens (bevindingen eerst aan de gebruiker). (ADR-0007)

## Open vragen voor de gebruiker

1. **Concrete app-ID** (voorstel in ADR-0004) en **Apple-account** voor Swiftfin-builds op echte apparaten.
2. **Welke apparaten** (D15): tv-modellen, telefoons, Android TV/Apple TV — nodig voor de echte testmatrix.
3. **Verspreidingskanaal** voor eigen APK's/IPA's/installers (ADR-0008).

## Licentie en credits

Elke client valt onder zijn eigen upstream-licentie (zie de tabel en de licentiebestanden in de mappen, die
ongewijzigd blijven). Jellyfin, Jellyfin Android, Jellyfin Android TV, Jellyfin Desktop en Swiftfin zijn projecten van
de [Jellyfin-gemeenschap](https://jellyfin.org); MpvQt is van KDE. Dit is geen officiële Jellyfin-release. Voor de
fork-eigen bestanden is (nog) geen aparte licentie gekozen.
