# TrueNAS Home Platform V2 — documentatie voor `jelly-leon-clients`

Bron: uitvoeringspakket `TrueNAS_Home_Platform_V2_VOLLEDIG_2026-11-09.zip` (peildatum 9 november 2026).

**Rol van deze repo (vast besluit):** Forks van jellyfin-android 2.7.3, jellyfin-androidtv 0.19.10, jellyfin-desktop 2.0.0, Swiftfin 1.6.1 (iOS/tvOS: NIET GEVALIDEERD, Mac/Xcode nodig).

Hier staan alleen de eigen B-, I-, A- en promptdocumenten plus de gedeelde architectuur (`00_START`, `01_ARCHITECTUUR`, `05_TESTS`). Het volledige pakket en de Excel staan in `lvos04/ai-server-manager` onder `docs/platform-v2/`.

Onbekende NAS-gegevens (D01–D18) worden nooit met voorbeeldwaarden ingevuld; ze worden via de onboarding-wizard in de web-UI vastgelegd.

## Contract (kopie, niet lokaal wijzigen)

- `PLATFORM_CONTRACTEN.md` — `contracts 1.3`, byte-gelijke kopie van `lvos04/ai-server-manager`
  `docs/platform-v2/PLATFORM_CONTRACTEN.md` (bron-commit `02b119c`); bij verschil wint de bron.
- `CONTRACT_1.3_CONFORMITEIT.md` — wat elke repo voor 1.3 moet veranderen (deze repo: §11, C1.3-JLC-01…03); zelfde
  bron en bron-commit. Hoe deze repo eraan voldoet: `../adr/ADR-0012-contract-1-3-in-de-clients.md`.
- `CONTRACT_1.2_CONFORMITEIT.md` — historie (deze repo: §11, JC1–JC5), ook byte-gelijk aan de bron op dezelfde
  bron-commit.
- Drifttest: `tools/clients/tests/test_contract_kopie.py` (vaste SHA-256 van elke kopie; met een git-checkout van de
  bronrepo naast deze repo of `JLC_CONTRACT_BRON=<map>` ook een byte-vergelijking met de bron op de bron-commit; een
  nieuwere contractstand in de bron geeft alleen een waarschuwing). Relatieve links in de kopie (bv. naar
  `docs/adr/…`) wijzen naar bestanden in ai-server-manager.
- De kopie noemt de bevestiging van de app-ID's nog als open punt (§1.2); de gebruiker heeft ze op 2026-11-10
  bevestigd (ADR-0004, ADR-0012). De kopie wordt niet lokaal aangepast; dat is gemeld als contractpunt.

## B03 2.0 — universele mediaserver (goedgekeurd door de gebruiker op 2026-11-09)

- `02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` (versie 2.0), `02_BOUWPLANNEN/B03_FASERING.md` en
  `02_BOUWPLANNEN/B03_BESLUITEN.md` zijn byte-gelijke kopieën uit `lvos04/ai-server-manager` (bron-commit `0f390bf`),
  net als `00_START/INHOUDSOPGAVE.md`. Nooit hier bewerken: een nieuwe stand overnemen = opnieuw byte-gelijk kopiëren.
- **HARDE EIS van de gebruiker:** alle kijkgeschiedenis (gezien-status, hervatpunten, favorieten, beoordelingen, onthouden
  spoorkeuzes, gebruikers, rechten) en de MediaGuard-voortgang blijven altijd beschikbaar (bouwplan §10.9 en B03-015). Geen
  cutover zonder vóór/na-rapport per gebruiker en uitdrukkelijk akkoord van de gebruiker op elk verschil; de bestaande
  installatie blijft ongewijzigd als terugval.
- **Huidige mediaserver: Emby.** De overname vanuit Emby (B03-015, JLT-70…74) heeft prioriteit P0 en begint al in golf 0.
  Voor de clients telt: na de overname loggen gebruikers in met een nieuw wachtwoord of SSO (wachtwoorden zijn niet over te
  zetten) en hervatten ze op het juiste punt (JLT-70 met stock-web en de Android-emulator; JLT-74 op de echte NAS,
  *Geblokkeerd*). Emby blijft ongewijzigd draaien tot de gebruiker na de controlelijst "Emby verwijderen" (bouwplan §10.9.2)
  zelf besluit.
- Besluiten van het bouwplan die de clients raken staan in jelly-leon (ADR-0015…0024); de verwijzingen staan in
  [`../adr/README.md`](../adr/README.md). Een kaal ADR-nummer in de kopieën is een ADR van jelly-leon of ai-server-manager,
  niet van deze repo.
