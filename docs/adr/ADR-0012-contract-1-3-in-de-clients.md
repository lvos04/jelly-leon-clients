# ADR-0012 — Contract 1.3 in jelly-leon-clients (C1.3-JLC-01…03) en de bevestigde app-ID's

- **Status:** Aanvaard (2026-11-10, ronde contract 1.3; aangevuld op 2026-11-11 met de meting van elke
  xml-resource, besluit 3)
- **Context:** `PLATFORM_CONTRACTEN.md` is naar `contracts 1.3` gegaan (ai-server-manager `02b119c`, inclusief de
  reviewcorrecties RV1–RV13). `CONTRACT_1.3_CONFORMITEIT.md` §11 noemt voor deze repo drie NU-punten:
  C1.3-JLC-01 (kopie + drifttest-pin), C1.3-JLC-02 (de ID-regel van §1.1 besluit 1 in de CI nalopen: niet alleen de
  ID, ook accounttype, authority, permissie, `app_search_suggest_*` en sharedpref-namen ≠ die van de officiële app;
  Swiftfin: de effectieve build-instelling) en C1.3-JLC-03 (de EVIDENCE-regels van 1.3 in de test). Daarnaast heeft de
  gebruiker op 2026-11-10 de app-ID's bevestigd (`ai-server-manager:docs/platform-v2/OVERDRACHT/STATUS.md`, sectie
  "Besluiten van de gebruiker na contract 1.3", commit `c63b32e`). Deze repo levert geen dienst en geen image
  (ADR-0008); de punten voor de vijf eigen diensten (statuspagina, koppelbestand, JWT, manifest) gelden hier niet.

## Besluiten

1. **C1.3-JLC-01 — kopie en pin.** `PLATFORM_CONTRACTEN.md` en `CONTRACT_1.3_CONFORMITEIT.md` zijn byte-gelijk
   overgenomen uit ai-server-manager op bron-commit `02b119cb84be` (de laatste commit die een van beide wijzigde).
   `CONTRACT_1.2_CONFORMITEIT.md` blijft als historie staan (C1.3-ALG-01 staat dat toe), maar dan in de stand van de
   bron op dezelfde commit: een kopie die niet gelijk is aan de bron zou de drifttest zinloos maken.
   `tools/clients/tests/test_contract_kopie.py` pint de drie SHA-256-waarden, vergelijkt met de bron op de pin als die
   lokaal naast deze repo staat, eist versie 1.3 met de punten C1.3-JLC-01…03 en faalt als er in `docs/platform-v2`
   een contract- of conformiteitsbestand zonder pin staat.

2. **C1.3-JLC-03 — EVIDENCE-regels van 1.3** (`tools/clients/tests/test_evidence.py`, als losse functie met
   tegenproeven). Gekozen lezing waar de tekst ruimte laat (de strengste):
   - `JLT-..` telt als Testmatrix-ID (zoals `EX..`; status `Mislukt` mag, `Geslaagd` nooit);
   - `Sim-geslaagd`/`Sim-mislukt` alleen bij Testmatrix-ID's en nooit samen (zelfde regel als jelly-leon-web);
     `Sim-getest` mag bij een Testmatrix-ID als een rij maar deels is uitgevoerd;
   - `Niet getest` alleen bij status `Niet gestart` — dus ook niet bij een besluit met status `Open` — en niet naast
     een testuitkomst (`Sim-…`, `Unit-getest`, `Intel-iGPU-getest`);
   - elke `NIET GEVALIDEERD (…)` in `blokkade` moet een waarde uit de vaste lijst zijn **en** in `validatie` staan;
   - contractpunten `C1.3-…`/`C1.2-…` moeten in de conformiteitslijst van hun versie staan; reviews hebben de vorm
     `REVIEW-jelly-leon-clients-<onderwerp>`.
   De nieuwe test vond twee fouten in het bestaande bewijs (B03-003: `NIET GEVALIDEERD (account)` alleen in de
   blokkade; I24-24-01: de niet-bestaande waarde `(echte NAS/hardware)`); beide zijn gecorrigeerd.

