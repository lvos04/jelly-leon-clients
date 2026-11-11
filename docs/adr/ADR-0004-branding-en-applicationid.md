# ADR-0004 — Branding alleen zichtbaar; eigen applicationId/bundle-id naast de officiële apps

- **Status:** Aanvaard — **besluit van de gebruiker 2026-11-09** (STATUS.md, besluit 1), concrete ID's eveneens
  **besluit van de gebruiker (2026-11-09)** en **door de gebruiker bevestigd op 2026-11-10**, ook de Swiftfin-bundle-id
  (`ai-server-manager:docs/platform-v2/OVERDRACHT/STATUS.md`, "Besluiten van de gebruiker na contract 1.3", commit
  `c63b32e`; ADR-0012). Uitgevoerd in de ronde van contract 1.2 (`CONTRACT_1.2_CONFORMITEIT.md` JC1/JC2) als
  geregistreerde patches JLC-0002 (android), JLC-0003 (androidtv) en JLC-0004 (swiftfin) — eerder dan het
  oorspronkelijke "P4", omdat contract 1.2 het in deze ronde vraagt. Contract 1.3 (§1.1 besluit 1) bewaakt sinds
  2026-11-10 ook in CI dat geen afgeleide waarde gelijk is aan die van de officiële app (C1.3-JLC-02, ADR-0012).
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
3. **De wijziging is een geregistreerde patch** in `docs/platform-v2/PATCHES.md`: JLC-0002 (android), JLC-0003
   (androidtv), JLC-0004 (swiftfin). Appnaam en pictogram blijven ongewijzigd (punt 5); `check_clients.py` weigert
   elke andere afwijking als niet-geregistreerde patch.
4. Ongewijzigd blijven, ook met de patches: `namespace` (Kotlin-pakket `org.jellyfin.mobile` /
   `org.jellyfin.androidtv`), de clientnaam in de `Authorization`-header, apparaatprofielen, API-gedrag, licentie- en
   creditbestanden.
5. Zichtbare naam/pictogram "Jelly Leon" is een aparte stap (B03-branding): eerst via build-configuratie, anders als
   geregistreerde patch. Bij android en desktop komt het meeste zichtbare uit de web-client van de server
   (`jelly-leon-web`); daar hoort de branding primair.

### Concrete waarde van de ID — besluit van de gebruiker (2026-11-09), bevestigd op 2026-11-10

| Client | Vastgezet (release) | Debug (upstream-suffix blijft) | Patch | Bron van de keuze |
|---|---|---|---|---|
| android | **`org.jellyfin.mobile.jellyleon`** | `org.jellyfin.mobile.jellyleon.debug` | JLC-0002 | besluit van de gebruiker (2026-11-09), **bevestigd 2026-11-10** |
| androidtv | **`org.jellyfin.androidtv.jellyleon`** | `org.jellyfin.androidtv.jellyleon.debug` | JLC-0003 | besluit van de gebruiker (2026-11-09), **bevestigd 2026-11-10** |
| swiftfin (iOS en tvOS) | **`org.jellyfin.swiftfin.jellyleon`** | n.v.t. (één ID voor Debug en Release) | JLC-0004 | eerst afgeleid (zelfde patroon, door de bouwer toegepast); **door de gebruiker bevestigd 2026-11-10** — NIET GEVALIDEERD (Mac/Xcode): nog nooit ondertekend of bij Apple geregistreerd |

**Bevestiging door de gebruiker (2026-11-10):** na contract 1.3 heeft de gebruiker de drie ID's bevestigd
(`ai-server-manager:docs/platform-v2/OVERDRACHT/STATUS.md`, "Besluiten van de gebruiker na contract 1.3": "App-ID's
(A02) bevestigd: `org.jellyfin.mobile.jellyleon` (Android), `org.jellyfin.androidtv.jellyleon` (Android TV),
`org.jellyfin.swiftfin.jellyleon` (iOS/tvOS; NIET GEVALIDEERD (Mac/Xcode))"). Daarmee vervalt het open punt van
contract 1.3 §1.2 ("Bevestiging van de Android-ID's … en van de Swiftfin-bundle-id"); de kopie van het contract in
deze repo noemt het nog als open en wordt niet lokaal aangepast (ADR-0012, gemeld als contractpunt). Vastgelegd in
`tools/clients/app_identiteit.json` (`bevestiging`). Verspreiden blijft wachten op het besluit over ondertekening en
kanaal (ADR-0008); een Apple-registratie vraagt een Apple Developer-account van de gebruiker (NIET GEVALIDEERD
(account); mogelijk betaald, dus alleen met diens akkoord).

**Besluit van de gebruiker (2026-11-09):** in het keuzemenu koos de gebruiker het alternatief "suffix `.jellyleon`
op de upstream-ID" uit het voorstel hieronder (`org.jellyfin.mobile.jellyleon` voor android,
`org.jellyfin.androidtv.jellyleon` voor androidtv). Herkomst in deze repo: de keuze is doorgegeven in de
orkestratie-opdracht van de contract-1.2-ronde; een eigen vastlegging in `ai-server-manager` (OVERDRACHT/STATUS.md)
bestond op de peildatum nog niet. De keuze heeft de kleinste diff en houdt de herkomst van de code herkenbaar; nadeel
(bewust geaccepteerd): de ID blijft in de naamruimte van het Jellyfin-project.

