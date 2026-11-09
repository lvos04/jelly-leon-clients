# Patchregister Jelly Leon clients (afwijkingen van upstream in `android/`, `androidtv/`, `desktop/`, `swiftfin/`)

Elke afwijking van de upstream-basis **binnen een clientmap** — gewijzigd, toegevoegd of verwijderd bestand, ook een
vervangen submodule-gitlink — is een patch en moet hier staan (ADR-0003). De basis per client is de jongste
subtree-squashcommit, die exact de upstream-tag uit `tools/clients/baseline.json` bevat.
`tools/clients/check_clients.py` controleert dat in CI (workflow *Clients / Forkregels*):

- een niet-geregistreerde afwijking → CI faalt;
- een geregistreerd bestand dat niet (meer) afwijkt → CI faalt (register verouderd, bv. na upstream-acceptatie);
- beschermde bestanden (licenties en credits: `android/LICENSE.md`, `androidtv/LICENSE`, `androidtv/CONTRIBUTORS.md`,
  `desktop/LICENSE`, `swiftfin/LICENSE.md`, de LGPL-teksten van mpvqt) mogen **nooit** afwijken of ontbreken;
- het register en de basislijn worden gelezen uit de gecontroleerde commit (een niet-gecommitte registratie telt niet);
- geen gitlinks/submodules: die zou `git subtree` leeg laten (ADR-0005).

Alles **buiten** de vier clientmappen (`README.md`, `docs/`, `tools/`, `.github/`, `Makefile`) is fork-eigen en
hoort niet in dit register.

**Vorm per patch** (de checker leest deze tabelvelden): `Status` ∈ `actief` | `upstream-aangeboden` | `vervallen`;
`Client` = sleutel uit de basislijn; `Bestanden` met elk pad (vanaf de repo-root) tussen backticks — een pad dat op
`/` eindigt dekt een hele map; verplicht ook `Doel`, `Waarom nodig`, `Upstream-PR-kans` en `Test`.

**Volgorde vóór een patch:** configuratie of build-optie → serverkant (Jelly Leon-plugin of web-client) → pas dan
een patch in de client. Branding is in P0 bewust **niet** gewijzigd (ADR-0004).

| ID | Titel | Client | Soort | Status |
|---|---|---|---|---|
| JLC-0001 | Submodule `external/mpvqt` als geneste subtree | desktop | bronvolledigheid (geen codewijziging) | actief |
| JLC-0002 | Eigen applicationId `org.jellyfin.mobile.jellyleon` | android | app-identiteit (build-configuratie + back-upregels) | actief |
| JLC-0003 | Eigen applicationId `org.jellyfin.androidtv.jellyleon` met `app_id` en zoek-authority | androidtv | app-identiteit (build-configuratie + back-upregels) | actief |
| JLC-0004 | Eigen bundle-id `org.jellyfin.swiftfin.jellyleon` | swiftfin | app-identiteit (build-instellingen) | actief |

Appcode (Kotlin, C++, Swift): **geen** patches — de app-identiteitspatches (JLC-0002 e.v.) wijzigen alleen
build-configuratie en XML-resources (contract 1.2 §2.3 regel 6, besluit van de gebruiker 2026-11-09, ADR-0004).
Kotlin-`namespace`/pakketten, de clientnaam in de `Authorization`-header, apparaatprofielen, API-gedrag, zichtbare
naam en pictogrammen zijn ongewijzigd.
De verwachte ID's staan centraal in `tools/clients/app_identiteit.json`; `tools/clients/app_identiteit.py bron`
(workflow *Clients / Forkregels*) en `… bouwmap` met `aapt2` (workflows *Clients / Android* en *Clients / Android TV*)
controleren ze.

## JLC-0001 — Submodule `external/mpvqt` als geneste subtree

| Veld | Waarde |
|---|---|
| Status | actief |
| Client | desktop |
| Soort | bronvolledigheid: lege submodule-gitlink vervangen door de broncode van exact de gepinde commit; geen wijziging aan code van jellyfin-desktop of mpvqt |
| Sinds | 2026-11-09 (forkversie 2.0.0-jl.0) |
| Doel | jellyfin-desktop v2.0.0 pint `external/mpvqt` als git-submodule op `2ebbd38bf65d01be9c55d673ecd43c8bb9a6fc8e` (KDE MpvQt, `v1.1.1-1-g2ebbd38`). Bij de subtree-import bleef alleen een lege gitlink over: broncode ontbrak, `-DUSE_STATIC_MPVQT=ON` kon niet bouwen en de LGPL-bron van een meegeleverde bibliotheek was niet in de fork aanwezig. |
| Bestanden | `desktop/external/mpvqt` |
| Wijziging | gitlink (mode 160000) verwijderd; `git subtree add --squash --prefix desktop/external/mpvqt https://github.com/KDE/mpvqt.git 2ebbd38…` (officiële GitHub-spiegel van `invent.kde.org/libraries/mpvqt`, dezelfde commit-hash). `desktop/.gitmodules` blijft byte-gelijk aan upstream (in een submap heeft het geen effect). |
| Waarom nodig | Zonder deze bron is de desktop-client niet reproduceerbaar te bouwen op systemen zonder `libmpvqt-dev` en is de fork niet bronvolledig (GPL-2.0/LGPL). Een git-submodule in de root zou de subtree-indeling (ADR-0001) doorbreken. |
| Upstream-PR-kans | n.v.t. — upstream gebruikt bewust een submodule. |
| Test | `tools/clients/check_clients.py`: upstream-gitlink == geneste basislijn-commit, geneste squashcommit == dezelfde commit en dezelfde inhoud (`upstream_tree` `7d1a4c1bcc95…`, in de review tegen de bron nagemeten); `tools/clients/tests/test_check_clients.py` en `test_upstream_sync.py` (gitlink-pin gelijk/gewijzigd/nieuw); lokale container-build met `-DUSE_STATIC_MPVQT=ON` (zie `BOUWVERIFICATIE_P0.md`). |
| Bij upstream-sync | Ongewijzigde pin → schone merge. Gewijzigde pin → `upstream_sync.py` lost het gitlink-conflict op en zet de geneste subtree op de nieuwe pin. Nieuwe submodule → sync faalt bewust (handmatig beoordelen). |

