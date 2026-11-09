# ADR-0004 — Branding alleen zichtbaar; eigen applicationId/bundle-id naast de officiële apps

- **Status:** Aanvaard — **besluit van de gebruiker 2026-11-09** (STATUS.md, besluit 1). Uitvoering pas in **P4** als
  geregistreerde patch; tot dan blijft alles upstream.
- **Context:** Vaste keuze (contract §1): technische identiteit/API blijft "Jellyfin", alleen de zichtbare naam wordt
  "Jelly Leon"; GPL-licenties en upstream-credits blijven staan. Voor de clients betekent "technische identiteit" ook:
  de `Authorization: MediaBrowser Client=…`-header, apparaatprofielen en API-gedrag. De app-identiteit op het apparaat
  (Android `applicationId`, iOS bundle-id, desktop app-id) is géén protocolzaak: die bepaalt alleen of onze build naast
  de officiële app kan staan.

## Besluit

1. **Android en Android TV krijgen een eigen `applicationId`**, zodat de Jelly Leon-app **naast** de officiële
   Jellyfin-app te installeren is (eigen gegevens, eigen updates; terugvallen op de officiële app blijft mogelijk —
   past bij I24 stap 6 "oude player blijft intact").
2. **iOS/tvOS (Swiftfin) krijgt een eigen bundle-id** onder het Apple-account van de gebruiker. **NIET GEVALIDEERD
   (Mac/Xcode)**; een Apple Developer-account is nodig (account, mogelijk betaald → geen kosten zonder akkoord van de
   gebruiker).
3. **De wijziging zelf volgt in P4** als geregistreerde patch in `docs/platform-v2/PATCHES.md` (voorlopig JLC-0002
   android en JLC-0003 androidtv; nummers worden pas bij de patch vastgelegd). In P0/P1 wordt **geen** applicationId,
   bundle-id, appnaam of pictogram gewijzigd; `check_clients.py` zou dat als niet-geregistreerde patch weigeren.
4. Ongewijzigd blijven, ook in P4: `namespace` (Kotlin-pakket `org.jellyfin.mobile` / `org.jellyfin.androidtv`), de
   clientnaam in de `Authorization`-header, apparaatprofielen, API-gedrag, licentie- en creditbestanden.
5. Zichtbare naam/pictogram "Jelly Leon" is een aparte stap (B03-branding): eerst via build-configuratie, anders als
   geregistreerde patch. Bij android en desktop komt het meeste zichtbare uit de web-client van de server
   (`jelly-leon-web`); daar hoort de branding primair.

### Concrete waarde van de ID (vast te zetten bij de P4-patch, vóór de eerste verspreiding)

Een `applicationId` is na verspreiding praktisch permanent (een andere ID = een andere app). Daarom wordt de waarde
pas bij de patch vastgezet en in deze ADR bijgeschreven. Voorstel (veiligste keuze, nog niet vastgelegd):

| Client | Voorstel | Debug (upstream-suffix blijft) |
|---|---|---|
| android | `io.github.lvos04.jellyleon` | `io.github.lvos04.jellyleon.debug` |
| androidtv | `io.github.lvos04.jellyleon.tv` | `io.github.lvos04.jellyleon.tv.debug` |
| swiftfin | `io.github.lvos04.jellyleon` (iOS) / tvOS volgens Xcode-target | n.v.t. |

Reden: een naamruimte die bij de eigenaar van deze repo hoort (GitHub-account `lvos04`), zonder te claimen dat de
build van `jellyfin.org` komt. Alternatief met de kleinste diff: suffix `.jellyleon` op de upstream-ID
(`org.jellyfin.mobile.jellyleon`); nadeel: blijft in de naamruimte van het Jellyfin-project. Heeft de gebruiker een
eigen domein, dan heeft dat de voorkeur.

## Patchplan P4 (gemeten in de broncode en in de lokaal gebouwde debug-APK's, 2026-11-09)

**android (`jellyfin-android` 2.7.3):**

