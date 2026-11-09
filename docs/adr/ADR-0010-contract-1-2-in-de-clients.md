# ADR-0010 — Contract 1.2 in jelly-leon-clients (JC1–JC5) en de eigen app-identiteit

- **Status:** Aanvaard (2026-11-09, ronde contract 1.2)
- **Context:** `PLATFORM_CONTRACTEN.md` is naar `contracts 1.2` gegaan; `CONTRACT_1.2_CONFORMITEIT.md` §11 noemt voor
  deze repo JC1 (eigen applicationId android/androidtv), JC2 (eigen bundle-id Swiftfin, NIET GEVALIDEERD),
  JC3 (Android-clients tegen de 12.x-server, pas na JL1), JC4 (gedaan in P0) en JC5 (ontwerptaal niet van
  toepassing), plus de algemene punten A1–A4. Deze repo levert geen dienst (ADR-0008); alleen deze punten raken haar.

## Besluiten

1. **A1 — contractkopie:** `docs/platform-v2/PLATFORM_CONTRACTEN.md` en `CONTRACT_1.2_CONFORMITEIT.md` zijn
   byte-gelijke kopieën van ai-server-manager (bron-commit `8b54f39`). Drifttest
   `tools/clients/tests/test_contract_kopie.py`: altijd de vaste SHA-256 van de bron (werkt in CI zonder de bronrepo),
   en een byte-vergelijking met de actuele bron als die naast deze repo staat of `JLC_CONTRACT_BRON` is gezet; zonder
   bron wordt alleen die tweede laag overgeslagen (zichtbaar als *skipped*, nooit als geslaagd).
2. **JC1 — eigen applicationId (JLC-0002, JLC-0003):** uitgevoerd met de ID's uit het besluit van de gebruiker
   (2026-11-09, ADR-0004): `org.jellyfin.mobile.jellyleon` en `org.jellyfin.androidtv.jellyleon` (debug met de
   upstream-suffix `.debug`). Androidtv leidt `app_id`, `app_search_suggest_authority` en
   `app_search_suggest_intent_data` nu af van `defaultConfig.applicationId`; de sharedpref-namen in de back-upregels
   volgen de pakketnaam (R9). `namespace` en alle Kotlin-code blijven ongewijzigd.
3. **Tegenstrijdigheid contract ↔ besluit (veiligste interpretatie, gemeld):** §1.1 besluit 1 en JC1 zeggen "nooit
   `org.jellyfin.*` als ID van de fork", maar §2.3 regel 6 legt de exacte ID's bij ADR-0004 en de gebruiker koos daar
   het alternatief met suffix `.jellyleon` op de upstream-ID. Het latere, concrete besluit van de gebruiker gaat voor
   (contract §1: besluiten van de gebruiker zijn vast). Wat de contractregel beschermt, blijft hard bewaakt: geen
   enkele officiële ID en geen enkele afgeleide waarde (accounttype, authority, permissie, sharedpref) gelijk aan die
   van de officiële app — `tools/clients/app_identiteit.py` faalt anders in CI. De contracteigenaar moet §1.1/JC1
   aanpassen (bv. "nooit een officiële ID"). Er is nog niets verspreid; vóór de eerste verspreiding kan de gebruiker de
   ID nog wijzigen (één bestand `tools/clients/app_identiteit.json` + de patches).
4. **JC2 — eigen bundle-id (JLC-0004):** `org.jellyfin.swiftfin.jellyleon` (zelfde patroon als besluit 2; door de
   gebruiker te bevestigen vóór de eerste Apple-registratie). JC2 noemt alleen `XcodeConfig/Shared.xcconfig`, maar het
   doel *Swiftfin iOS* zet in Release zelf `PRODUCT_BUNDLE_IDENTIFIER` (de projectconfiguratie Release heeft de
   xcconfig niet als basis); daarom wijzigt de patch ook die ene regel in `project.pbxproj` (gemeld als contractpunt).
   Bewijs: bron-controle lokaal en in CI; op de macOS-runner leest *Clients / Swiftfin* de echte build-instellingen
   (`xcodebuild -showBuildSettings -json`, Debug en Release, iOS en tvOS) en de Info.plist van de simulator-app.
   Ondertekenen, Apple-registratie en installeren op een apparaat: **NIET GEVALIDEERD (Mac/Xcode)** en **NIET
   GEVALIDEERD (account)** (Apple Developer-account van de gebruiker; mogelijk betaald → niets zonder akkoord).
5. **Release-identiteit controleren zonder release-build in CI:** de workflowregel "geen `assembleRelease`/publicatie
   in CI" (ADR-0006, `tests/test_workflows.py`) blijft. CI linkt daarom alleen de release-resources
   (`process*ReleaseResources`: samengevoegd manifest + resources, geen code, geen ondertekening) en controleert die
   `*.ap_` met `aapt2` (bij resource-shrinking van android maakt AGP alleen het proto-formaat; aapt2 leest beide).
   Lokaal is daarnaast een volledige `assembleRelease` (niet ondertekend) gebouwd en gecontroleerd.
6. **Forkversies:** android `2.7.3-jl.1`, androidtv `0.19.10-jl.1`, swiftfin `1.6.1-jl.1` (eerste fork-eigen
   wijziging aan de app; bij een upstream-sync weer `-jl.0`, ADR-0002). Desktop blijft `2.0.0-jl.0`.
7. **JC3 — niet uitgevoerd (wacht op JL1):** de server `jelly-leon` stond op de peildatum nog op Jellyfin 10.11.11
   (`global.json` SDK 9.0.0; gelezen op commit `ce980c25d` van de branch, alleen lezen). Zonder 12.x-server is er
   niets om tegen te controleren; ADR-0009 blijft ongewijzigd. De statische routevergelijking v10.11.11 ↔ v12.4
   (`tools/clients/server_api_compat.py`) is een voorbereiding, geen compatibiliteitsbewijs.
8. **JC5 / §13:** de ontwerptaal Peil is voor de clients niet van toepassing (contract §13, ADR-0015 van de Hub); de
   Jellyfin-vormgeving blijft. Er is hier dan ook geen ontwerpstap of ontwerpreview.
9. **A2–A4:** commits eindigen met de attributieregel van de lopende sessie; de historiescan vóór publiek maken
   (A3/besluit 3) hoort niet bij deze ronde; `tests/test_evidence.py` bewaakt §11 al (A4).

## Gevolgen

- Appcode (Kotlin/Swift) blijft vrij van patches; alle drie de identiteitspatches zitten in build-configuratie en
  XML-resources en worden bij elke push en elke syncbranch gecontroleerd.
- Een upstream-sync die de gewijzigde regels raakt, faalt bewust (exitcode 2) en vraagt een mens (ADR-0002).
- Contractpunten voor de eigenaar (ai-server-manager): §1.1/JC1 "nooit `org.jellyfin.*`" tegenover het besluit van de
  gebruiker; JC2 noemt alleen de xcconfig.
