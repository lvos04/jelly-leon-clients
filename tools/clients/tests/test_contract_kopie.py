"""Drifttest: de contractkopie in deze repo is byte-gelijk aan de bron in `lvos04/ai-server-manager` (contract 1.2, A1).

Drie lagen (zelfde opzet als `tools/jelly-leon-web/contract_drift.py` in jelly-leon-web):
  1. altijd (ook in CI, waar de bronrepo niet naast deze repo staat): SHA-256 van beide kopieën is exact de vastgelegde
     hash van de bron op de vaste bron-commit `BRON_COMMIT` (`docs/platform-v2/` in ai-server-manager);
  2. als de bronrepo als git-checkout lokaal naast deze repo staat (of `JLC_CONTRACT_BRON` naar die checkout wijst):
     byte-vergelijking met `git show <BRON_COMMIT>:docs/platform-v2/<bestand>`. Een verschil faalt altijd (dan klopt
     de pin niet of is de kopie lokaal aangepast). Ontbreekt de bron of de commit, dan wordt alleen deze laag
     overgeslagen — nooit als geslaagd gemeld;
  3. wijkt de werkboom van die checkout af van de pin (de eigenaar heeft het contract na `BRON_COMMIT` gewijzigd, bv.
     contract 1.3), dan volgt een **waarschuwing**: een nieuwe contractstand overnemen is een bewuste stap van de
     orkestratie (byte-gelijk kopiëren, `BRON_COMMIT` en de hashes bijwerken; C1.3-JLC-01), geen rode test door werk
     in een andere repo. Deze taak volgt contract 1.2 (ADR-0011 van deze repo, slot).
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
#: ai-server-manager, laatste wijziging van beide bestanden onder contracts 1.2 (incl. review-correcties R1–R12).
BRON_COMMIT = "8b54f39408e25fd5c9b9e390d1bbacba52f0e584"
KOPIEEN = {
    "PLATFORM_CONTRACTEN.md": "6a9d29bd94fd991ac5d7876c1a5e51455d471c8bb2833dbed5c52c915b7df424",
    "CONTRACT_1.2_CONFORMITEIT.md": "6daedffb44a9506f97c7b9135f65393191a4b6247e96661a64c7a6fed5297f59",
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
            "orkestratie (byte-gelijk kopiëren, BRON_COMMIT en hash bijwerken; C1.3-JLC-01)")
    return fouten, waarschuwingen, True


@pytest.mark.parametrize("naam", sorted(KOPIEEN))
def test_kopie_heeft_de_vastgelegde_hash_van_de_bron(naam):
    data = (KOPIE_DIR / naam).read_bytes()
    assert hashlib.sha256(data).hexdigest() == KOPIEEN[naam], (
        f"{naam} wijkt af van de bron (ai-server-manager {BRON_COMMIT[:9]}); nooit lokaal aanpassen, opnieuw kopiëren")


def test_contract_is_versie_1_2():
    data = (KOPIE_DIR / "PLATFORM_CONTRACTEN.md").read_bytes()
    assert b"Versie: `contracts 1.2`" in data
    assert b"## 11. jelly-leon-clients" in (KOPIE_DIR / "CONTRACT_1.2_CONFORMITEIT.md").read_bytes()


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
    (bron / BRON_REL / "X.md").write_bytes(b"versie 1.2\n")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "1.2"], check=True)
    pin = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    kopie = tmp_path / "X.md"
    kopie.write_bytes(b"versie 1.2\n")
    assert vergelijk(kopie, bron, "X.md", pin) == ([], [], True)
    (bron / BRON_REL / "X.md").write_bytes(b"versie 1.3\n")  # de eigenaar werkt verder
    fouten, waarschuwingen, beoordeeld = vergelijk(kopie, bron, "X.md", pin)
    assert beoordeeld and not fouten and "gewijzigd" in waarschuwingen[0]
    kopie.write_bytes(b"versie 1.2 lokaal aangepast\n")
    assert vergelijk(kopie, bron, "X.md", pin)[0], "een lokaal aangepaste kopie moet falen"
    (bron / BRON_REL / "X.md").unlink()
    assert "niet (meer)" in vergelijk(kopie, bron, "X.md", pin)[1][0]
    assert vergelijk(kopie, bron, "X.md", "0" * 40)[2] is False  # pin ontbreekt: overslaan, nooit geslaagd
    monkeypatch.setenv("JLC_CONTRACT_BRON", str(bron / BRON_REL))
    assert bron_repo() == bron.resolve()
    monkeypatch.setenv("JLC_CONTRACT_BRON", str(tmp_path / "geen-repo"))
    assert bron_repo() is None
