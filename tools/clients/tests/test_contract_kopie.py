"""Drifttest: de contractkopieën in deze repo zijn byte-gelijk aan de bron in `lvos04/ai-server-manager`.

Contract 1.3, kop en C1.3-ALG-01/C1.3-JLC-01.

Drie lagen (zelfde opzet als `tools/jelly-leon-web/contract_drift.py` in jelly-leon-web):
  1. altijd (ook in CI, waar de bronrepo niet naast deze repo staat): SHA-256 van elke kopie is exact de vastgelegde
     hash van de bron op de vaste bron-commit `BRON_COMMIT` (`docs/platform-v2/` in ai-server-manager). Gekopieerd:
     `PLATFORM_CONTRACTEN.md` en `CONTRACT_1.3_CONFORMITEIT.md` (verplicht) en `CONTRACT_1.2_CONFORMITEIT.md` (historie,
     C1.3-ALG-01: "mag als historie blijven staan"; dan wel de stand van de bron op dezelfde commit);
  2. als de bronrepo als git-checkout lokaal naast deze repo staat (of `JLC_CONTRACT_BRON` naar die checkout wijst):
     byte-vergelijking met `git show <BRON_COMMIT>:docs/platform-v2/<bestand>`. Een verschil faalt altijd (dan klopt
     de pin niet of is de kopie lokaal aangepast). Ontbreekt de bron of de commit, dan wordt alleen deze laag
     overgeslagen — nooit als geslaagd gemeld;
  3. wijkt de werkboom van die checkout af van de pin (de eigenaar heeft het contract na `BRON_COMMIT` gewijzigd), dan
     volgt een **waarschuwing**: een nieuwe contractstand overnemen is een bewuste stap van de orkestratie (byte-gelijk
     kopiëren, `BRON_COMMIT` en de hashes bijwerken), geen rode test door werk in een andere repo.
Contract 1.3 in deze repo: ADR-0012.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import warnings
from pathlib import Path

import pytest
from clients_common import DEFAULT_REPO_ROOT

ROOT = Path(DEFAULT_REPO_ROOT)
KOPIE_DIR = ROOT / "docs" / "platform-v2"
BRON_REL = "docs/platform-v2"
#: ai-server-manager (branch ccr-c133d7a0-kuz1cv), laatste wijziging van de contractbestanden onder contracts 1.3,
#: inclusief de reviewcorrecties RV1–RV13 (ADR-0028 daar): "Contract 1.3: MediaGuard-overstap naar de publieke repo
#: gemeten (RV13)".
BRON_COMMIT = "02b119cb84be9a307a88532f6692ea8a4bcb12f1"
KOPIEEN = {
    "PLATFORM_CONTRACTEN.md": "15b30cf17f91b606451ef9c41f02327076ef76ce655ee94e40e3538106962310",
    "CONTRACT_1.3_CONFORMITEIT.md": "f0a2352ddb27088ae668013501c62a1eaaf879efe742a2d4422ffe8d33b43466",
    # historie (C1.3-ALG-01), dezelfde bron-commit; vervangt de stand van 1.2 (8b54f3940) door die van de bron nu
    "CONTRACT_1.2_CONFORMITEIT.md": "634941340afd2d9a55846076ab468ea4aacddb32dd8be6a7b92dd113661d39a4",
}


def bron_repo() -> Path | None:
    """Git-checkout van ai-server-manager (``JLC_CONTRACT_BRON`` mag naar de checkout of naar ``docs/platform-v2``
    daarin wijzen); ``None`` als er geen bruikbare checkout is."""
    kandidaat = os.environ.get("JLC_CONTRACT_BRON")
    pad = Path(kandidaat) if kandidaat else ROOT.parent / "ai-server-manager"
    if pad.name == "platform-v2" and pad.parent.name == "docs":
        pad = pad.parent.parent
    proc = subprocess.run(["git", "-C", str(pad), "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                          check=False)
    return Path(proc.stdout.strip()) if proc.returncode == 0 else None


def bron_op_pin(repo: Path, naam: str, pin: str = BRON_COMMIT) -> bytes | None:
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{pin}:{BRON_REL}/{naam}"], capture_output=True,
                          check=False)
    return proc.stdout if proc.returncode == 0 else None


def vergelijk(kopie: Path, repo: Path, naam: str, pin: str = BRON_COMMIT) -> tuple[list[str], list[str], bool]:
    """(fouten, waarschuwingen, beoordeeld): kopie ↔ bron op de pin (fout bij verschil) en bron op de pin ↔ werkboom
    van de bron (alleen een waarschuwing). ``beoordeeld`` is onwaar als de pin of het bestand in de bron ontbreekt."""
    bron = bron_op_pin(repo, naam, pin)
    if bron is None:
        return [], [], False
    fouten = [] if kopie.read_bytes() == bron else [
        f"{naam}: kopie is niet byte-gelijk aan ai-server-manager@{pin[:9]} — opnieuw kopiëren"]
    actueel = repo / BRON_REL / naam
    waarschuwingen = []
    if not actueel.is_file():
        waarschuwingen.append(f"{naam} staat niet (meer) in de werkboom van {repo} — contractstand nagaan")
    elif actueel.read_bytes() != bron:
        waarschuwingen.append(
            f"{naam}: de bron in {repo} is na {pin[:9]} gewijzigd — nieuwe contractstand overnemen is een stap van de "
            "orkestratie (byte-gelijk kopiëren, BRON_COMMIT en hash bijwerken)")
    return fouten, waarschuwingen, True


@pytest.mark.parametrize("naam", sorted(KOPIEEN))
def test_kopie_heeft_de_vastgelegde_hash_van_de_bron(naam):
    data = (KOPIE_DIR / naam).read_bytes()
    assert hashlib.sha256(data).hexdigest() == KOPIEEN[naam], (
        f"{naam} wijkt af van de bron (ai-server-manager {BRON_COMMIT[:9]}); nooit lokaal aanpassen, opnieuw kopiëren")


def test_contract_is_versie_1_3_met_de_punten_voor_deze_repo():
    data = (KOPIE_DIR / "PLATFORM_CONTRACTEN.md").read_bytes()
    assert b"Versie: `contracts 1.3`" in data
    conformiteit = (KOPIE_DIR / "CONTRACT_1.3_CONFORMITEIT.md").read_bytes()
    assert b"## 11. jelly-leon-clients" in conformiteit
    for punt in (b"C1.3-JLC-01", b"C1.3-JLC-02", b"C1.3-JLC-03"):
        assert punt in conformiteit, punt


def test_elke_contractkopie_in_de_map_is_gepind():
    """Een contract- of conformiteitsbestand in docs/platform-v2 zonder pin zou stil verouderen."""
    gevonden = {p.name for p in KOPIE_DIR.glob("*.md")
                if p.name == "PLATFORM_CONTRACTEN.md" or p.name.startswith("CONTRACT_")}
    assert gevonden == set(KOPIEEN), sorted(gevonden ^ set(KOPIEEN))


@pytest.mark.parametrize("naam", sorted(KOPIEEN))
def test_kopie_is_byte_gelijk_aan_de_bron_op_de_pin(naam):
    repo = bron_repo()
    if repo is None:
        pytest.skip("geen git-checkout van ai-server-manager naast deze repo (zet JLC_CONTRACT_BRON); alleen de hash "
                    "is gecontroleerd")
    fouten, waarschuwingen, beoordeeld = vergelijk(KOPIE_DIR / naam, repo, naam)
    if not beoordeeld:
        pytest.skip(f"commit {BRON_COMMIT[:9]} of {BRON_REL}/{naam} ontbreekt in {repo} (ondiepe clone?); alleen de "
                    "hash is gecontroleerd")
    assert not fouten, fouten
    for w in waarschuwingen:
        warnings.warn(w, stacklevel=1)


def test_drift_ten_opzichte_van_de_pin_faalt_en_nieuwere_bron_waarschuwt(tmp_path, monkeypatch):
    """Negatief, met een nep-bronrepo (zonder netwerk): een kopie die niet gelijk is aan de bron op de pin faalt; een
    nieuwere werkboom van de bron geeft alleen een waarschuwing; geen checkout of geen pin = niet beoordeeld."""
    bron = tmp_path / "ai-server-manager"
    (bron / BRON_REL).mkdir(parents=True)
    git = ["git", "-C", str(bron), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    (bron / BRON_REL / "X.md").write_bytes(b"versie 1.3\n")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "1.3"], check=True)
    pin = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    kopie = tmp_path / "X.md"
    kopie.write_bytes(b"versie 1.3\n")
    assert vergelijk(kopie, bron, "X.md", pin) == ([], [], True)
    (bron / BRON_REL / "X.md").write_bytes(b"versie 1.4\n")  # de eigenaar werkt verder
    fouten, waarschuwingen, beoordeeld = vergelijk(kopie, bron, "X.md", pin)
    assert beoordeeld and not fouten and "gewijzigd" in waarschuwingen[0]
    kopie.write_bytes(b"versie 1.3 lokaal aangepast\n")
    assert vergelijk(kopie, bron, "X.md", pin)[0], "een lokaal aangepaste kopie moet falen"
    (bron / BRON_REL / "X.md").unlink()
    assert "niet (meer)" in vergelijk(kopie, bron, "X.md", pin)[1][0]
    assert vergelijk(kopie, bron, "X.md", "0" * 40)[2] is False  # pin ontbreekt: overslaan, nooit geslaagd
    monkeypatch.setenv("JLC_CONTRACT_BRON", str(bron / BRON_REL))
    assert bron_repo() == bron.resolve()
    monkeypatch.setenv("JLC_CONTRACT_BRON", str(tmp_path / "geen-repo"))
    assert bron_repo() is None
