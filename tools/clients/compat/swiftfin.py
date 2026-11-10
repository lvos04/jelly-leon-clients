"""Swiftfin 1.6.1 tegen de 12.x-server: de **serverkant** van het protocol, nagebootst met de exacte vormen uit de bron.

Swiftfin zelf draait hier niet (geen Mac/Xcode): de app blijft **NIET GEVALIDEERD (Mac/Xcode)**. Wat wel kan, is meten
hoe de Jelly Leon-server (en stock 12.x als controle) antwoordt op precies de verzoeken die Swiftfin 1.6.1 met
jellyfin-sdk-swift 3.0.0 (API 12.0.0, revisie 37a2f50) maakt. Bronnen (alleen gelezen):

- versiecontrole ``isVersionCompatible``: ``swiftfin/Shared/SwiftfinStore/SwiftfinStore+ServerState.swift`` (major.minor
  van de server ≥ die van de SDK, 12.0);
- aanmeldkop ``authorizationHeaders``: SDK ``Sources/PassthroughAPIClientDelegate.swift`` — ``MediaBrowser`` met
  **ongequote** waarden ``DeviceId=…, Device=…, Client=…, Version=…, Token=…``;
- websocket: SDK ``Sources/JellyfinClient.swift`` (``/socket?api_key=<token>&deviceId=…``) plus dezelfde
  ``Authorization``-kop (``Sources/JellyfinSocket/JellyfinSocket.swift``);
- Direct Play: ``/Videos/{id}/stream?static=true&tag=…&playSessionId=…&mediaSourceId=…`` zonder token
  (``MediaPlayerItem+Build.swift``); transcode: de ``TranscodingUrl`` van de server;
- logbestand (beheer): ``client.url(with:queryAPIKey: true)`` → ``?api_key=<token>``
  (``Swiftfin/Extensions/LogFile.swift``).
"""

from __future__ import annotations

import base64
import os
import socket
import urllib.parse
from typing import Any

from . import scenario as sc
from .jfapi import Http
from .server import BEHEER_WW, BEHEERDER, KIJKER, KIJKER_WW, TestServer

SDK_API = "12.0.0"
APPVERSIE = "1.6.1"


def kop(token: str | None = None) -> str:
    """Exact de vorm van jellyfin-sdk-swift 3.0.0 (ongequote waarden, gescheiden door ', ')."""
    velden = {
        "DeviceId": "iOS_00000000-0000-4000-8000-00000000jc3a",
        "Device": "iPhone",
        "Client": "Swiftfin iOS",
        "Version": APPVERSIE,
    }
    if token:
        velden["Token"] = token
    return "MediaBrowser " + ", ".join(f"{k}={v}" for k, v in velden.items())


def versie_compatibel(server: str, sdk: str = SDK_API) -> bool:
    """``isVersionCompatible`` van Swiftfin: major.minor van de server ≥ major.minor van de SDK."""

    def mm(v: str) -> tuple[int, int]:
        delen = [int(x) for x in v.split("-")[0].split(".")[:2]]
        return delen[0], delen[1] if len(delen) > 1 else 0

    return mm(server) >= mm(sdk)


def websocket_handdruk(poort: int, pad: str, kop_waarde: str | None) -> int:
    """Ruwe HTTP/1.1-upgrade naar ``/socket``; geeft de statuscode (101 = verbonden)."""
    sleutel = base64.b64encode(os.urandom(16)).decode()
    regels = [
        f"GET {pad} HTTP/1.1",
        f"Host: 127.0.0.1:{poort}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {sleutel}",
        "Sec-WebSocket-Version: 13",
    ]
    if kop_waarde:
        regels.append(f"Authorization: {kop_waarde}")
    with socket.create_connection(("127.0.0.1", poort), timeout=10) as s:
        s.sendall(("\r\n".join(regels) + "\r\n\r\n").encode())
        eerste = s.recv(256).split(b"\r\n", 1)[0].decode(errors="replace")
    try:
        return int(eerste.split()[1])
    except (IndexError, ValueError):
        return 0


def stap(ok: bool, **gegevens: Any) -> dict[str, Any]:
    return {"uitkomst": sc.GESLAAGD if ok else sc.MISLUKT, **gegevens}


