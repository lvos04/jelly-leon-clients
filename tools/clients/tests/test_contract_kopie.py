"""Drifttest: de contractkopie in deze repo is byte-gelijk aan de bron in `lvos04/ai-server-manager` (contract 1.2, A1).

Twee lagen:
  1. altijd (ook in CI, waar de bronrepo niet naast deze repo staat): SHA-256 van beide kopieën is exact de vastgelegde
     hash van de bron op bron-commit 8b54f39 (`docs/platform-v2/` in ai-server-manager);
  2. als de bronrepo lokaal naast deze repo staat (of `JLC_CONTRACT_BRON` naar die map wijst): byte-vergelijking met de
     actuele bron. Verandert de eigenaar het contract, dan faalt deze test tot de kopie (en de hash) is bijgewerkt.
     Ontbreekt de bron, dan wordt alleen deze laag overgeslagen — nooit als geslaagd gemeld.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from clients_common import DEFAULT_REPO_ROOT

ROOT = Path(DEFAULT_REPO_ROOT)
KOPIE_DIR = ROOT / "docs" / "platform-v2"
BRON_COMMIT = "8b54f39"  # ai-server-manager, laatste wijziging van beide bestanden
KOPIEEN = {
    "PLATFORM_CONTRACTEN.md": "6a9d29bd94fd991ac5d7876c1a5e51455d471c8bb2833dbed5c52c915b7df424",
    "CONTRACT_1.2_CONFORMITEIT.md": "6daedffb44a9506f97c7b9135f65393191a4b6247e96661a64c7a6fed5297f59",
}


def bron_dir() -> Path | None:
    kandidaat = os.environ.get("JLC_CONTRACT_BRON")
    pad = Path(kandidaat) if kandidaat else ROOT.parent / "ai-server-manager" / "docs" / "platform-v2"
    return pad if (pad / "PLATFORM_CONTRACTEN.md").is_file() else None


@pytest.mark.parametrize("naam", sorted(KOPIEEN))
def test_kopie_heeft_de_vastgelegde_hash_van_de_bron(naam):
    data = (KOPIE_DIR / naam).read_bytes()
    assert hashlib.sha256(data).hexdigest() == KOPIEEN[naam], (
        f"{naam} wijkt af van de bron (ai-server-manager {BRON_COMMIT}); nooit lokaal aanpassen, opnieuw kopiëren")


def test_contract_is_versie_1_2():
    data = (KOPIE_DIR / "PLATFORM_CONTRACTEN.md").read_bytes()
    assert b"Versie: `contracts 1.2`" in data
    assert b"## 11. jelly-leon-clients" in (KOPIE_DIR / "CONTRACT_1.2_CONFORMITEIT.md").read_bytes()


@pytest.mark.parametrize("naam", sorted(KOPIEEN))
def test_kopie_is_byte_gelijk_aan_de_lokale_bron(naam):
    bron = bron_dir()
    if bron is None:
        pytest.skip("bronrepo ai-server-manager staat niet naast deze repo (zet JLC_CONTRACT_BRON); alleen de hash "
                    "is gecontroleerd")
    assert (KOPIE_DIR / naam).read_bytes() == (bron / naam).read_bytes(), (
        f"{naam}: de bron in {bron} is veranderd — kopie byte-gelijk overnemen, hash en BRON_COMMIT bijwerken")
