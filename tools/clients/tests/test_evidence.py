"""Vorm en eerlijkheid van docs/platform-v2/EVIDENCE.json (contract §11).

Bewaakt: exact de velden uit §11, alleen statussen uit de Excel-lijst van het juiste soort ID, nooit `Gereed` of
`Geslaagd` (die vragen echte acceptatie op de NAS), alleen toegestane validatiewaarden (meerdere met "; "), ID's die
in de eigen takenlijst of de pakketdocs voorkomen, en commits in het bewijs die echt bestaan.
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
EVIDENCE = ROOT / "docs/platform-v2/EVIDENCE.json"
TAKEN = ROOT / "docs/platform-v2/EXCEL_TAKEN.json"
VELDEN = {"id", "status", "validatie", "bewijs", "blokkade", "opmerking", "repo", "bijgewerkt"}
WERKPAKKET = {"Niet gestart", "Bezig", "Geblokkeerd", "N.v.t."}  # "Gereed" bewust niet
TESTMATRIX = {"Niet gestart", "Bezig", "Mislukt", "Geblokkeerd", "N.v.t."}  # "Geslaagd" bewust niet
BESLUIT = {"Open", "Ingevuld", "Getest", "Geblokkeerd", "N.v.t."}
VALIDATIE = {
    "Sim-getest", "Unit-getest", "Sim-geslaagd", "Sim-mislukt",
    "NIET GEVALIDEERD (echte NAS)", "NIET GEVALIDEERD (hardware)", "NIET GEVALIDEERD (account)",
    "NIET GEVALIDEERD (Mac/Xcode)",
}
COMMIT_RE = re.compile(r"\bcommits?\s+([0-9a-f]{7,40})\b")


def records() -> list[dict]:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data, "EVIDENCE.json hoort een niet-lege lijst te zijn"
    return data


def toegestane_statussen(evidence_id: str) -> set[str]:
    if re.fullmatch(r"EX\d{2}", evidence_id):
        return TESTMATRIX
    if re.fullmatch(r"D\d{2}", evidence_id):
        return BESLUIT
    return WERKPAKKET


@pytest.mark.parametrize("rec", records(), ids=lambda r: r.get("id", "?"))
def test_velden_status_en_validatie(rec):
    assert set(rec) == VELDEN, f"{rec.get('id')}: velden {sorted(set(rec) ^ VELDEN)}"
    assert rec["repo"] == "jelly-leon-clients"
    date.fromisoformat(rec["bijgewerkt"])
    assert rec["status"] not in {"Gereed", "Geslaagd"}, f"{rec['id']}: Gereed/Geslaagd vraagt echte acceptatie"
    assert rec["status"] in toegestane_statussen(rec["id"]), f"{rec['id']}: status {rec['status']!r}"
    waarden = [w.strip() for w in rec["validatie"].split(";")]
    assert waarden and all(w in VALIDATIE for w in waarden), f"{rec['id']}: validatie {rec['validatie']!r}"
    if rec["status"] == "Geblokkeerd":
        assert rec["blokkade"].strip(), f"{rec['id']}: Geblokkeerd zonder blokkade"
    assert rec["bewijs"].strip(), f"{rec['id']}: geen bewijs"


def test_ids_uniek_en_bekend():
    ids = [r["id"] for r in records()]
    assert len(ids) == len(set(ids)), "dubbele ID's"
    eigen = {t["ID"] for t in json.loads(TAKEN.read_text(encoding="utf-8"))}
    pakket = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "docs/platform-v2").rglob("*.md"))
    for evidence_id in ids:
        assert evidence_id in eigen or re.search(rf"\b{re.escape(evidence_id)}\b", pakket), (
            f"{evidence_id}: staat niet in EXCEL_TAKEN.json of de pakketdocs")


def test_genoemde_commits_bestaan():
    for rec in records():
        for sha in COMMIT_RE.findall(rec["bewijs"]):
            proc = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{sha}^{{commit}}"],
                                  capture_output=True, check=False)
            assert proc.returncode == 0, f"{rec['id']}: commit {sha} bestaat niet in deze repo"