def run(server: TestServer) -> dict[str, Any]:
    assert server.jf
    st: dict[str, Any] = {}
    anoniem = Http(server.url)
    info = anoniem.doe("GET", "/System/Info/Public")
    st["versiecontrole"] = stap(
        versie_compatibel(info["Version"]),
        server=info["Version"],
        sdk_api=SDK_API,
        betekenis="geen melding 'Update to Jellyfin 12.0' meer (ADR-0009)",
    )

    auth = Http(server.url, {"Authorization": kop()}).doe(
        "POST", "/Users/AuthenticateByName", body={"Username": KIJKER, "Pw": KIJKER_WW}
    )
    token = auth["AccessToken"]
    app = Http(server.url, {"Authorization": kop(token)})
    st["aanmelden_met_ongequote_kop"] = stap(bool(token), gebruiker=auth["User"]["Name"])
    ik = app.ruw("GET", "/Users/Me")[0]
    hervat = app.doe("GET", "/UserItems/Resume", {"userId": server.kijker_id, "limit": "5"})
    st["api_met_kop"] = stap(
        ik == 200 and server.items.hervat["Name"] in [i["Name"] for i in hervat["Items"]],
        users_me=ik,
        hervatlijst=[i["Name"] for i in hervat["Items"]],
    )
    sessie = next((s for s in server.jf.sessies() if s.get("Client") == "Swiftfin iOS"), {})
    st["sessie_herkend"] = stap(
        sessie.get("ApplicationVersion") == APPVERSIE,
        client=sessie.get("Client"),
        versie=sessie.get("ApplicationVersion"),
    )

    socket_pad = "/socket?" + urllib.parse.urlencode({"api_key": token, "deviceId": "iOS_jc3"})
    met_kop = websocket_handdruk(server.poort, socket_pad, kop(token))
    zonder_kop = websocket_handdruk(server.poort, socket_pad, None)
    st["websocket"] = stap(
        met_kop == 101,
        met_kop_en_api_key=met_kop,
        alleen_api_key=zonder_kop,
        uitleg="Swiftfin stuurt de kop mee; api_key alleen telt in 12.x niet meer (legacy uit)",
    )

    item = server.items.direct_play
    msid = item["MediaSources"][0]["Id"]
    stream = anoniem.ruw(
        "GET", f"/Videos/{item['Id']}/stream", {"static": "true", "playSessionId": "jc3", "mediaSourceId": msid}
    )[0]
    st["direct_play_url_zonder_token"] = stap(
        stream in (200, 206), status=stream, uitleg="statische stream is in 12.x zonder token bereikbaar (UG-GEM-1)"
    )

    profiel = {
        "Name": "jc3-swiftfin-transcode",
        "MaxStreamingBitrate": 120_000_000,
        "DirectPlayProfiles": [],
        "TranscodingProfiles": [
            {
                "Type": "Video",
                "Container": "ts",
                "VideoCodec": "h264",
                "AudioCodec": "aac",
                "Protocol": "hls",
                "Context": "Streaming",
            }
        ],
    }
    pi = app.doe(
        "POST",
        f"/Items/{item['Id']}/PlaybackInfo",
        {"userId": server.kijker_id},
        body={"DeviceProfile": profiel, "EnableDirectPlay": False, "EnableDirectStream": False},
    )
    url = pi["MediaSources"][0].get("TranscodingUrl") or ""
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    master = anoniem.ruw("GET", url.split("?")[0], {k: v[0] for k, v in query.items()})[0] if url else 0
    app.ruw(
        "DELETE",
        "/Videos/ActiveEncodings",
        {"deviceId": "iOS_00000000-0000-4000-8000-00000000jc3a", "playSessionId": pi.get("PlaySessionId")},
    )
    st["transcode_url_van_de_server"] = stap(
        master == 200 and "ApiKey" in query and "api_key" not in query,
        status_master=master,
        parameter="ApiKey" if "ApiKey" in query else None,
    )

    # Beheerweergave 'serverlog openen': alleen voor een beheerder, dus aangemeld als de beheerder (zelfde kopvorm).
    beheer_auth = Http(server.url, {"Authorization": kop()}).doe(
        "POST", "/Users/AuthenticateByName", body={"Username": BEHEERDER, "Pw": BEHEER_WW}
    )
    beheer_token = beheer_auth["AccessToken"]
    beheer = Http(server.url, {"Authorization": kop(beheer_token)})
    logs = beheer.doe("GET", "/System/Logs")
    logbestand = logs[0]["Name"] if logs else "log_onbekend.log"
    alleen_api_key = anoniem.ruw("GET", "/System/Logs/Log", {"name": logbestand, "api_key": beheer_token})[0]
    met_kop_log = beheer.ruw("GET", "/System/Logs/Log", {"name": logbestand})[0]
    # Gevonden in de bron: Swiftfin opent een serverlog met ?api_key=; 12.x negeert api_key (legacy uit).
    st["logbestand_beheer"] = {
        "uitkomst": sc.GESLAAGD if alleen_api_key == 200 else sc.MISLUKT,
        "informatief": True,
        "alleen_api_key": alleen_api_key,
        "met_kop": met_kop_log,
        "gevolg": "alleen de beheerweergave 'serverlog openen' in Swiftfin; kijken en afspelen gebruiken de kop",
    }
    return {
        "client": "Swiftfin 1.6.1 (jellyfin-sdk-swift 3.0.0, API 12.0.0) — alleen de serverkant nagebootst",
        "stappen": st,
        "app_zelf": "NIET GEVALIDEERD (Mac/Xcode)",
        "oordeel": sc.eindoordeel(
            st,
            [
                "versiecontrole",
                "aanmelden_met_ongequote_kop",
                "api_met_kop",
                "sessie_herkend",
                "websocket",
                "direct_play_url_zonder_token",
                "transcode_url_van_de_server",
            ],
        ),
    }
