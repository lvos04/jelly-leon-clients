"""Kleine Jellyfin-API-client (alleen stdlib) voor de wegwerpserver van het compatibiliteitsharnas.

Spreekt de 12.x-server aan zoals moderne clients: ``Authorization: MediaBrowser …, Token="…"`` (legacy-headers en
``api_key=`` staan in 12.x uit; besluit BG-01). Tokens en wachtwoorden komen nooit in het bewijs (zie ``bewijs``).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

CLIENT = 'MediaBrowser Client="jlc-compat-harnas", Device="harnas", DeviceId="jlc-jc3-harnas", Version="1.0"'
TICKS = 10_000_000  # Jellyfin-ticks per seconde


class HttpFout(RuntimeError):
    def __init__(self, status: int, tekst: str) -> None:
        super().__init__(tekst)
        self.status = status


class Http:
    def __init__(self, basis: str, headers: dict[str, str] | None = None, timeout: float = 120.0) -> None:
        self.basis = basis.rstrip("/")
        self.headers = dict(headers or {})
        self.timeout = timeout

    def ruw(self, methode: str, pad: str, query: dict[str, Any] | None = None, body: Any = None) -> tuple[int, bytes]:
        q = {k: v for k, v in (query or {}).items() if v is not None}
        url = self.basis + pad + ("?" + urllib.parse.urlencode(q, doseq=True) if q else "")
        data = json.dumps(body).encode() if body is not None else (b"" if methode in ("POST", "DELETE") else None)
        h = {"Accept": "application/json", **self.headers}
        if body is not None:
            h["Content-Type"] = "application/json"
        verzoek = urllib.request.Request(url, data=data, method=methode, headers=h)  # noqa: S310 - lokaal testadres
        try:
            with urllib.request.urlopen(verzoek, timeout=self.timeout) as antwoord:  # noqa: S310
                return antwoord.status, antwoord.read()
        except urllib.error.HTTPError as fout:
            return fout.code, fout.read()

    def doe(
        self,
        methode: str,
        pad: str,
        query: dict[str, Any] | None = None,
        body: Any = None,
        verwacht: tuple[int, ...] = (200, 204),
    ) -> Any:
        status, ruw = self.ruw(methode, pad, query, body)
        if status not in verwacht:
            raise HttpFout(status, f"{methode} {pad} → HTTP {status}: {ruw[:300]!r}")
        if not ruw:
            return None
        try:
            return json.loads(ruw.decode("utf-8-sig"))
        except ValueError:
            return ruw.decode("utf-8", "replace")


def wacht_klaar(url: str, timeout: float = 300.0) -> dict[str, Any]:
    """Wacht tot /System/Info/Public geldige JSON met een versie geeft (12.x toont tijdens het opstarten HTML)."""
    einde = time.monotonic() + timeout
    laatste = ""
    while time.monotonic() < einde:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/System/Info/Public", timeout=5) as a:  # noqa: S310
                data = json.loads(a.read().decode("utf-8-sig"))
                if isinstance(data, dict) and data.get("Version"):
                    return data
        except (urllib.error.URLError, OSError, ValueError) as fout:
            laatste = str(fout)
        time.sleep(2)
    raise RuntimeError(f"{url} niet klaar binnen {timeout:.0f} s ({laatste})")


class Jellyfin:
    """Wizard, gebruikers, bibliotheken, kijkgegevens en de afstandsbedieningsroutes die het harnas gebruikt."""

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.anoniem = Http(self.url, {"Authorization": CLIENT})
        self.admin: Http | None = None
        self.admin_id = ""

    # --- inrichten ---------------------------------------------------------------------------------------------

    def wizard(self, gebruiker: str, wachtwoord: str) -> None:
        a = self.anoniem
        for poging in range(60):
            try:
                a.doe(
                    "POST",
                    "/Startup/Configuration",
                    body={"UICulture": "en-US", "MetadataCountryCode": "NL", "PreferredMetadataLanguage": "nl"},
                )
                break
            except HttpFout as fout:
                if fout.status != 503 or poging == 59:
                    raise
                time.sleep(2)
        a.doe("GET", "/Startup/User")
        a.doe("POST", "/Startup/User", body={"Name": gebruiker, "Password": wachtwoord})
        a.doe("POST", "/Startup/RemoteAccess", body={"EnableRemoteAccess": False, "EnableAutomaticPortMapping": False})
        a.doe("POST", "/Startup/Complete")
        self.login_admin(gebruiker, wachtwoord)

    def login_admin(self, gebruiker: str, wachtwoord: str) -> None:
        auth = self.anoniem.doe("POST", "/Users/AuthenticateByName", body={"Username": gebruiker, "Pw": wachtwoord})
        self.admin_id = auth["User"]["Id"]
        self.admin = Http(self.url, {"Authorization": CLIENT + f', Token="{auth["AccessToken"]}"'})

    @property
    def a(self) -> Http:
        if self.admin is None:
            raise RuntimeError("eerst inloggen")
        return self.admin

    def gebruiker(self, naam: str, wachtwoord: str) -> str:
        return self.a.doe("POST", "/Users/New", body={"Name": naam, "Password": wachtwoord})["Id"]

    def gebruikersconfig(self, user_id: str, wijzigingen: dict[str, Any]) -> dict[str, Any]:
        huidig = self.a.doe("GET", f"/Users/{user_id}")["Configuration"]
        nieuw = {**huidig, **wijzigingen}
        self.a.doe("POST", "/Users/Configuration", {"userId": user_id}, body=nieuw)
        return self.a.doe("GET", f"/Users/{user_id}")["Configuration"]

    def bibliotheek(self, naam: str, soort: str, paden: list[str]) -> None:
        typen = {"movies": ["Movie"], "tvshows": ["Series", "Season", "Episode"]}.get(soort, ["Movie"])
        opties = {
            "EnableRealtimeMonitor": False,
            "SaveLocalMetadata": False,
            "EnableChapterImageExtraction": False,
            "ExtractChapterImagesDuringLibraryScan": False,
            "EnableTrickplayImageExtraction": False,
            "ExtractTrickplayImagesDuringLibraryScan": False,
            "SaveSubtitlesWithMedia": False,
            "SaveTrickplayWithMedia": False,
            "SaveLyricsWithMedia": False,
            "EnableEmbeddedTitles": False,
            "PathInfos": [{"Path": p} for p in paden],
            "MetadataSavers": [],
            "DisabledSubtitleFetchers": [],
            "SubtitleDownloadLanguages": [],
            # Geen online metadata: wegwerpserver zonder internetverkeer naar metadatabronnen.
            "TypeOptions": [
                {
                    "Type": t,
                    "MetadataFetchers": [],
                    "MetadataFetcherOrder": [],
                    "ImageFetchers": [],
                    "ImageFetcherOrder": [],
                }
                for t in typen
            ],
        }
        self.a.doe(
            "POST",
            "/Library/VirtualFolders",
            {"name": naam, "collectionType": soort, "refreshLibrary": "false"},
            body={"LibraryOptions": opties},
        )

    def scan(self, verwacht_minimaal: int, timeout: float = 900.0) -> float:
        """Start de scan; klaar als er geen taak meer loopt, er genoeg items zijn en het aantal stabiel is."""
        begin = time.monotonic()
        self.a.doe("POST", "/Library/Refresh")
        time.sleep(3)
        vorige, gelijk = -1, 0
        while time.monotonic() - begin < timeout:
            taken = self.a.doe("GET", "/ScheduledTasks", {"isHidden": "false"})
            aantal = self.a.doe(
                "GET", "/Items", {"recursive": "true", "limit": "0", "includeItemTypes": "Movie,Episode"}
            ).get("TotalRecordCount", 0)
            gelijk = gelijk + 1 if aantal == vorige else 0
            vorige = aantal
            if aantal >= verwacht_minimaal and not any(t.get("State") == "Running" for t in taken) and gelijk >= 2:
                return time.monotonic() - begin
            time.sleep(2)
        raise RuntimeError(f"bibliotheekscan niet klaar binnen {timeout:.0f} s ({vorige} items)")

    # --- lezen -------------------------------------------------------------------------------------------------

    def items(self, user_id: str) -> list[dict[str, Any]]:
        q = {
            "userId": user_id,
            "recursive": "true",
            "includeItemTypes": "Movie,Episode",
            "fields": "Path,MediaStreams,MediaSources",
            "limit": "500",
        }
        return self.a.doe("GET", "/Items", q)["Items"]

    def userdata(self, user_id: str, item_id: str) -> dict[str, Any]:
        return self.a.doe("GET", f"/UserItems/{item_id}/UserData", {"userId": user_id})

    def zet_userdata(self, user_id: str, item_id: str, gegevens: dict[str, Any]) -> dict[str, Any]:
        return self.a.doe("POST", f"/UserItems/{item_id}/UserData", {"userId": user_id}, body=gegevens)

    def hervatlijst(self, user_id: str) -> list[dict[str, Any]]:
        return self.a.doe("GET", "/UserItems/Resume", {"userId": user_id, "limit": "20"})["Items"]

    def playbackinfo(self, user_id: str, item_id: str) -> dict[str, Any]:
        return self.a.doe("POST", f"/Items/{item_id}/PlaybackInfo", {"userId": user_id}, body={})

    def segmenten(self, item_id: str) -> list[dict[str, Any]]:
        return self.a.doe("GET", f"/MediaSegments/{item_id}").get("Items", [])

    def sessies(self) -> list[dict[str, Any]]:
        return self.a.doe("GET", "/Sessions")

    # --- afstandsbediening (officiële routes) ------------------------------------------------------------------

    def speel(
        self,
        sessie_id: str,
        item_id: str,
        *,
        start_ticks: int | None = None,
        ondertitel: int | None = None,
        audio: int | None = None,
    ) -> None:
        self.a.doe(
            "POST",
            f"/Sessions/{sessie_id}/Playing",
            {
                "playCommand": "PlayNow",
                "itemIds": item_id,
                "startPositionTicks": start_ticks,
                "subtitleStreamIndex": ondertitel,
                "audioStreamIndex": audio,
            },
        )

    def afspeelcommando(self, sessie_id: str, commando: str) -> None:
        self.a.doe("POST", f"/Sessions/{sessie_id}/Playing/{commando}")

    def toon(self, sessie_id: str, item: dict[str, Any]) -> None:
        """DisplayContent: de client opent de detailpagina van het item (zoals 'Bekijk op tv' in de web-client)."""
        self.a.doe(
            "POST",
            f"/Sessions/{sessie_id}/Viewing",
            {"itemType": item["Type"], "itemId": item["Id"], "itemName": item.get("Name", "")},
        )

    def algemeen_commando(self, sessie_id: str, naam: str, argumenten: dict[str, str]) -> None:
        self.a.doe("POST", f"/Sessions/{sessie_id}/Command", body={"Name": naam, "Arguments": argumenten})

    def quickconnect_autoriseer(self, code: str, user_id: str) -> bool:
        return self.a.doe("POST", "/QuickConnect/Authorize", {"code": code, "userId": user_id}) is True