- `android/app/build.gradle.kts`: `applicationId` staat er nu niet → is impliciet gelijk aan `namespace`
  (`org.jellyfin.mobile`). Patch: `applicationId = "<eigen ID>"` in `defaultConfig`; `namespace` blijft.
- `android/app/src/main/res/xml/backup_content.xml`: de regels `sharedpref` `org.jellyfin.mobile_preferences` en
  `org.jellyfin.mobile.debug_preferences` volgen de pakketnaam. Zonder aanpassing vallen de instellingen stil buiten de
  Android-back-up.
- Niet nodig (gecontroleerd): de manifest-authorities gebruiken `${applicationId}` (debug-APK gemeten:
  `org.jellyfin.mobile.debug.image-provider`, `org.jellyfin.mobile.debug.androidx-startup`); de eigen broadcast
  (`ACTION_STOP`) zet `package = BuildConfig.APPLICATION_ID` en de ontvanger is `RECEIVER_NOT_EXPORTED`; de overige
  `org.jellyfin.mobile.intent.*`-strings zijn intern (expliciete intents) en meldingskanalen zijn per app. Nog te
  controleren in P4: Chromecast (*proprietary*) met een andere pakketnaam — NIET GEVALIDEERD (hardware).

**androidtv (`jellyfin-androidtv` 0.19.10):**

- `androidtv/app/build.gradle.kts`: `applicationId = namespace` → eigen ID.
- Zelfde bestand: de `resValue`'s `app_id` (accounttype van de authenticator, `res/xml/authenticator.xml`),
  `app_search_suggest_authority` en `app_search_suggest_intent_data` (`res/xml/searchable.xml`) worden afgeleid van
  **`namespace`** (+ suffix van het buildtype). De code gebruikt echter `BuildConfig.APPLICATION_ID` voor het
  accounttype (`AccountManagerMigration.ACCOUNT_TYPE`) en de content-provider (`MediaContentProvider.AUTHORITY`), en
  het manifest `${applicationId}.content`. Patch: deze drie waarden afleiden van de applicationId. Anders: accounttype
  gelijk aan dat van de officiële app (Android houdt één authenticator per accounttype aan) en zoeksuggesties wijzen
  naar een provider die niet bestaat.
- `androidtv/app/src/main/res/xml/backup_content.xml` (2 regels) en `backup_rules.xml` (4 regels): `sharedpref`-namen
  `org.jellyfin.androidtv[.debug]_preferences` → nieuwe pakketnaam.
- Gemeten in de debug-APK van nu: pakket `org.jellyfin.androidtv.debug`, `app_id` = `org.jellyfin.androidtv.debug`,
  zoek-authority `org.jellyfin.androidtv.debug.content` → upstream laat debug al consistent naast release bestaan; de
  patch maakt hetzelfde mechanisme geldig voor de eigen ID.

**Test bij de patch (P4):** forkregels (geregistreerd, geen andere bestanden); CI-controle met `aapt2` dat pakketnaam
= `app_id` en dat elke authority met de pakketnaam begint; unit-tests en assemble van beide clients; naast elkaar
installeren op een emulator (Sim) en op echte apparaten uit D15 (**NIET GEVALIDEERD (hardware)** tot dat gedaan is).

**Desktop:** app-id `org.jellyfin.JellyfinDesktop`, pakket/binary `jellyfin-desktop`. Het besluit noemt alleen Android
en iOS; naast elkaar installeren vraagt andere namen (patch) en wordt samen met de zichtbare branding beslist. Tot dan
upstream.

## Gevolgen

- Geen release van eigen APK's/IPA's vóór de P4-patch; de debug-APK's uit onze CI (`.debug`-suffix, debug-sleutel)
  zijn alleen voor testen en staan nu al naast de officiële release-app.
- Elke upstream-sync na P4 moet de patch schoon laten (de sync faalt anders met exitcode 2, ADR-0002).
- B03-003-branding blijft tot P4 "ontbrekend (bewust)" in de delta-matrix (`INVENTARIS.md` §4).
