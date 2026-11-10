"""jellyfin-desktop 2.0.0 onder Xvfb in een container tegen de Jelly Leon 12.x-server (P4-0, JC3; B03 §10.14).

De app is uit ``desktop/`` gebouwd met de bouwomgeving van deze repo (``make desktop-bouw``, Release) en draait in het
doel ``test`` van ``bouwverificatie/desktop.Dockerfile`` (Xvfb en de QML-runtimemodules uit ``debian/control``), als
niet-root, zonder capabilities, met de build alleen-lezen, op het hostnetwerk (alleen 127.0.0.1) en met
``--shm-size 1g``. Besturing via ruwe CDP (``desktop_cdp.mjs``); afspelen gaat via libmpv, dus beoordeeld wordt wat de
server ziet en het beeld komt van het X-scherm (``xwd``).

Gemeten oorzaak van de eerdere blokkade (jelly-leon B03-016, desktop-spike): met de standaard ``/dev/shm`` van Docker
(64 MiB) laadt QtWebEngine de web-client van de server niet (``net::ERR_INSUFFICIENT_RESOURCES`` op elke bundle) en
blijft de app op ``find-webclient.html`` hangen. Met ``--shm-size 1g`` werkt het (ADR-0011 van deze repo).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from . import bewijs
from . import scenario as sc
from .android import Volger, log
from .jfapi import TICKS
from .server import BEHEER_WW, KIJKER, KIJKER_WW, TestServer, docker

IMAGE = os.environ.get("JLC_DESKTOP_IMAGE", "jelly-leon-clients/desktop-test:dev")
NAAM = "jlc-jc3-desktop"
CDP_JS = Path(__file__).resolve().parent / "desktop_cdp.mjs"
CLIENT = "Jellyfin Desktop"
VEREIST = [
    "inloggen",
    "bladeren",
    "hervatten",
    "hervatpunt_bewaard",
    "direct_play",
    "transcode",
    "ondertitel_voorkeur",
    "ondertitel_extern",
]
# Instellingen → Afspelen → maximale streamingbitrate (appSettings van de web-client): 400 kbit/s in het thuisnetwerk.
LAGE_BITRATE = {"enableautobitratebitrate-Video-true": "false", "maxbitrate-Video-true": "400000"}


def vrije_poort() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Desktop:
    def __init__(self, build: Path) -> None:
        self.build = build
        self.poort = vrije_poort()
        self.cid = ""

    def start(self) -> None:
        docker("rm", "-f", NAAM, check=False)
        self.cid = docker(
            "run",
            "-d",
            "--name",
            NAAM,
            "--network",
            "host",
            "--shm-size",
            "1g",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--memory",
            "3g",
            "--cpus",
            "4",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "-e",
            "HOME=/tmp",
            "-v",
            f"{self.build}:/out:ro",
            IMAGE,
            "sh",
            "-c",
            "Xvfb :99 -screen 0 1600x900x24 >/tmp/xvfb.log 2>&1 & sleep 2; DISPLAY=:99 "
            "QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox /out/build/src/jellyfin-desktop "
            f"--remote-debugging-port {self.poort} > /tmp/app.log 2>&1",
        ).stdout.strip()
        for _ in range(60):
            if self.cdp("doelen").get("doelen"):
                return
            time.sleep(2)
        raise RuntimeError("CDP antwoordt niet: " + self.log(20))

    def cdp(self, actie: str, timeout: float = 150, **velden: Any) -> dict[str, Any]:
        cfg = json.dumps({"poort": self.poort, "actie": actie, **velden})
        try:
            r = subprocess.run(["node", str(CDP_JS), cfg], capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return {"ok": False, "fout": f"CDP-actie {actie} liep vast"}
        regels = r.stdout.strip().splitlines()
        try:
            return json.loads(regels[-1]) if regels else {"ok": False, "fout": r.stderr[-300:]}
        except ValueError:
            return {"ok": False, "fout": regels[-1][:300]}

    def schermafdruk(self, pad: Path) -> bool:
        """X-scherm (met het mpv-beeld) via xwd in de container, omgezet met ffmpeg op de host."""
        xwd = pad.with_suffix(".xwd")
        r = subprocess.run(
            ["docker", "exec", "-e", "DISPLAY=:99", NAAM, "xwd", "-root", "-silent"],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if r.returncode != 0 or not r.stdout:
            return False
        pad.parent.mkdir(parents=True, exist_ok=True)
        xwd.write_bytes(r.stdout)
        c = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(xwd), "-vf", "scale=1280:-1", str(pad)],
            capture_output=True,
            check=False,
        )
        xwd.unlink(missing_ok=True)
        return c.returncode == 0

    def log(self, regels: int = 30) -> str:
        return docker("exec", NAAM, "tail", f"-{regels}", "/tmp/app.log", check=False).stdout[-2000:]  # noqa: S108

    def geheugen(self) -> dict[str, Any]:
        basis = Path(f"/sys/fs/cgroup/system.slice/docker-{self.cid}.scope")
        try:
            events = dict(r.split() for r in (basis / "memory.events").read_text().splitlines())
            return {"piek_bytes": int((basis / "memory.peak").read_text()), "oom_kill": int(events.get("oom_kill", 0))}
        except OSError as fout:
            return {"fout": str(fout)}

    def stop(self) -> None:
        docker("rm", "-f", NAAM, check=False)


def stap(ok: bool, **gegevens: Any) -> dict[str, Any]:
    return {"uitkomst": sc.GESLAAGD if ok else sc.MISLUKT, **gegevens}


def run(server: TestServer, build: Path, uitmap: Path, label: str) -> dict[str, Any]:
    res: dict[str, Any] = {
        "client": "jellyfin-desktop 2.0.0 (forkbron desktop/, 2.0.0-jl.0; Release-build in container)",
        "omgeving": "Xvfb 1600x900, QtWebEngine, libmpv (software), container --shm-size 1g",
        "stappen": {},
    }
    d = Desktop(build)
    try:
        _stappen(d, res, server, uitmap, label)
    except Exception as fout:  # noqa: BLE001 - eerlijk in het bewijs
        res["fout"] = f"{type(fout).__name__}: {str(fout)[:600]}"
    finally:
        res["app_log_staart"] = "\n".join(r for r in d.log(15).splitlines() if "Token" not in r)[-1200:]
        res["geheugen"] = d.geheugen()
        d.stop()
    res["oordeel"] = sc.eindoordeel(res["stappen"], VEREIST)
    return res


def _stappen(d: Desktop, res: dict[str, Any], server: TestServer, uitmap: Path, label: str) -> None:
    assert server.jf
    jf, it, st = server.jf, server.items, res["stappen"]
    volger = Volger(jf, CLIENT)
    schot = lambda naam: d.schermafdruk(uitmap / f"{label}-desktop-{naam}.png")  # noqa: E731
    d.start()
    v = d.cdp("verbind", server=server.url)
    i = d.cdp("inloggen", server=server.url, gebruiker=KIJKER, wachtwoord=KIJKER_WW) if v.get("ok") else {}
    sessie = volger.bestuurbaar(30) if i.get("ok") else None
    st["inloggen"] = stap(
        bool(v.get("ok") and i.get("ok") and i.get("thuis") and sessie),
        stappen=[
            "find-webclient: serveradres verstuurd",
            f"web-client van de server geladen: {v.get('ok')}",
            f"ingelogd: {i.get('ok')}, startscherm: {i.get('thuis')}",
        ],
        sessie={"client": sessie.get("Client"), "versie": sessie.get("ApplicationVersion")} if sessie else None,
        **({"fouten": v.get("fouten") or i.get("fout")} if not (v.get("ok") and i.get("ok")) else {}),
    )
    schot("startscherm")
    if not sessie:
        return
    log(f"desktop: ingelogd ({sessie.get('Client')} {sessie.get('ApplicationVersion')})")

    thuis = d.cdp("teksten", server=server.url).get("teksten", [])
    films = sorted(x["Name"] for x in jf.items(server.kijker_id) if x.get("Type") == "Movie")
    views = {x["Name"]: x for x in jf.a.doe("GET", "/UserViews", {"userId": server.kijker_id})["Items"]}
    jf.toon(volger.id(), views["Films"])
    bib = d.cdp("teksten", server=server.url, wacht_ms=4000).get("teksten", [])
    serie_id = it.afleveringen[0].get("SeriesId") if it.afleveringen else None
    serie: list[str] = []
    if serie_id:
        jf.toon(volger.id(), {"Type": "Series", "Id": serie_id, "Name": "B03 Testserie"})
        serie = d.cdp("teksten", server=server.url, wacht_ms=4000).get("teksten", [])
    gezien = {
        "films_tegel": "Films" in thuis,
        "series_tegel": "Series" in thuis,
        "verder_kijken_rij": "Continue Watching" in thuis,
        "hervatitem_op_startscherm": it.hervat["Name"] in thuis,
        "films_in_bibliotheek": [f for f in films if f in bib],
        "serie_pagina": sc.serie_seizoenen(serie, "B03 Testserie", 2),
    }
    st["bladeren"] = stap(
        gezien["films_tegel"]
        and gezien["verder_kijken_rij"]
        and gezien["hervatitem_op_startscherm"]
        and gezien["films_in_bibliotheek"] == films
        and gezien["serie_pagina"]["ok"],
        gezien=gezien,
    )
    log(f"desktop: bladeren {st['bladeren']['uitkomst']}")

    jf.toon(volger.id(), it.hervat)
    knop = d.cdp("klik", server=server.url, selector=".mainDetailButtons .btnPlay[title='Resume']")
    monsters = volger.volg(it.hervat["Id"], 25, minimaal_s=6) if knop.get("ok") else []
    st["hervatten"] = {
        **sc.beoordeel_hervatten(monsters, it.hervat["Id"], server.HERVAT_S),
        "knop": "Resume (detailpagina)",
    }
    schot("hervatten")
    laatste = max((m.positie_s for m in sc.van_item(monsters, it.hervat["Id"])), default=0.0)
    jf.afspeelcommando(volger.id(), "Stop")
    volger.wacht_tot_gestopt()
    time.sleep(2)
    st["hervatpunt_bewaard"] = sc.beoordeel_bewaard(jf.userdata(server.kijker_id, it.hervat["Id"]), laatste)
    log(f"desktop: hervatten {st['hervatten']['uitkomst']}, bewaard {st['hervatpunt_bewaard']['uitkomst']}")

    def speel(item: dict[str, Any], methode: str | None, naam: str, **extra: Any) -> dict[str, Any]:
        jf.speel(volger.id(), item["Id"], **extra)
        m = volger.volg(item["Id"], 45, minimaal_s=6)
        uitslag = {**sc.beoordeel_afspelen(m, item["Id"], verwachte_methode=methode), "item": item["Name"]}
        schot(naam)
        jf.afspeelcommando(volger.id(), "Stop")
        volger.wacht_tot_gestopt()
        time.sleep(2)
        return uitslag

    st["direct_play"] = speel(it.direct_play, "DirectPlay", "direct_play")
    # mpv speelt alles direct; transcode alleen via de gebruikersinstelling 'maximale streamingbitrate' (400 kbit/s).
    d.cdp("opslag", server=server.url, zet=LAGE_BITRATE)
    st["transcode"] = {
        **speel(it.transcode[0], "Transcode", "transcode"),
        "route": "Instellingen → Afspelen: maximale streamingbitrate 400 kbit/s (appSettings)",
    }
    d.cdp("opslag", server=server.url, zet=dict.fromkeys(LAGE_BITRATE))
    log(f"desktop: direct_play {st['direct_play']['uitkomst']}, transcode {st['transcode']['uitkomst']}")

    jf.gebruikersconfig(server.kijker_id, {"SubtitleMode": "Always", "SubtitleLanguagePreference": "nld"})
    verwacht = jf.playbackinfo(server.kijker_id, it.ondertitel_ingebed["Id"])["MediaSources"][0].get(
        "DefaultSubtitleStreamIndex"
    )
    nl = sc.spoor_index(it.ondertitel_ingebed.get("MediaStreams", []), sc.NL_TALEN)
    jf.speel(volger.id(), it.ondertitel_ingebed["Id"], start_ticks=5 * TICKS)
    m = volger.volg(it.ondertitel_ingebed["Id"], 30, minimaal_s=6)
    st["ondertitel_voorkeur"] = {
        **sc.beoordeel_ondertitel(m, it.ondertitel_ingebed["Id"], verwacht),
        "nl_spoor": nl,
        "server_standaard": verwacht,
        "afspeelmethode": sc.meest_voorkomend([x.methode for x in m]),
    }
    if verwacht != nl:
        st["ondertitel_voorkeur"].update(uitkomst=sc.MISLUKT, reden="de server kiest niet het NL-spoor als standaard")
    schot("ondertitel-voorkeur")
    jf.afspeelcommando(volger.id(), "Stop")
    volger.wacht_tot_gestopt()

    streams = it.hervat.get("MediaStreams", [])
    nl_ext, en_ext = sc.spoor_index(streams, sc.NL_TALEN), sc.spoor_index(streams, sc.EN_TALEN)
    jf.speel(volger.id(), it.hervat["Id"], start_ticks=24 * TICKS, ondertitel=nl_ext)
    begin = volger.volg(it.hervat["Id"], 20, minimaal_s=2)
    jf.algemeen_commando(volger.id(), "SetSubtitleStreamIndex", {"Index": str(en_ext)})
    # Gemeten: de desktop meldt een gewisseld extern spoor soms pas na ~10 s (mpv laadt de srt van de server).
    naar_en = volger.volg(it.hervat["Id"], 20, minimaal_s=99, tot_ondertitel=en_ext)
    jf.algemeen_commando(volger.id(), "SetSubtitleStreamIndex", {"Index": str(nl_ext)})
    naar_nl = volger.volg(it.hervat["Id"], 20, minimaal_s=99, tot_ondertitel=nl_ext)
    schot("ondertitel-extern")
    en_ok = sc.beoordeel_ondertitel(naar_en, it.hervat["Id"], en_ext, vanaf_t=3)
    nl_ok = sc.beoordeel_ondertitel(naar_nl, it.hervat["Id"], nl_ext, vanaf_t=3)
    st["ondertitel_extern"] = {
        "uitkomst": sc.GESLAAGD if en_ok["uitkomst"] == nl_ok["uitkomst"] == sc.GESLAAGD else sc.MISLUKT,
        "route": "SetSubtitleStreamIndex tijdens het afspelen (EN, daarna NL)",
        "naar_en": en_ok,
        "naar_nl": nl_ok,
        "bij_start_met_playnow_index": {
            "gevraagd": nl_ext,
            "gemeld": sc.meest_voorkomend([x.ondertitel for x in begin]),
        },
    }
    jf.afspeelcommando(volger.id(), "Stop")
    volger.wacht_tot_gestopt()
    log(
        f"desktop: ondertitels voorkeur {st['ondertitel_voorkeur']['uitkomst']}, "
        f"extern {st['ondertitel_extern']['uitkomst']}"
    )
    st["skip_segmenten"] = sc.beoordeel_segmenten({x["Name"]: jf.segmenten(x["Id"]) for x in it.afleveringen})
    res["webfouten"] = d.cdp("fouten", server=server.url).get("fouten", [])


def main(a: argparse.Namespace) -> int:
    uitmap = a.uit.with_suffix("")
    uitmap.mkdir(parents=True, exist_ok=True)
    build = a.build.resolve()
    if not (build / "build/src/jellyfin-desktop").exists():
        log(f"geen gebouwde app in {build}/build/src (eerst make desktop-bouw)")
        return 2
    servers = [("jelly-leon", a.image)] + ([("stock", a.stock_image)] if a.met_stock else [])
    from .cli import image_herkomst  # vermijdt een importkring

    document: dict[str, Any] = {
        "schema": "jelly-leon-clients/p4-0-jc3-desktop/1",
        "begin": bewijs.nu(),
        "servers": {lbl: image_herkomst(img) for lbl, img in servers},
        "resultaten": {},
        "niet_hier": bewijs.NIET_HIER,
    }
    for label, image in servers:
        with bewijs.slot("stack.lock", log):
            log(f"== {label} / desktop")
            server = TestServer(image).start()
            try:
                inrichting = server.inrichten()
                r = run(server, build, uitmap, label)
                r["server"] = {
                    "versie": server.info.get("Version"),
                    "image_id": server.image_id(),
                    "inrichting": inrichting,
                }
            finally:
                server.verwijder()
        document["resultaten"][label] = r
        log(f"== {label} / desktop: {r['oordeel']['validatie']} {r['oordeel']['mislukte_stappen']}")
    if "stock" in document["resultaten"]:
        document["vergelijking_met_stock"] = bewijs.vergelijk(
            document["resultaten"]["jelly-leon"]["stappen"], document["resultaten"]["stock"]["stappen"]
        )
        document["regressies"] = [v for v in document["vergelijking_met_stock"] if v["regressie"]]
    document["schermafdrukken"] = bewijs.comprimeer_schermafdrukken(uitmap)
    document["eind"] = bewijs.nu()
    jl = document["resultaten"]["jelly-leon"]["oordeel"]["validatie"]
    document["validatie"] = "Sim-geslaagd" if jl == "Sim-geslaagd" and not document.get("regressies") else "Sim-mislukt"
    bewijs.schrijf(a.uit, document, geheimen=[KIJKER_WW, BEHEER_WW])
    log(f"bewijs geschreven: {a.uit} — {document['validatie']}")
    return 0
