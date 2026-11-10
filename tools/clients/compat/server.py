"""Wegwerpserver voor de clienttests: de jelly-leon-image (lokaal gebouwd of uit CI) of stock 12.x op digest.

Regels (B03 §10.13/§10.14, 03_RISICO_AUTONOMIE): alleen op 127.0.0.1, media alleen-lezen en per bestand gekoppeld
(nooit een schrijfpad in het corpus), eigen uid, ``--cap-drop ALL``, ``no-new-privileges``, geen Docker-socket, geen
``--privileged``; datamap en cache in een werkmap buiten de repo die na de test weg gaat (BG-38). Het mediacorpus komt
uit ``.lokaal/media-corpus`` en gaat nooit in een repo of image.
"""

from __future__ import annotations

import itertools
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .jfapi import TICKS, Jellyfin, wacht_klaar
from .scenario import beoordeel_migratie

STOCK_12_4 = "docker.io/jellyfin/jellyfin:12.4@sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771"
CORPUS = Path(os.environ.get("JLC_CORPUS", "/home/transcode/truenas-v2/.lokaal/media-corpus"))
WERK = Path(os.environ.get("JLC_WERK", "/home/transcode/truenas-v2/.lokaal/jelly-leon-clients-jc3"))

# Wegwerpaccounts in een wegwerpcontainer op 127.0.0.1 (geen echte gegevens). Alleen letters en cijfers: `adb shell
# input text` vertaalt sommige leestekens niet betrouwbaar.
BEHEERDER, BEHEER_WW = "jc3beheer", "Jc3Beheer2026"
KIJKER, KIJKER_WW = "jc3kijker", "Jc3Kijker2026"

# Testbibliotheek: bestand in de container → bron onder het corpus (sha256 in CORPUS/SHA256SUMS.*). Alle bronnen zijn
# vrij gelicentieerd (CC BY); geen Pioneer One of andere beperkte testdata (BG-37).
FILMS: dict[str, str] = {
    "/media/films/hero/hero.mp4": "bron/blender/hero/hero.mp4",
    "/media/films/tears_of_steel/tears_of_steel_1080p.mov": "bron/blender/tos/uitgepakt/tears_of_steel_1080p.mov",
    "/media/films/tears_of_steel/tears_of_steel_1080p.nl.srt": "bron/blender/tos/subs/TOS-nl.srt",
    "/media/films/tears_of_steel/tears_of_steel_1080p.en.srt": "bron/blender/tos/subs/TOS-en.srt",
    "/media/films/sintel-60s-referentie/sintel-60s-referentie.mkv": "afgeleid/kwaliteit/sintel-60s-referentie.mkv",
    "/media/films/sintel-30s-mpeg2-ac3/sintel-30s-mpeg2-ac3.ts": "afgeleid/formaten/sintel-30s-mpeg2-ac3.ts",
    "/media/films/sintel-30s-mpeg4-mp3/sintel-30s-mpeg4-mp3.avi": "afgeleid/formaten/sintel-30s-mpeg4-mp3.avi",
}
SERIES: dict[str, str] = {"/media/series/B03 Testserie": "afgeleid/series/B03 Testserie"}


@dataclass
class Testitems:
    """De rollen van de items in de scenario's (Id's worden na de scan opgezocht)."""

    direct_play: dict[str, Any] = field(default_factory=dict)  # hero.mp4: H.264 + AAC in mp4
    hervat: dict[str, Any] = field(default_factory=dict)  # Tears of Steel: H.264 + MP3 in mov, externe NL/EN-srt
    # Kandidaten die een client niet direct kan spelen (welke dat is, hangt af van het apparaatprofiel van de app;
    # gemeten: android 2.7.3 transcodeert de TS, androidtv 0.19.10 speelt die direct maar niet de AVI).
    transcode: list[dict[str, Any]] = field(default_factory=list)  # MPEG-4 ASP + MP3 in AVI; MPEG-2 + AC3 in TS
    ondertitel_ingebed: dict[str, Any] = field(default_factory=dict)  # Sintel 60 s: H.264 + AC3 + ingebedde NL-srt
    afleveringen: list[dict[str, Any]] = field(default_factory=list)


_TELLER = itertools.count(1)


def vrije_poort() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def docker(*args: str, check: bool = True, timeout: float = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=timeout)


