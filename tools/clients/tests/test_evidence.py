"""Vorm en eerlijkheid van docs/platform-v2/EVIDENCE.json (contract 1.3 §11; C1.3-JLC-03).

Bewaakt per regel (`fouten_in_regel`, met tegenproeven hieronder):
- exact de velden uit §11, `repo` = deze repo, `bijgewerkt` een echte datum, een niet-leeg `bewijs`;
- `status` uit de Excel-lijst van het soort ID: Testmatrix (`EX..`, `JLT-..`), Besluiten (`D..`) of Werkpakketten (de
  rest, ook contractpunten `C1.3-…`/`C1.2-…` en reviews `REVIEW-jelly-leon-clients-…`); nooit `Gereed` of `Geslaagd`
  (die vragen echte acceptatie op de NAS, in deze bouwomgeving onmogelijk);
- `validatie`: nooit leeg; één of meer waarden uit de vaste lijst van 1.3, gescheiden door precies `"; "`, zonder
  dubbele; `Sim-geslaagd`/`Sim-mislukt` alleen bij Testmatrix-ID's en nooit samen; `Niet getest` (nieuw in 1.3) alleen
  bij status `Niet gestart` en niet naast een testuitkomst;
- elke `NIET GEVALIDEERD (…)` in `blokkade` is een waarde uit de vaste lijst en staat ook in `validatie` (nieuw in 1.3);
- `Geblokkeerd` heeft een blokkade.
Over alle regels: ID's uniek; Excel-ID's staan in de eigen takenlijst of de pakketdocs; contractpunten bestaan in de
conformiteitslijst van hun versie; reviews hebben de vaste vorm; commits in het bewijs bestaan in deze repo.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from pathlib import Path

import pytest
from clients_common import DEFAULT_REPO_ROOT

ROOT = Path(DEFAULT_REPO_ROOT)
REPO = "jelly-leon-clients"
PV2 = ROOT / "docs/platform-v2"
EVIDENCE = PV2 / "EVIDENCE.json"
TAKEN = PV2 / "EXCEL_TAKEN.json"
VELDEN = {"id", "status", "validatie", "bewijs", "blokkade", "opmerking", "repo", "bijgewerkt"}
WERKPAKKET = {"Niet gestart", "Bezig", "Geblokkeerd", "N.v.t."}  # "Gereed" bewust niet
TESTMATRIX = {"Niet gestart", "Bezig", "Mislukt", "Geblokkeerd", "N.v.t."}  # "Geslaagd" bewust niet
BESLUIT = {"Open", "Ingevuld", "Getest", "Geblokkeerd", "N.v.t."}
NOOIT = {"Gereed", "Geslaagd"}
SIM_UITKOMST = {"Sim-geslaagd", "Sim-mislukt"}  # alleen Testmatrix
NIET_GETEST = "Niet getest"  # nieuw in 1.3, alleen bij "Niet gestart"
VALIDATIE = {
    "Sim-getest", "Unit-getest", *SIM_UITKOMST,
    "Intel-iGPU-getest (ontwikkelmachine)",  # nieuw in 1.3
    "NIET GEVALIDEERD (echte NAS)", "NIET GEVALIDEERD (hardware)", "NIET GEVALIDEERD (account)",
    "NIET GEVALIDEERD (Mac/Xcode)",
    NIET_GETEST,
}
SCHEIDING = "; "
TESTMATRIX_ID = re.compile(r"(?:EX\d{2}|JLT-\d{2})")
BESLUIT_ID = re.compile(r"D\d{2}")
CONTRACTPUNT_ID = re.compile(r"C1\.(?P<versie>[23])-(?P<code>[A-Z0-9]+(?:-\d{2})?)")
REVIEW_ID = re.compile(rf"REVIEW-{REPO}-[a-z0-9][a-z0-9.-]*")
NIET_GEVALIDEERD = re.compile(r"NIET GEVALIDEERD \([^)]*\)")
COMMIT_RE = re.compile(r"\bcommits?\s+([0-9a-f]{7,40})\b")


def records() -> list[dict]:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data, "EVIDENCE.json hoort een niet-lege lijst te zijn"
    return data


def soort(evidence_id: str) -> str:
    if TESTMATRIX_ID.fullmatch(evidence_id):
        return "testmatrix"
    if BESLUIT_ID.fullmatch(evidence_id):
        return "besluit"
    return "werkpakket"


def toegestane_statussen(evidence_id: str) -> set[str]:
    return {"testmatrix": TESTMATRIX, "besluit": BESLUIT, "werkpakket": WERKPAKKET}[soort(evidence_id)]


def fouten_in_regel(rec: dict) -> list[str]:
    """Alle overtredingen van §11 (1.3) in één EVIDENCE-regel; leeg = in orde."""
    rid = str(rec.get("id", "?"))
    if set(rec) != VELDEN:
        return [f"{rid}: velden wijken af: {sorted(set(rec) ^ VELDEN)}"]
    if not all(isinstance(rec[v], str) for v in VELDEN):
        return [f"{rid}: elk veld is tekst"]
    out: list[str] = []
    if rec["repo"] != REPO:
        out.append(f"{rid}: repo {rec['repo']!r}, verwacht {REPO!r}")
    try:
        date.fromisoformat(rec["bijgewerkt"])
    except ValueError:
        out.append(f"{rid}: bijgewerkt {rec['bijgewerkt']!r} is geen datum JJJJ-MM-DD")
    status = rec["status"]
    if status in NOOIT:
        out.append(f"{rid}: {status} vraagt echte acceptatie op de NAS en wordt hier nooit gezet")
    elif status not in toegestane_statussen(rid):
        out.append(f"{rid}: status {status!r} hoort niet bij een {soort(rid)}-ID")
    if not rec["bewijs"].strip():
        out.append(f"{rid}: geen bewijs")
    if status == "Geblokkeerd" and not rec["blokkade"].strip():
        out.append(f"{rid}: Geblokkeerd zonder blokkade")

    validatie = rec["validatie"]
    if not validatie.strip():
        return [*out, f"{rid}: lege validatie is nooit toegestaan"]
    waarden = validatie.split(SCHEIDING)
    for w in waarden:
        if w not in VALIDATIE:
            out.append(f"{rid}: validatie {w!r} staat niet in de vaste lijst (scheiding precies '; ', toelichting in "
                       "'opmerking')")
    if len(waarden) != len(set(waarden)):
        out.append(f"{rid}: validatie bevat een waarde dubbel")
    if soort(rid) != "testmatrix" and SIM_UITKOMST & set(waarden):
        out.append(f"{rid}: Sim-geslaagd/Sim-mislukt hoort alleen bij Testmatrix-ID's (EX.., JLT-..); hier Sim-getest")
    if set(waarden) >= SIM_UITKOMST:
        out.append(f"{rid}: tegelijk Sim-geslaagd en Sim-mislukt (kies één uitkomst)")
    if NIET_GETEST in waarden:
        if status != "Niet gestart":
            out.append(f"{rid}: 'Niet getest' alleen bij status 'Niet gestart' (nu {status!r})")
        getest = [w for w in waarden if w != NIET_GETEST and not w.startswith("NIET GEVALIDEERD")]
        if getest:
            out.append(f"{rid}: 'Niet getest' naast een testuitkomst {getest}")
    for gevonden in dict.fromkeys(NIET_GEVALIDEERD.findall(rec["blokkade"])):
        if gevonden not in VALIDATIE:
            out.append(f"{rid}: blokkade noemt {gevonden!r}, geen waarde uit de vaste lijst")
        elif gevonden not in waarden:
            out.append(f"{rid}: blokkade noemt {gevonden!r}, maar validatie niet")
    return out


@pytest.mark.parametrize("rec", records(), ids=lambda r: r.get("id", "?"))
def test_regel_volgt_paragraaf_11(rec):
    assert fouten_in_regel(rec) == []


def test_ids_uniek_en_bekend():
    ids = [r["id"] for r in records()]
    assert len(ids) == len(set(ids)), "dubbele ID's"
    eigen = {t["ID"] for t in json.loads(TAKEN.read_text(encoding="utf-8"))}
    conformiteit = {v: (PV2 / f"CONTRACT_1.{v}_CONFORMITEIT.md").read_text(encoding="utf-8") for v in ("2", "3")}
    pakket = "\n".join(p.read_text(encoding="utf-8") for p in PV2.rglob("*.md"))
    for evidence_id in ids:
        if evidence_id.startswith("REVIEW-"):
            assert REVIEW_ID.fullmatch(evidence_id), f"{evidence_id}: vorm REVIEW-{REPO}-<onderwerp>"
            continue
        punt = CONTRACTPUNT_ID.fullmatch(evidence_id)
        if evidence_id.startswith("C1."):
            assert punt, f"{evidence_id}: vorm C1.3-<code>-<nn> of C1.2-<code>"
            assert re.search(rf"(?<![\w.-]){re.escape(evidence_id)}(?![\w-])", conformiteit[punt["versie"]]), (
                f"{evidence_id}: staat niet in CONTRACT_1.{punt['versie']}_CONFORMITEIT.md")
            continue
        assert evidence_id in eigen or re.search(rf"\b{re.escape(evidence_id)}\b", pakket), (
            f"{evidence_id}: staat niet in EXCEL_TAKEN.json of de pakketdocs")


def test_genoemde_commits_bestaan():
    for rec in records():
        for sha in COMMIT_RE.findall(rec["bewijs"]):
            proc = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{sha}^{{commit}}"],
                                  capture_output=True, check=False)
            assert proc.returncode == 0, f"{rec['id']}: commit {sha} bestaat niet in deze repo"


# ------------------------------------------------------------------------------- tegenproeven op de regelcontrole


def regel(**kw) -> dict:
    basis = {"id": "B03-001", "status": "Bezig", "validatie": "Sim-getest", "bewijs": "commit abc1234",
             "blokkade": "", "opmerking": "", "repo": REPO, "bijgewerkt": "2026-11-10"}
    return {**basis, **kw}


def test_geldige_regels_van_elk_soort():
    assert fouten_in_regel(regel()) == []
    assert fouten_in_regel(regel(id="JLT-63", validatie="Sim-geslaagd; NIET GEVALIDEERD (hardware)",
                                 blokkade="Echte tv's: NIET GEVALIDEERD (hardware).")) == []
    assert fouten_in_regel(regel(id="EX48", status="Mislukt", validatie="Sim-mislukt")) == []
    assert fouten_in_regel(regel(id="D15", status="Open", validatie="NIET GEVALIDEERD (hardware)")) == []
    assert fouten_in_regel(regel(id="C1.3-JLC-02", validatie="Unit-getest; NIET GEVALIDEERD (Mac/Xcode)")) == []
    assert fouten_in_regel(regel(id="B03-077", status="Niet gestart", validatie="Niet getest")) == []
    assert fouten_in_regel(regel(validatie="Intel-iGPU-getest (ontwikkelmachine); NIET GEVALIDEERD (hardware)")) == []


@pytest.mark.parametrize(("wijziging", "melding"), [
    ({"status": "Gereed"}, "nooit gezet"),
    ({"id": "JLT-60", "status": "Geslaagd", "validatie": "Sim-geslaagd"}, "nooit gezet"),
    ({"status": "Mislukt"}, "hoort niet bij een werkpakket-ID"),
    ({"id": "D15", "status": "Bezig"}, "hoort niet bij een besluit-ID"),
    ({"validatie": ""}, "lege validatie"),
    ({"validatie": "  "}, "lege validatie"),
    ({"validatie": "Sim-getest;NIET GEVALIDEERD (hardware)"}, "scheiding precies"),
    ({"validatie": "Sim-getest, met emulator"}, "vaste lijst"),
    ({"validatie": "Sim-getest; Sim-getest"}, "dubbel"),
    ({"validatie": "Sim-geslaagd"}, "alleen bij Testmatrix"),
    ({"id": "JLT-63", "validatie": "Sim-geslaagd; Sim-mislukt"}, "tegelijk Sim-geslaagd en Sim-mislukt"),
    ({"validatie": "Niet getest"}, "alleen bij status 'Niet gestart'"),
    ({"id": "D15", "status": "Open", "validatie": "Niet getest"}, "alleen bij status 'Niet gestart'"),
    ({"status": "Niet gestart", "validatie": "Niet getest; Sim-getest"}, "naast een testuitkomst"),
    ({"blokkade": "Echte apparaten: NIET GEVALIDEERD (hardware)."}, "maar validatie niet"),
    ({"validatie": "Sim-getest; NIET GEVALIDEERD (hardware)",
      "blokkade": "NIET GEVALIDEERD (echte NAS/hardware)"}, "geen waarde uit de vaste lijst"),
    ({"status": "Geblokkeerd"}, "zonder blokkade"),
    ({"bewijs": " "}, "geen bewijs"),
    ({"repo": "jelly-leon"}, "verwacht 'jelly-leon-clients'"),
    ({"bijgewerkt": "10-11-2026"}, "geen datum"),
])
def test_overtredingen_worden_gevonden(wijziging, melding):
    gevonden = fouten_in_regel(regel(**wijziging))
    assert any(melding in f for f in gevonden), gevonden


def test_extra_of_ontbrekend_veld_faalt():
    assert "velden wijken af" in fouten_in_regel({**regel(), "extra": "x"})[0]
    zonder = regel()
    del zonder["opmerking"]
    assert "velden wijken af" in fouten_in_regel(zonder)[0]
