# ADR-0003 — Patchregister `docs/platform-v2/PATCHES.md` met automatische controle

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** GPL-2.0 §2a vraagt dat wijzigingen herkenbaar zijn; B03-013 vraagt een minimale patch stack; bij elke
  upstream-sync moet duidelijk zijn wat van ons is. Zelfde aanpak als `jelly-leon` (patch-ID's `JL-…`).

## Besluit

- Elke afwijking van upstream **binnen een clientmap** is een patch `JLC-<nnnn>` in `docs/platform-v2/PATCHES.md`
  met de velden `Status` (`actief` | `upstream-aangeboden` | `vervallen`), `Client`, `Doel`, `Bestanden` (paden tussen
  backticks; eindigt een pad op `/`, dan dekt het de hele map), `Waarom nodig`, `Upstream-PR-kans`, `Test`.
- `tools/clients/check_clients.py` vergelijkt per client de boom van de jongste squashcommit met `HEAD:<map>`
  (en per geneste subtree met diens squashcommit) en faalt bij:
  - een niet-geregistreerde afwijking (gewijzigd, toegevoegd, verwijderd, vervangen gitlink);
  - een geregistreerd pad dat niet (meer) afwijkt (register verouderd);
  - een wijziging aan een beschermd bestand (licenties, `CONTRIBUTORS.md`) — ook mét registratie;
  - ontbrekende verplichte velden, onbekende status of client, dubbele ID's.
- Volgorde vóór een patch: configuratie/build-optie → serverkant (plugin of web-client) → pas dan een clientpatch.

## Gevolgen

- Stand P0: één patch, JLC-0001 (mpvqt als geneste subtree, geen codewijziging). Appcode: geen patches.
- Een geregistreerde wijziging binnen vendored code (mpvqt) moet apart geregistreerd worden; de vendoring-regel
  `desktop/external/mpvqt` dekt alleen de vervangen gitlink zelf.
