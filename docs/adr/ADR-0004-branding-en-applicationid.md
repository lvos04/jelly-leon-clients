# ADR-0004 — Branding: alleen zichtbare naam "Jelly Leon"; applicationId/bundle-id is een open vraag

- **Status:** Aanvaard voor P0 (niets wijzigen); **OPEN VRAAG voor de gebruiker** over de app-identiteit
- **Context:** Vaste keuze (contract §1): technische identiteit/API blijft "Jellyfin", alleen de zichtbare naam wordt
  "Jelly Leon"; GPL-licenties en upstream-credits blijven staan. Voor de clients betekent "technische identiteit" ook:
  de `Authorization: MediaBrowser Client=…`-header, apparaatprofielen, en de app-identiteit op het apparaat
  (Android `applicationId`, iOS bundle-id, desktop app-id).

## Besluit voor P0

- **Niets aan branding gewijzigd.** App-namen blijven `Jellyfin` (android `strings_donottranslate.xml`, androidtv
  `app_name_release`), bundle-id's en applicationId's blijven upstream. Afwijkingen zou `check_clients.py` als
  niet-geregistreerde patch weigeren.
- Later (P1+) mag alleen de **zichtbare** naam/het pictogram "Jelly Leon" worden — eerst via build-configuratie, anders
  via een geregistreerde patch. De clientnaam in de `Authorization`-header, apparaatprofielen en API-gedrag blijven
  ongewijzigd (servercompatibiliteit, statistieken, sessies).
- Bij android en desktop komt het meeste zichtbare uit de **web-client van de server** (`jelly-leon-web`); daar hoort de
  branding primair.

## OPEN VRAAG — Android `applicationId` (en iOS bundle-id)

| Keuze | Gevolg |
|---|---|
| **Zelfde ID** (`org.jellyfin.mobile`, `org.jellyfin.androidtv`) | De Jelly Leon-app **vervangt** de officiële app: niet naast elkaar te installeren. Omdat onze APK met een andere sleutel ondertekend is, weigert Android een update over de officiële app (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`): eerst de officiële app verwijderen (lokale app-gegevens zoals serverlijst, instellingen en downloads gaan dan verloren). Play Store/F-Droid-updates van Jellyfin werken daarna niet meer voor dat apparaat. Geen bronpatch nodig. |
| **Andere ID** (bv. `org.jellyfin.mobile.jellyleon` of een eigen domein) | **Naast elkaar** installeerbaar met eigen gegevens en eigen updates; terugvallen op de officiële app blijft mogelijk (past bij I24 stap 6 "oude player blijft intact"). Vraagt een geregistreerde patch: android `app/build.gradle.kts` (`applicationId`/`applicationIdSuffix`); androidtv daarnaast de `resValue`'s `app_id` (accounttype van de authenticator) en `app_search_suggest_authority`, die upstream uit `namespace` afleidt — anders botst het accounttype met de officiële app en werkt zoeken niet. `namespace` (Kotlin-pakket) blijft ongewijzigd. |

- **iOS/tvOS (Swiftfin):** `org.jellyfin.swiftfin` hoort bij het Apple-team van Jellyfin; een eigen build op een
  apparaat zetten (ook TestFlight/ad-hoc) vraagt vrijwel zeker een **eigen bundle-id** onder het Apple-account van de
  gebruiker. Upstream voegt optioneel `XcodeConfig/DevelopmentTeam.xcconfig` in (staat in `.gitignore`); bundle-id en
  team zijn dus mogelijk zonder bronpatch via build-instellingen te zetten — NIET GEVALIDEERD (Mac/Xcode). Daarnaast is
  een Apple Developer-account nodig (account; mogelijk betaald → gebruikersbesluit, geen kosten zonder akkoord).
- **Desktop:** app-id `org.jellyfin.JellyfinDesktop`, pakketnaam `jellyfin-desktop`, binary `jellyfin-desktop`. Een
  eigen pakket met dezelfde namen vervangt het officiële; naast elkaar vraagt andere namen (patch).
- **Debug-builds uit onze CI** hebben upstream al de suffix `.debug` (`org.jellyfin.mobile.debug`,
  `org.jellyfin.androidtv.debug`) en zijn dus nu al naast de officiële release-app te installeren — alleen voor testen.

**Advies (veiligste interpretatie, niet uitgevoerd):** andere ID voor Android en Android TV, eigen bundle-id voor iOS,
zodat de officiële apps als terugvaloptie blijven staan. De gebruiker beslist; tot dan blijft alles upstream.

## Gevolgen

- B03-003-branding blijft "ontbrekend (bewust)" in de delta-matrix; geen release van eigen APK's/IPA's vóór dit besluit.
