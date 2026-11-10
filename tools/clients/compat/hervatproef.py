"""Herhaalproef 'hervatten op het juiste punt' (HARDE EIS kijkgeschiedenis; JLT-63, B03-019).

Eén emulator en één verse server per servervariant; na het inloggen wordt het hervatten met de eigen knop van de app
``n`` keer herhaald: hervatpunt terug op 300 s zetten (zoals een overgenomen kijkpunt), detailpagina openen
(DisplayContent), op *Resume* drukken, de gemelde posities volgen en stoppen. Zo is te zien of een afwijking bij het
hervatten aan de server ligt (alleen op Jelly Leon) of aan de app (ook op stock).

    python3 tools/clients/client_compat.py hervatproef --image <jelly-leon-image> [--soort tv] [--bediend officieel]
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from . import scenario as sc
from .android import CLIENTNAAM, Volger, dpad_kies, inloggen_telefoon, inloggen_tv, log, stop
from .emulator import AVDS, Emulator
from .jfapi import TICKS
from .server import TestServer


def herhaal(server: TestServer, soort: str, apks: dict[str, Any], bediend: str, n: int) -> dict[str, Any]:
    assert server.jf
    jf, it = server.jf, server.items
    app = AVDS[soort]["app"]
    doel = apks[app]["fork" if bediend == "fork" else "officieel"]
    emu = Emulator(soort, Path(apks[app]["fork"]["pad"]).parent)
    volger = Volger(jf, CLIENTNAAM[app])
    uit: dict[str, Any] = {
        "emulator": soort,
        "bediend": bediend,
        "pakket": doel["pakket"],
        "gevraagd": n,
        "pogingen": [],
    }
    try:
        uit["boot_s"] = round(emu.start(), 1)
        emu.installeer(Path(apks[app]["officieel"]["pad"]))
        emu.installeer(Path(apks[app]["fork"]["pad"]))
        login = (inloggen_telefoon if app == "android" else inloggen_tv)(
            emu, doel["pakket"], f"http://10.0.2.2:{server.poort}"
        )
        uit["inloggen"] = login["uitkomst"]
        knop_patroon = r"^Resume$" if app == "android" else r"^Resume from"
        for i in range(n if login["uitkomst"] == sc.GESLAAGD else 0):
            try:
                jf.zet_userdata(
                    server.kijker_id, it.hervat["Id"], {"PlaybackPositionTicks": int(server.HERVAT_S * TICKS)}
                )
                jf.toon(volger.id(), it.hervat)
                knop = emu.wacht_op(knop_patroon, timeout=30)
                if knop is None:
                    uit["pogingen"].append({"poging": i + 1, "uitkomst": sc.MISLUKT, "reden": "geen hervatknop"})
                    continue
                if app == "android":
                    emu.tik(knop)
                else:
                    dpad_kies(emu, knop_patroon)
                monsters = volger.volg(it.hervat["Id"], 25, minimaal_s=6)
                uit["pogingen"].append(
                    {"poging": i + 1, **sc.beoordeel_hervatten(monsters, it.hervat["Id"], server.HERVAT_S)}
                )
                stop(emu, app, jf, {}, volger)
            except Exception as fout:  # noqa: BLE001 - een harnas- of appfout telt als mislukte poging, nooit stil
                uit["pogingen"].append(
                    {"poging": i + 1, "uitkomst": sc.MISLUKT, "reden": f"{type(fout).__name__}: {str(fout)[:300]}"}
                )
            time.sleep(2)
            log(f"hervatproef {soort} poging {i + 1}: {uit['pogingen'][-1]['uitkomst']}")
    finally:
        uit["geheugen"] = emu.geheugen()
        emu.stop()
    # n = het gevraagde aantal: een niet uitgevoerde poging (bv. inloggen mislukt) telt nooit als geslaagd.
    uit["geslaagd"] = sum(p["uitkomst"] == sc.GESLAAGD for p in uit["pogingen"])
    uit["n"] = n
    return uit