## JLC-0002 — Eigen applicationId `org.jellyfin.mobile.jellyleon`

| Veld | Waarde |
|---|---|
| Status | actief |
| Client | android |
| Soort | app-identiteit: build-configuratie en back-upregels; geen Kotlin-code |
| Sinds | 2026-11-09 (forkversie 2.7.3-jl.1) |
| Doel | De Jelly Leon-build naast de officiële Jellyfin-app kunnen installeren (eigen gegevens, eigen updates, terugvallen op de officiële app blijft mogelijk). Release `org.jellyfin.mobile.jellyleon`, debug `org.jellyfin.mobile.jellyleon.debug` (upstream-suffix `.debug` blijft). |
| Bestanden | `android/app/build.gradle.kts`, `android/app/src/main/res/xml/backup_content.xml` |
| Wijziging | `defaultConfig`: `applicationId = "org.jellyfin.mobile.jellyleon"` (stond er upstream niet: impliciet gelijk aan `namespace`); `namespace = "org.jellyfin.mobile"` blijft. Back-upregels: sharedpref `org.jellyfin.mobile[.debug]_preferences` → `org.jellyfin.mobile.jellyleon[.debug]_preferences` (de app schrijft `${packageName}_preferences`, `AppPreferences.kt`); vorm verder gelijk aan upstream. |
| Waarom nodig | Zonder eigen ID vervangt de build de officiële app (zelfde pakketnaam, andere ondertekening → installatie faalt of de officiële app moet eerst weg). Zonder aangepaste back-upregels vallen de instellingen stil buiten de Android-back-up. Authorities (`${applicationId}.image-provider`, `.androidx-startup`) en `BuildConfig.APPLICATION_ID` volgen vanzelf. Een build-optie zonder bestandswijziging bestaat niet (de Gradle-configuratie zelf is de plek). |
| Upstream-PR-kans | Laag — upstream heeft geen reden voor een andere ID; een optionele Gradle-property zou kunnen, maar niet nodig. |
| Test | `tools/clients/app_identiteit.py bron` en `tools/clients/tests/test_app_identiteit.py` (bron + aapt2-uitvoer met een nep-aapt2, Sim-getest); `app_identiteit.py bouwmap android android/app/build` met de echte `aapt2` op de debug-APK's (libre + proprietary) en de release-`.ap_` in CI en lokaal (pakketnaam, authorities en eigen permissies met de pakketnaam als prefix, sharedpref-namen, verschil met `org.jellyfin.mobile[.debug]`). Naast de officiële app installeren en Chromecast (*proprietary*) met de andere pakketnaam: NIET GEVALIDEERD (hardware). |
| Bij upstream-sync | Wijzigt upstream `defaultConfig` of de back-upregels, dan conflicteert de sync bewust (exitcode 2, ADR-0002) en wordt de patch met de hand opnieuw toegepast; de bron-controle in *Forkregels* faalt als de ID verdwijnt. |

## JLC-0003 — Eigen applicationId `org.jellyfin.androidtv.jellyleon` met `app_id` en zoek-authority

