# TrueNAS Home Platform V2 — documentatie voor `jelly-leon-clients`

Bron: uitvoeringspakket `TrueNAS_Home_Platform_V2_VOLLEDIG_2026-11-09.zip` (peildatum 9 november 2026).

**Rol van deze repo (vast besluit):** Forks van jellyfin-android 2.7.3, jellyfin-androidtv 0.19.10, jellyfin-desktop 2.0.0, Swiftfin 1.6.1 (iOS/tvOS: NIET GEVALIDEERD, Mac/Xcode nodig).

Hier staan alleen de eigen B-, I-, A- en promptdocumenten plus de gedeelde architectuur (`00_START`, `01_ARCHITECTUUR`, `05_TESTS`). Het volledige pakket en de Excel staan in `lvos04/ai-server-manager` onder `docs/platform-v2/`.

Onbekende NAS-gegevens (D01–D18) worden nooit met voorbeeldwaarden ingevuld; ze worden via de onboarding-wizard in de web-UI vastgelegd.

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
- `02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md`
- `03_INSTALLATIE/I24_UNIVERSELE_MEDIASERVER.md`
- `04_BESTAANDE_APPS/A17_JELLYFIN.md`
- `05_TESTS/GEBRUIKERSWENSEN_TRACEERBAARHEID.md`
- `05_TESTS/INTEGRALE_E2E_TESTMATRIX.md`
- `06_TEMPLATES/PROMPTS_PER_APP/PROMPT_B03_UNIVERSELE_MEDIASERVER.md`

## Eigen documenten van deze repo (fase P0)

- `FORK_STRATEGIE.md` — aanpak: subtree-indeling, upstream-sync per client, patchregister, branding, licenties
- `INVENTARIS.md` — per client taal/build, toolchain, minimale SDK/OS, tests, servercompatibiliteit, delta-matrix B03-003
- `PATCHES.md` — patchregister (JLC-…), automatisch gecontroleerd door `tools/clients/check_clients.py`
- `BOUWVERIFICATIE_P0.md` en `test-evidence/` — wat echt gebouwd/getest is en wat geblokkeerd was
- `EVIDENCE.json` — status per Excel-taak (contract §11)
- Besluiten: `../adr/ADR-0001…0009`