3. **C1.3-JLC-02 — de ID-regel gemeten tegen de officiële app.** Tot 1.2 bewees CI dat elke waarde van de eigen
   pakketnaam is afgeleid (`bouwmap`: prefix-regel, `app_id` = pakketnaam enz.). Dat sluit gelijkheid met de
   officiële app uit, maar alleen indirect. Sinds 1.3:
   - `app_identiteit.py vergelijk <client> <bouwmap>` meet met `aapt2` dezelfde waarden in de **officiële
     upstream-APK's van dezelfde versie** — alle gepubliceerde varianten (android: libre/proprietary × debug/release;
     androidtv: debug/release), dus ook de officiële debug-apps — en faalt bij elke gelijke pakketnaam, authority,
     eigen permissie, accounttype, `app_search_suggest_*`-waarde of sharedpref-naam, over de soorten heen. De APK's
     komen van de GitHub-release van upstream; hun SHA-256 (de digest van de release) staat in
     `tools/clients/app_identiteit.json` en wordt bij elke download gecontroleerd (tijdelijk bestand, atomaire
     hernoeming, geen gebruik bij afwijking). De officiële meting moet zelf bruikbaar zijn: elke officiële ID gemeten
     en authorities gevonden, anders exitcode 3 (niets gemeten is geen bewijs). Draait in *Clients / Android* en
     *Clients / Android TV* na de build, en in `make android-bouw`/`androidtv-bouw`.
   - **Elke xml-resource, bij elke client (2026-11-11).** De `aapt2`-controle las het accounttype en de
     zoek-authority eerst alleen uit de vaste androidtv-bestanden (`xml/authenticator`, `xml/searchable`). Bij android
     stond er daardoor altijd "accounttype 0; app_search_suggest 0", ook als een latere upstream zo'n bestand zou
     toevoegen: een aanname, geen meting. Nu leest de controle bij elke client elke `xml/`-resource in het archief op
     `accountType`, `searchSuggestAuthority`, `searchSuggestIntentData` en `contentAuthority` (sync-adapter), en tellen
     `permission-tree` en `permission-group` als permissie. Een officiële waarde is een overtreding in `bouwmap`/`apk`
     en telt mee in `vergelijk`; een xml-resource die `aapt2` niet kan lezen is exitcode 3. De vaste androidtv-eisen
     (JLC-0003) blijven. Gemeten op de echte artefacten: android (officieel en eigen) heeft geen van deze waarden,
     androidtv precies de drie bekende.
   - `app_identiteit.py bron` zoekt daarnaast in alle manifesten, `res/xml` en Kotlin/Java van alle Gradle-modules
     (zonder testbronnen en `buildSrc`) naar **letterlijk geschreven** officiële waarden (authority, permissie,
     `accountType`, zoek-authority/-data, `targetPackage`; in code: de officiële ID zelf, `<id>_preferences` en
     `<id>.<suffix>` met een authority-suffix uit het eigen manifest). Interne intent- en klassenamen
     (`org.jellyfin.mobile.intent.action.PLAY`, `org.jellyfin.androidtv.ui.…`) zijn geen identiteit en tellen niet.
   - **Swiftfin:** de CI leest al sinds 1.2 de effectieve build-instelling (`xcodebuild -showBuildSettings -json`,
     Debug en Release, iOS en tvOS) en de `CFBundleIdentifier` van de gebouwde simulator-app (*Clients / Swiftfin*,
     macOS-runner) — conform. Ondertekenen, registreren bij Apple en installeren: **NIET GEVALIDEERD (Mac/Xcode)** en
     **NIET GEVALIDEERD (account)**.

4. **Sharedpref-namen die niet van een pakketnaam zijn afgeleid** (androidtv `systemprefs`,
   `AuthenticationPreferences`; ook in de back-upregels van de officiële app) zijn gelijk aan die van de officiële
   app. De contractregel noemt "sharedpref-naam (`backup_content.xml`/`backup_rules.xml`) gelijk aan die van de
   officiële app". Lezing: de regel beschermt tegen botsingen en tegen back-upregels die naar de officiële app
   verwijzen; dat speelt alleen bij namen die de pakketnaam bevatten (`<pakket>_preferences`). Sharedprefs liggen in
   de afgeschermde datamap van elke app (`/data/data/<pakket>/shared_prefs`), dus een vaste naam als `systemprefs`
   kan niet botsen. Ze hernoemen zou een Kotlin-patch vragen zonder enige bescherming. `vergelijk` meldt zulke namen
   apart ("gelijk, toegestaan") en faalt op elke gelijke naam die een officiële ID bevat. Gemeld als contractpunt.