class TestServer:
    """Eén wegwerpserver met de testbibliotheek, een beheerder en één kijker met gezaaide kijkgeschiedenis."""

    def __init__(
        self,
        image: str,
        naam: str | None = None,
        werk: Path = WERK,
        corpus: Path = CORPUS,
        geheugen: str = "3g",
        cpus: str = "4",
    ) -> None:
        self.image = image
        # Eigen naam en map per proces: twee harnasruns naast elkaar mogen elkaars server nooit vervangen
        # (gemeten: met een vaste naam verwijderde de ene run de server van de andere).
        self.naam = naam or f"jlc-jc3-server-{os.getpid()}-{next(_TELLER)}"
        self.map = werk / self.naam
        self.corpus = corpus
        self.geheugen = geheugen
        self.cpus = cpus
        self.poort = 0
        self.jf: Jellyfin | None = None
        self.info: dict[str, Any] = {}
        self.kijker_id = ""
        self.items = Testitems()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.poort}"

    def koppelingen(self) -> list[str]:
        uit: list[str] = []
        for doel, bron in {**FILMS, **SERIES}.items():
            pad = self.corpus / bron
            if not pad.exists():
                raise FileNotFoundError(f"corpusbestand ontbreekt: {pad}")
            uit += ["-v", f"{pad}:{doel}:ro"]
        return uit

    def start(self) -> TestServer:
        shutil.rmtree(self.map, ignore_errors=True)
        for sub in ("config", "cache"):
            (self.map / sub).mkdir(parents=True, exist_ok=True)
        self.poort = vrije_poort()
        self._draai()
        return self

    def _draai(self, timeout: float = 300) -> None:
        """Container op de bestaande datamap (``self.map``) starten en wachten tot de server antwoordt."""
        docker("rm", "-f", self.naam, check=False)
        docker(
            "run", "-d", "--name", self.naam, "--user", f"{os.getuid()}:{os.getgid()}",
            "--memory", self.geheugen, "--cpus", self.cpus, "--security-opt", "no-new-privileges", "--cap-drop", "ALL",
            "-p", f"127.0.0.1:{self.poort}:8096", "-v", f"{self.map / 'config'}:/config",
            "-v", f"{self.map / 'cache'}:/cache", "-e", "TZ=UTC", *self.koppelingen(), self.image,
        )  # fmt: skip
        self.info = wacht_klaar(self.url, timeout=timeout)
        self.jf = Jellyfin(self.url)

    def image_id(self) -> str:
        return docker("inspect", "--format", "{{.Image}}", self.naam, check=False).stdout.strip()

    def inrichten(self, voorkeuren: bool = False) -> dict[str, Any]:
        """Wizard, bibliotheken, scan, de kijker en zijn kijkgeschiedenis (alsof die net is overgenomen)."""
        assert self.jf
        jf = self.jf
        jf.wizard(BEHEERDER, BEHEER_WW)
        jf.bibliotheek("Films", "movies", ["/media/films"])
        jf.bibliotheek("Series", "tvshows", ["/media/series"])
        scan_s = jf.scan(verwacht_minimaal=len(FILMS) - 2 + 5)  # 2 srt-bestanden, 5 afleveringen
        self.kijker_id = jf.gebruiker(KIJKER, KIJKER_WW)
        aantal = self.items_opzoeken()
        return {"scan_s": round(scan_s, 1), "items": aantal, "kijkgeschiedenis": self.zaai_kijkgeschiedenis(voorkeuren)}

    def items_opzoeken(self) -> int:
        """De testitems op pad opzoeken (na een migratie opnieuw: Id's worden niet aangenomen)."""
        assert self.jf
        alle = self.jf.items(self.kijker_id)
        per_pad = {i.get("Path"): i for i in alle}
        self.items = Testitems(
            direct_play=per_pad["/media/films/hero/hero.mp4"],
            hervat=per_pad["/media/films/tears_of_steel/tears_of_steel_1080p.mov"],
            transcode=[
                per_pad["/media/films/sintel-30s-mpeg4-mp3/sintel-30s-mpeg4-mp3.avi"],
                per_pad["/media/films/sintel-30s-mpeg2-ac3/sintel-30s-mpeg2-ac3.ts"],
            ],
            ondertitel_ingebed=per_pad["/media/films/sintel-60s-referentie/sintel-60s-referentie.mkv"],
            afleveringen=sorted((i for i in alle if i.get("Type") == "Episode"), key=lambda i: i.get("Path", "")),
        )
        return len(alle)

    def kijkgegevens(self) -> dict[str, Any]:
        """Vergelijkbare momentopname van de kijkgegevens van de kijker (per item op naam) en zijn voorkeuren."""
        assert self.jf
        jf, uid, it = self.jf, self.kijker_id, self.items
        velden = ("Played", "PlayCount", "PlaybackPositionTicks", "IsFavorite", "Likes", "LastPlayedDate")
        per_item = {}
        for item in (it.hervat, it.direct_play, it.ondertitel_ingebed):
            data = jf.userdata(uid, item["Id"])
            per_item[item["Name"]] = {k: data.get(k) for k in velden}
        config = jf.a.doe("GET", f"/Users/{uid}")["Configuration"]
        return {
            "items": per_item,
            "hervatlijst": sorted(i["Name"] for i in jf.hervatlijst(uid)),
            "voorkeuren": {
                k: config.get(k)
                for k in (
                    "SubtitleMode",
                    "SubtitleLanguagePreference",
                    "RememberSubtitleSelections",
                    "RememberAudioSelections",
                )
            },
        }

    def migreer_van(self, oude_image: str) -> dict[str, Any]:
        """JLT-60, clientdeel: dezelfde testbibliotheek en kijkgeschiedenis eerst op de oude server (10.11.11)
        zaaien, die stoppen en dezelfde datamap met de nieuwe image starten (de server migreert zelf).
        Daarna moet vóór = na gelden, per veld."""
        nieuw, self.image = self.image, oude_image
        self.start()
        inrichting = self.inrichten(voorkeuren=True)
        oud = {"image": oude_image, "versie": self.info.get("Version"), "image_id": self.image_id()}
        voor = self.kijkgegevens()
        docker("stop", "-t", "30", self.naam, check=False)
        self.image = nieuw
        self._draai(timeout=600)
        assert self.jf
        self.jf.login_admin(BEHEERDER, BEHEER_WW)
        self.items_opzoeken()
        na = self.kijkgegevens()
        oordeel = beoordeel_migratie(
            voor,
            na,
            {
                "hervat": (self.items.hervat["Name"], int(self.HERVAT_S * TICKS)),
                "gezien": (self.items.direct_play["Name"], 2),
                "favoriet": self.items.ondertitel_ingebed["Name"],
            },
        )
        return {
            "oude_server": oud,
            "nieuwe_server": {"versie": self.info.get("Version"), "image_id": self.image_id()},
            "inrichting_op_oude_server": inrichting,
            "voor": voor,
            "na": na,
            **oordeel,
        }

    HERVAT_S = 300.0  # gezaaid hervatpunt in Tears of Steel (734 s)

    def zaai_kijkgeschiedenis(self, voorkeuren: bool = False) -> dict[str, Any]:
        """Kijkgegevens van de kijker zoals na een overname: hervatpunt, gezien met datum en aantal, favoriet; met
        ``voorkeuren`` ook de ondertitelvoorkeur (NL, altijd tonen), zodat die mee door een migratie gaat."""
        assert self.jf
        jf, uid, it = self.jf, self.kijker_id, self.items
        if voorkeuren:
            jf.gebruikersconfig(uid, {"SubtitleMode": "Always", "SubtitleLanguagePreference": "nld"})
        jf.zet_userdata(
            uid,
            it.hervat["Id"],
            {
                "PlaybackPositionTicks": int(self.HERVAT_S * TICKS),
                "Played": False,
                "LastPlayedDate": "2026-11-01T20:15:00Z",
            },
        )
        jf.zet_userdata(
            uid, it.direct_play["Id"], {"Played": True, "PlayCount": 2, "LastPlayedDate": "2026-10-30T19:00:00Z"}
        )
        jf.zet_userdata(uid, it.ondertitel_ingebed["Id"], {"IsFavorite": True, "Likes": True})
        return {
            "hervatpunt": {"item": it.hervat["Name"], "positie_s": self.HERVAT_S},
            "gezien": {"item": it.direct_play["Name"], "aantal": 2},
            "favoriet": {"item": it.ondertitel_ingebed["Name"]},
            "controle_na_zaaien": {
                "hervatlijst": [i["Name"] for i in jf.hervatlijst(uid)],
                "hervat_ticks": jf.userdata(uid, it.hervat["Id"]).get("PlaybackPositionTicks"),
                "gezien_aantal": jf.userdata(uid, it.direct_play["Id"]).get("PlayCount"),
                "favoriet": jf.userdata(uid, it.ondertitel_ingebed["Id"]).get("IsFavorite"),
            },
        }

    def logs(self, regels: int = 60) -> str:
        return docker("logs", "--tail", str(regels), self.naam, check=False).stdout

    def verwijder(self) -> None:
        docker("rm", "-f", self.naam, check=False)
        shutil.rmtree(self.map, ignore_errors=True)

    def __enter__(self) -> TestServer:
        return self

    def __exit__(self, *_: object) -> None:
        self.verwijder()