| Veld | Waarde |
|---|---|
| Status | actief |
| Client | androidtv |
| Soort | app-identiteit: build-configuratie en back-upregels; geen Kotlin-code |
| Sinds | 2026-11-09 (forkversie 0.19.10-jl.1) |
| Doel | De Jelly Leon-build naast de officiële Jellyfin-app voor Android TV kunnen installeren, met een eigen accounttype en eigen zoeksuggesties. Release `org.jellyfin.androidtv.jellyleon`, debug `org.jellyfin.androidtv.jellyleon.debug`. |
| Bestanden | `androidtv/app/build.gradle.kts`, `androidtv/app/src/main/res/xml/backup_content.xml`, `androidtv/app/src/main/res/xml/backup_rules.xml` |
| Wijziging | `applicationId = namespace` → `applicationId = "org.jellyfin.androidtv.jellyleon"`; de `resValue`'s `app_id`, `app_search_suggest_authority` en `app_search_suggest_intent_data` (release en debug) worden afgeleid van `defaultConfig.applicationId` (+ `applicationIdSuffix`) in plaats van `namespace`. Back-upregels (`backup_content.xml` 2 regels, `backup_rules.xml` 4 regels): sharedpref `org.jellyfin.androidtv[.debug]_preferences` → `org.jellyfin.androidtv.jellyleon[.debug]_preferences` (`PreferenceManager.getDefaultSharedPreferences` = `${packageName}_preferences`). `namespace = "org.jellyfin.androidtv"` blijft. |
| Waarom nodig | Upstream leidt `app_id` (accounttype van de authenticator, `res/xml/authenticator.xml`) en de zoek-authority/-data (`res/xml/searchable.xml`) af van `namespace`, terwijl de code `BuildConfig.APPLICATION_ID` gebruikt (`AccountManagerMigration.ACCOUNT_TYPE`, `MediaContentProvider.AUTHORITY`) en het manifest `${applicationId}.content`. Alleen de applicationId wijzigen zou het accounttype van de officiële app delen (Android houdt één authenticator per accounttype) en zoeksuggesties naar een niet-bestaande provider laten wijzen. |
| Upstream-PR-kans | Middel — afleiden van `applicationId` in plaats van `namespace` is ook upstream correcter (geldt voor elke afgeleide build); de vaste eigen ID zelf blijft fork-eigen. |
| Test | `tools/clients/app_identiteit.py bron` en `tools/clients/tests/test_app_identiteit.py` (Sim-getest); `app_identiteit.py bouwmap androidtv androidtv/app/build` met de echte `aapt2` op de debug-APK en de release-`.ap_` in CI (lokaal ook op de release-APK): pakketnaam, `string/app_id` = pakketnaam, zoek-authority = pakketnaam + `.content` en bestaat als provider, accounttype in `xml/authenticator` en authority/data in `xml/searchable` verwijzen naar die waarden, alle authorities en eigen permissies met de pakketnaam als prefix, sharedpref-namen; unit-tests van upstream (15 per variant). Naast de officiële app installeren, accounts en zoeken op een tv: NIET GEVALIDEERD (hardware). |
| Bij upstream-sync | Zoals JLC-0002: conflict → sync faalt bewust; de bron-controle faalt als een `resValue` weer `namespace` gebruikt. |

## JLC-0004 — Eigen bundle-id `org.jellyfin.swiftfin.jellyleon`

| Veld | Waarde |
|---|---|
| Status | actief |
| Client | swiftfin |
| Soort | app-identiteit: build-instellingen (xcconfig + één doelinstelling in het project); geen Swift-code |
| Sinds | 2026-11-09 (forkversie 1.6.1-jl.1) |
| Doel | Eigen bundle-id voor iOS en tvOS naast de officiële Swiftfin-app (zelfde patroon als JLC-0002/0003). |
| Bestanden | `swiftfin/XcodeConfig/Shared.xcconfig`, `swiftfin/Swiftfin.xcodeproj/project.pbxproj` |
| Wijziging | `Shared.xcconfig`: `PRODUCT_BUNDLE_IDENTIFIER = org.jellyfin.swiftfin.jellyleon`. `project.pbxproj`: de doelinstelling `PRODUCT_BUNDLE_IDENTIFIER` van *Swiftfin iOS* / Release (de enige configuratie zonder `Shared.xcconfig` als basis; een doelinstelling wint van de xcconfig) krijgt dezelfde waarde. Alleen de xcconfig wijzigen (zoals `CONTRACT_1.2_CONFORMITEIT.md` JC2 noemt) zou iOS-Release op `org.jellyfin.swiftfin` laten. |
| Waarom nodig | Twee apps met dezelfde bundle-id kunnen niet naast elkaar op één apparaat; de eigen build zou de officiële app vervangen. Keychain-items (KeychainSwift), Spotlight-items en caches zijn per app en volgen zonder codewijziging. `fastlane/Fastfile.swift` (upstream-publicatiepad, door onze CI nooit gebruikt) noemt nog de officiële ID en blijft ongewijzigd. |
| Upstream-PR-kans | Geen — fork-eigen identiteit. |
| Test | `tools/clients/app_identiteit.py bron` (elke `PRODUCT_BUNDLE_IDENTIFIER` in xcconfig en project = de eigen ID) en `tools/clients/tests/test_app_identiteit.py`; workflow *Clients / Swiftfin*: `xcodebuild -showBuildSettings` voor beide schema's en beide configuraties + `CFBundleIdentifier` in de gebouwde simulator-app. Ondertekenen, registratie van de bundle-id bij Apple en installeren op een apparaat: **NIET GEVALIDEERD (Mac/Xcode)** en **NIET GEVALIDEERD (account)** (Apple Developer-account van de gebruiker nodig). |
| Bij upstream-sync | Zoals JLC-0002; een nieuwe doelinstelling met de officiële ID laat de bron-controle falen. |
