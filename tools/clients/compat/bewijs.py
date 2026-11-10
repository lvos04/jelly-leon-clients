"""Bewijsdocument van de compatibiliteitstests: herkomst, uitkomst per stap en de vergelijking met stock.

Er komen geen tokens, wachtwoorden of sleutels in (``controleer_geen_geheimen`` weigert het document anders); de
testaccounts staan er alleen met naam in. Validatielabels volgen contract §11: Sim-geslaagd/Sim-mislukt per client;
echte apparaten NIET GEVALIDEERD (hardware), Swiftfin NIET GEVALIDEERD (Mac/Xcode).
"""

from __future__ import annotations

import fcntl
import json
import re
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .scenario import GESLAAGD, MISLUKT

LOCKS = Path("/home/transcode/truenas-v2/.lokaal")
GEHEIM_RE = re.compile(r'^AccessToken$|Token="[^"]+"|(?:api_key|ApiKey)=[0-9a-fA-F]{16,}')
NIET_HIER = [
    {
        "client": "Swiftfin 1.6.1 (iOS/tvOS), Safari, Apple TV",
        "rol": "stock-native / fork-app",
        "status": "NIET GEVALIDEERD (Mac/Xcode)",
        "reden": "geen Mac/Xcode; statische herbeoordeling in ADR-0009",
    },
    {
        "client": "echte telefoons, tablets, tv's, Chromecast, DLNA",
        "rol": "alle",
        "status": "NIET GEVALIDEERD (hardware)",
        "reden": "geen echte apparaten; D15 onbekend (JLT-69)",
    },
]


def nu() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def slot(naam: str, log: Any = print) -> Iterator[float]:
    """Machinebreed slot met flock (wacht netjes); levert de wachttijd in seconden."""
    pad = LOCKS / naam
    t0 = time.monotonic()
    with pad.open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log(f"wacht op {naam} …")
            fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield round(time.monotonic() - t0, 1)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def vergelijk(jelly_leon: dict[str, Any], stock: dict[str, Any]) -> list[dict[str, Any]]:
    """Per stap: uitkomst tegen Jelly Leon en tegen stock. Regressie = geslaagd op stock en mislukt op Jelly Leon."""
    uit = []
    for stap in sorted(set(jelly_leon) | set(stock)):
        jl = jelly_leon.get(stap, {}).get("uitkomst")
        st = stock.get(stap, {}).get("uitkomst")
        uit.append(
            {
                "stap": stap,
                "jelly_leon": jl,
                "stock": st,
                "regressie": st == GESLAAGD and jl == MISLUKT,
                "gelijk": jl == st,
            }
        )
    return uit


def controleer_geen_geheimen(document: dict[str, Any], geheimen: list[str] | None = None) -> None:
    """Weigert een document met een token-vorm of met een bekende geheime waarde (wachtwoorden van de testaccounts)."""
    for tekst in _teksten(document):
        treffer = GEHEIM_RE.search(tekst)
        if treffer:
            raise ValueError(f"bewijs bevat mogelijk een token ({treffer.group(0)[:12]}…); niet geschreven")
        if any(g and g in tekst for g in geheimen or []):
            raise ValueError("bewijs bevat een wachtwoord of sleutel; niet geschreven")


def _teksten(waarde: Any) -> Iterator[str]:
    """Alle sleutels en tekstwaarden (onge-escapet), recursief."""
    if isinstance(waarde, dict):
        for k, v in waarde.items():
            yield str(k)
            yield from _teksten(v)
    elif isinstance(waarde, list | tuple):
        for v in waarde:
            yield from _teksten(v)
    elif isinstance(waarde, str):
        yield waarde


def schrijf(pad: Path, document: dict[str, Any], geheimen: list[str] | None = None) -> None:
    controleer_geen_geheimen(document, geheimen)
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def comprimeer_schermafdrukken(map_: Path, behoud: tuple[str, ...] = ("jelly-leon-",)) -> list[str]:
    """PNG → JPEG (hoogte ≤ 720 px) voor de repo; schermafdrukken van de controlegroep (stock) vervallen: hun uitkomst
    staat in het bewijs-JSON. Geeft de bewaarde bestandsnamen."""
    bewaard = []
    for png in sorted(map_.glob("*.png")):
        if png.name.startswith(behoud):
            jpg = png.with_suffix(".jpg")
            r = subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(png),
                    "-vf",
                    "scale=-2:'min(720,ih)'",
                    "-q:v",
                    "5",
                    str(jpg),
                ],
                capture_output=True,
                check=False,
            )
            if r.returncode == 0:
                bewaard.append(jpg.name)
        png.unlink()
    return bewaard
