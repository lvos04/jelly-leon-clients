# Jelly Leon clients

Apparaat-apps voor het universele mediaplatform van **TrueNAS Home Platform V2** (bouwplan B03): forks van de officiële
Jellyfin-clients, bijgehouden met upstream en later met de zichtbare naam **"Jelly Leon"**. De technische identiteit en
het protocol blijven "Jellyfin", zodat alles blijft werken met de server [`jelly-leon`](https://github.com/lvos04/jelly-leon)
(Jellyfin 10.11.11) en met gewone Jellyfin-servers.

> **Stand P0 (2026-11-09):** inventaris, bouw- en syncbasis. **Aan de apps zelf is niets veranderd** — geen branding,
> geen andere app-ID's. Niets is op een echt apparaat getest.

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

Lokaal voor ontwikkelaars (Linux): `make help`. De desktop-client is in een container te bouwen met
`make desktop-bouw` (alleen ontwikkeling; geen installatiemethode). Debug-APK's hebben de upstream-suffix `.debug` en zijn
alleen bedoeld om te testen.

**Validatie:** desktop-Linux is lokaal gebouwd en unit-getest; Android-builds waren in de bouwomgeving geblokkeerd
(Android SDK niet downloadbaar); Swiftfin is **NIET GEVALIDEERD (Mac/Xcode)**. Geen enkele workflow heeft al op GitHub
gedraaid. Zie `BOUWVERIFICATIE_P0.md`.

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
de pilot de officiële Jellyfin-apps. Eerst beslist de gebruiker over de app-identiteit (zie hieronder) en het
verspreidingskanaal.

## Open vragen voor de gebruiker

1. **Android `applicationId`** — zelfde ID (`org.jellyfin.mobile`, `org.jellyfin.androidtv`): de Jelly Leon-app
   vervangt de officiële app (eerst verwijderen, app-gegevens weg, geen officiële updates). Andere ID: beide naast
   elkaar, terugval mogelijk, maar een kleine geregistreerde patch nodig. Advies: andere ID. (ADR-0004)
2. **iOS bundle-id en Apple-account** voor Swiftfin-builds op echte apparaten. (ADR-0004)
3. **Swiftfin 1.6.1 verwacht Jellyfin 12.0**; Jelly Leon is 10.11.11 → houden, terug naar Swiftfin 1.5, of server
   upgraden? (ADR-0009)
4. **Welke apparaten** (D15): tv-modellen, telefoons, Android TV/Apple TV — nodig voor de echte testmatrix.
5. **Zichtbaarheid van deze repo** vóór verspreiding aan anderen (GPL: bron beschikbaar). (ADR-0007)

## Licentie en credits

Elke client valt onder zijn eigen upstream-licentie (zie de tabel en de licentiebestanden in de mappen, die
ongewijzigd blijven). Jellyfin, Jellyfin Android, Jellyfin Android TV, Jellyfin Desktop en Swiftfin zijn projecten van
de [Jellyfin-gemeenschap](https://jellyfin.org); MpvQt is van KDE. Dit is geen officiële Jellyfin-release. Voor de
fork-eigen bestanden is (nog) geen aparte licentie gekozen.