- `EXCEL_TAKEN.json` bevat de volledige B03-set: B03-001…079 (de uitgebreide rijen B03-004/005/007/009/010/013 vervangen
  de oude rijen; de oude tekst staat er letterlijk vooraan in) en de testrijen JLT-01…74 (conventie van ai-server-manager:
  Fase `P6 - E2E`, Soort `Testen`, startstatus en bewijsrijen in `Afhankelijkheid`). Nooit `Gereed` of `Geslaagd`. Deze repo
  voert er 15 uit (o.a. B03-016 clientmatrix, B03-019 compat-regressie, B03-026 volgmodus, B03-068, B03-077 clients).

## Bestanden

- `00_START/BESLUITEN_EN_ONBEKENDEN.md`
- `00_START/INHOUDSOPGAVE.md`
- `00_START/INHOUD_CONTROLE.json`
- `00_START/LEES_MIJ_EERST.md`
- `00_START/SHA256SUMS.txt`
- `01_ARCHITECTUUR/01_PROJECTCHARTER.md`
- `01_ARCHITECTUUR/02_DATA_EIGENAARSCHAP.md`
- `01_ARCHITECTUUR/03_RISICO_AUTONOMIE.md`
- `01_ARCHITECTUUR/04_GEGEVENS_EN_STORAGE.md`
- `01_ARCHITECTUUR/05_OPERATIES_EN_UPDATES.md`
- `01_ARCHITECTUUR/06_FASERING_EN_GATES.md`
- `01_ARCHITECTUUR/07_API_EN_EVENTSCHEMA.md`
- `01_ARCHITECTUUR/08_UI_EN_INTERACTIES.md`
- `02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` (versie 2.0, kopie)
- `02_BOUWPLANNEN/B03_FASERING.md` (kopie)
- `02_BOUWPLANNEN/B03_BESLUITEN.md` (kopie)
- `03_INSTALLATIE/I24_UNIVERSELE_MEDIASERVER.md`
- `04_BESTAANDE_APPS/A17_JELLYFIN.md`
- `05_TESTS/GEBRUIKERSWENSEN_TRACEERBAARHEID.md`
- `05_TESTS/INTEGRALE_E2E_TESTMATRIX.md`
- `06_TEMPLATES/PROMPTS_PER_APP/PROMPT_B03_UNIVERSELE_MEDIASERVER.md`

## Eigen documenten van deze repo (P0, contract 1.2 en contract 1.3)

- `FORK_STRATEGIE.md` — aanpak: subtree-indeling, upstream-sync per client, patchregister, branding, licenties
- `INVENTARIS.md` — per client taal/build, toolchain, minimale SDK/OS, tests, servercompatibiliteit, delta-matrix B03-003
- `PATCHES.md` — patchregister (JLC-…), automatisch gecontroleerd door `tools/clients/check_clients.py`
- `BOUWVERIFICATIE_P0.md` en `test-evidence/` — wat echt gebouwd/getest is en wat geblokkeerd was
- `EVIDENCE.json` — status per Excel-taak (contract §11)
- `test-evidence/contract-1.2-app-identiteit.json` — lokale builds en `aapt2`-metingen van de eigen app-identiteit
- `test-evidence/contract-1.3-app-identiteit.json` — de eigen builds gemeten tegen de officiële upstream-APK's
  (`app_identiteit.py vergelijk`), met tegenproef; apparaten en Swiftfin NIET GEVALIDEERD
- Besluiten: `../adr/ADR-0001…0012` (ADR-0010: contract 1.2 in deze repo; ADR-0011: clientcompatibiliteit met 12.x;
  ADR-0012: contract 1.3 in deze repo en de bevestigde app-ID's);
  B03 2.0-besluiten van jelly-leon die de clients raken: `../adr/README.md`

## P4-0 — clients tegen de Jelly Leon 12.x-server (JC3, 2026-11-10)

- `BOUWVERIFICATIE_P4-0.md` — wat echt gebouwd en gedraaid is: release-APK's met de eigen applicationId op telefoon-,
  tablet- (Sim-mislukt, niet stabiel) en Android TV-emulators, desktop 2.0.0 onder Xvfb, de serverkant van het Swiftfin-protocol en de statische
  routevergelijking, telkens tegen de jelly-leon-image 12.4.0-jl.0 met stock 12.4 als controlegroep
- `test-evidence/p4-0-jc3-*` — het bewijs (JSON en schermafdrukken van de Jelly Leon-runs)
- Harnas: `tools/clients/compat/` (`tools/clients/client_compat.py`, `make compat-android|compat-desktop|compat-swiftfin`);
  statische CI: `.github/workflows/clients-compat.yml`
