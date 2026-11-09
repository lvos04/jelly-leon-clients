# TrueNAS Home Platform V2 — documentatie voor `jelly-leon-clients`

Bron: uitvoeringspakket `TrueNAS_Home_Platform_V2_VOLLEDIG_2026-11-09.zip` (peildatum 9 november 2026).

**Rol van deze repo (vast besluit):** Forks van jellyfin-android 2.7.3, jellyfin-androidtv 0.19.10, jellyfin-desktop 2.0.0, Swiftfin 1.6.1 (iOS/tvOS: NIET GEVALIDEERD, Mac/Xcode nodig).

Hier staan alleen de eigen B-, I-, A- en promptdocumenten plus de gedeelde architectuur (`00_START`, `01_ARCHITECTUUR`, `05_TESTS`). Het volledige pakket en de Excel staan in `lvos04/ai-server-manager` onder `docs/platform-v2/`.

Onbekende NAS-gegevens (D01–D18) worden nooit met voorbeeldwaarden ingevuld; ze worden via de onboarding-wizard in de web-UI vastgelegd.

## Contract (kopie, niet lokaal wijzigen)

- `PLATFORM_CONTRACTEN.md` — `contracts 1.2`, byte-gelijke kopie van `lvos04/ai-server-manager`
  `docs/platform-v2/PLATFORM_CONTRACTEN.md` (bron-commit `8b54f39`); bij verschil wint de bron.
- `CONTRACT_1.2_CONFORMITEIT.md` — wat elke repo voor 1.2 moet veranderen (deze repo: §11, JC1–JC5); zelfde bron.
- Drifttest: `tools/clients/tests/test_contract_kopie.py` (vaste SHA-256 van de bron; met de bronrepo naast deze repo
  of `JLC_CONTRACT_BRON=<map>` ook een byte-vergelijking met de actuele bron). Relatieve links in de kopie (bv. naar
  `docs/adr/ADR-0011-contract-1-2.md`) wijzen naar bestanden in ai-server-manager.

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

## Eigen documenten van deze repo (P0 en contract 1.2)

- `FORK_STRATEGIE.md` — aanpak: subtree-indeling, upstream-sync per client, patchregister, branding, licenties
- `INVENTARIS.md` — per client taal/build, toolchain, minimale SDK/OS, tests, servercompatibiliteit, delta-matrix B03-003
- `PATCHES.md` — patchregister (JLC-…), automatisch gecontroleerd door `tools/clients/check_clients.py`
- `BOUWVERIFICATIE_P0.md` en `test-evidence/` — wat echt gebouwd/getest is en wat geblokkeerd was
- `EVIDENCE.json` — status per Excel-taak (contract §11)
- `test-evidence/contract-1.2-app-identiteit.json` — lokale builds en `aapt2`-metingen van de eigen app-identiteit
- Besluiten: `../adr/ADR-0001…0010` (ADR-0010: contract 1.2 in deze repo); B03 2.0-besluiten van jelly-leon die de clients raken: `../adr/README.md`