5. **Bevestigde app-ID's (2026-11-10).** `org.jellyfin.mobile.jellyleon` (Android), `org.jellyfin.androidtv.jellyleon`
   (Android TV) en `org.jellyfin.swiftfin.jellyleon` (iOS/tvOS; NIET GEVALIDEERD (Mac/Xcode)) zijn door de gebruiker
   bevestigd. ADR-0004 en `app_identiteit.json` (`bevestiging`) leggen dat vast. Contract 1.3 (§1.1 besluit 1, §1.2)
   noemt de bevestiging nog als open; de latere vastlegging door de gebruiker gaat voor, de tekst van de kopie wordt
   hier niet aangepast (gemeld als contractpunt). Wat níet verandert: de ID's zijn nog nergens verspreid, verspreiden
   wacht op het besluit over ondertekening en kanaal (ADR-0008), en een Apple-registratie vraagt een
   Apple Developer-account van de gebruiker (mogelijk betaald: alleen met diens akkoord). Na de eerste verspreiding
   verandert een ID niet meer.

6. **Gemeten, buiten de regel van §1.1 (niet gewijzigd, gemeld):**
   - **Swiftfin-URL-schema `swiftfin`** (`CFBundleURLSchemes` in beide `Info.plist`'s) is gelijk aan dat van de
     officiële app. Met beide apps op één apparaat bepaalt iOS welke app een `swiftfin://…`-deeplink opent. Het schema
     staat ook vast in de code (`DeepLink`: `^swiftfin://…`), dus wijzigen is een Swift-patch die hier niet te testen is
     (NIET GEVALIDEERD (Mac/Xcode)). Contract en besluit noemen URL-schema's niet; open voor de gebruiker/de
     contracteigenaar.
   - Swiftfin `CSSearchableItem`-ID, loggerlabel en cachenamen `org.jellyfin.swiftfin…`, Android-intentnamen
     `org.jellyfin.mobile.intent.*` en meldingskanalen zijn per app afgeschermd of expliciet binnen de app (geen
     botsing); `fastlane/Fastfile.swift` (upstream-publicatiepad, door onze CI nooit gebruikt) noemt de officiële ID.
   - Desktop houdt de upstream-app-id `org.jellyfin.JellyfinDesktop` (het besluit noemt alleen Android en iOS;
     ADR-0004).

## Gevolgen

- **Upstream-sync:** gaat een client naar een nieuwe upstream-versie, dan horen de `officiele_apks` in
  `app_identiteit.json` mee te gaan (naam, URL en SHA-256 van de nieuwe GitHub-release). `test_app_identiteit.py`
  faalt in *Clients / Forkregels* zolang ze bij een andere tag horen dan `baseline.json` — bewust, net als een
  patchconflict (ADR-0002).
- CI downloadt per Android-run de officiële APK's (android ±89 MB, androidtv ±50 MB) van GitHub; zonder netwerk faalt
  de stap met exitcode 3, nooit stil geslaagd.
- Bewijs: `docs/platform-v2/test-evidence/contract-1.3-app-identiteit.json` (lokale builds, echte vergelijking,
  tegenproef met de officiële APK's als "eigen" build) en `EVIDENCE.json` (C1.3-JLC-01…03). Validatie: **Unit-getest**
  (tooling) en **Sim-getest** (echte builds en officiële APK's op de ontwikkelmachine en in de GitHub-runs); naast
  elkaar installeren op echte apparaten **NIET GEVALIDEERD (hardware)**, Swiftfin op een eigen Mac, ondertekend of op
  een apparaat **NIET GEVALIDEERD (Mac/Xcode)** en **NIET GEVALIDEERD (account)**.
- ADR-0010 (contract 1.2) blijft de herkomst van de patches; het punt "§1.1/JC1 aanpassen" daaruit is in 1.3 opgelost
  (nieuwe regeltekst, gekozen ID's genoemd).