**Afwijking van de letterlijke contracttekst van 1.2 (gemeld als contractpunt, ADR-0010; in 1.3 opgelost):**
contract 1.2 §1.1 besluit 1 en `CONTRACT_1.2_CONFORMITEIT.md` JC1 zeiden "nooit `org.jellyfin.*` als ID van de fork".
Contract 1.3 heeft die regel vervangen door "nooit een ID die gelijk is aan die van een officiële app, en geen
accounttype, authority, permissie, `app_search_suggest_*`-waarde of sharedpref-naam die gelijk is aan die van de
officiële app; CI bewaakt dit", met de gekozen ID's erbij. De fork gebruikt **nooit een officiële ID**
(`org.jellyfin.mobile[.debug]`, `org.jellyfin.androidtv[.debug]`, `org.jellyfin.swiftfin`); dat alle afgeleide waarden
verschillen, bewaakt `tools/clients/app_identiteit.py` in CI (bron, `aapt2` op de eigen builds en sinds 1.3 de
vergelijking met de gemeten waarden van de officiële APK's, ADR-0012).

**De ID's liggen vast:** een `applicationId`/bundle-id is na verspreiding praktisch permanent (een andere ID = een andere
app). Er is nog niets verspreid. Met de bevestiging van 2026-11-10 liggen de ID's vast; wijzigen kan alleen met een
nieuw besluit van de gebruiker vóór de eerste verspreiding, in `tools/clients/app_identiteit.json` + de patches.

Oorspronkelijk voorstel (bewaard voor de herleidbaarheid; niet gekozen):

| Client | Voorstel | Debug (upstream-suffix blijft) |
|---|---|---|
| android | `io.github.lvos04.jellyleon` | `io.github.lvos04.jellyleon.debug` |
| androidtv | `io.github.lvos04.jellyleon.tv` | `io.github.lvos04.jellyleon.tv.debug` |
| swiftfin | `io.github.lvos04.jellyleon` (iOS) / tvOS volgens Xcode-target | n.v.t. |

Reden: een naamruimte die bij de eigenaar van deze repo hoort (GitHub-account `lvos04`), zonder te claimen dat de
build van `jellyfin.org` komt. Alternatief met de kleinste diff: suffix `.jellyleon` op de upstream-ID
(`org.jellyfin.mobile.jellyleon`); nadeel: blijft in de naamruimte van het Jellyfin-project. Heeft de gebruiker een
eigen domein, dan heeft dat de voorkeur.

## Patchplan (gemeten in de broncode en in de lokaal gebouwde debug-APK's, 2026-11-09; uitgevoerd als JLC-0002/0003)

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
  controleren op een apparaat: Chromecast (*proprietary*) met een andere pakketnaam — NIET GEVALIDEERD (hardware).

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

**Swiftfin (JLC-0004):** `XcodeConfig/Shared.xcconfig` is de basis van alle configuraties **behalve** de
projectconfiguratie Release; het doel *Swiftfin iOS* zet in Release zelf `PRODUCT_BUNDLE_IDENTIFIER =
org.jellyfin.swiftfin` (een doelinstelling wint van de xcconfig). Daarom wijzigt de patch beide plekken; alleen de
xcconfig (zoals JC2 noemt) liet iOS-Release op de officiële ID. Keychain (KeychainSwift), Spotlight-items en caches
zijn per app; `fastlane/Fastfile.swift` (upstream-publicatiepad, door onze CI nooit gebruikt) blijft ongewijzigd.

**Tests bij de patch (uitgevoerd 2026-11-09):** forkregels (geregistreerd, geen andere bestanden);
`tools/clients/app_identiteit.py bron` in *Clients / Forkregels*; `… bouwmap` met `aapt2` in *Clients / Android* en
*Clients / Android TV* op de debug-APK's en de gelinkte release-resources (pakketnaam, `app_id` = pakketnaam,
zoek-authority = pakketnaam + `.content` en bestaand als provider, accounttype/zoekwaarden opgelost in
`xml/authenticator`/`xml/searchable`, elke authority en eigen permissie met de pakketnaam als prefix,
sharedpref-namen); lokaal daarnaast op de release-APK's (`assembleRelease`, niet ondertekend) en als tegenproef op een
echte upstream-build en een "halve patch" (alleen `applicationId`: accounttype `org.jellyfin.androidtv.debug` = dat
van de officiële debug-app, 13 overtredingen); *Clients / Swiftfin* leest de bundle-id uit `xcodebuild
-showBuildSettings` (Debug en Release) en de Info.plist van de simulator-app. **Sinds contract 1.3 (2026-11-10,
ADR-0012):** `app_identiteit.py vergelijk` meet dezelfde waarden in de officiële upstream-APK's (alle varianten van
dezelfde versie, SHA-256 gepind) en faalt bij elke gelijke waarde; `bron` zoekt ook letterlijke officiële waarden in
manifesten, `res/xml` en Kotlin/Java van alle modules. Naast elkaar installeren op een
emulator en op echte apparaten uit D15: **NIET GEVALIDEERD (hardware)**; Swiftfin ondertekenen/registreren:
**NIET GEVALIDEERD (Mac/Xcode)** en **(account)**.

**Desktop:** app-id `org.jellyfin.JellyfinDesktop`, pakket/binary `jellyfin-desktop`. Het besluit noemt alleen Android
en iOS; naast elkaar installeren vraagt andere namen (patch) en wordt samen met de zichtbare branding beslist. Tot dan
upstream.

## Gevolgen

- Nog geen release van eigen APK's/IPA's: dat wacht op het besluit over ondertekening en verspreidingskanaal
  (ADR-0008). De debug-APK's uit onze CI (`org.jellyfin.*.jellyleon.debug`, debug-sleutel) zijn alleen voor testen.
- Elke upstream-sync moet de patches schoon laten (de sync faalt anders met exitcode 2, ADR-0002); de bron-controle
  in *Forkregels* faalt als de eigen ID verdwijnt.
- Zichtbare branding (naam/pictogram "Jelly Leon") blijft "ontbrekend (bewust)" in de delta-matrix
  (`INVENTARIS.md` §4); alleen de app-identiteit is nu eigen.
