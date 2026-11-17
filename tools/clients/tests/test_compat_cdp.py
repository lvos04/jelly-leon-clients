"""CDP-besturing van de desktop (compat/desktop_cdp.mjs) tegen een nep-CDP, met de echte Node (S-P40-72, R-VEILIG-1).

De lijst ``/json/list`` en de ``webSocketDebuggerUrl`` daarin komen uit de desktopcontainer. Het harnas op de host mag
daar geen adres uit overnemen: anders laat een container de host verbinden met een dienst die alleen op 127.0.0.1 van
de host luistert (zoals PostgreSQL of Redis), of met het thuisnetwerk, en stuurt ``inloggen`` het kijkerwachtwoord mee.
Verwacht: geen doorverwijzing volgen, van ``webSocketDebuggerUrl`` alleen een pad ``/devtools/page/<id>`` gebruiken en
altijd verbinden met ``ws://127.0.0.1:<doorgiftepoort><pad>``; alles anders geeft ``ok: false``.

Opzet: de nep-CDP luistert op 127.0.0.1 van de host (zoals de doorgifte van ``CdpDoorgifte``), een lokker luistert
op een andere poort op 127.0.0.1 en telt elke verbinding. Een lokker die iets ontvangt is een lek.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

CDP_JS = Path(__file__).resolve().parents[1] / "compat" / "desktop_cdp.mjs"
SERVER = "http://testserver:8096"


def _node() -> str:
    """De Node van de ontwikkelmachine en van CI (setup-node 22): nodig, nooit overslaan (V-004)."""
    node = shutil.which("node")
    if not node:
        pytest.fail("node ontbreekt: desktop_cdp.mjs vraagt Node 22 (globale fetch en WebSocket)")
    versie = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    if int(versie.lstrip("v").split(".")[0]) < 22:
        pytest.fail(f"Node {versie}: desktop_cdp.mjs vraagt Node 22 of nieuwer")
    return node


class Lokker:
    """Een 'andere dienst' op 127.0.0.1 van de host; bewaart de eerste regel van elke verbinding."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.poort: int = self.sock.getsockname()[1]
        self.ontvangen: list[str] = []
        self._stop = threading.Event()
        self._draad = threading.Thread(target=self._accepteer, daemon=True)
        self._draad.start()

    def _accepteer(self) -> None:
        while not self._stop.is_set():
            try:
                klant, _ = self.sock.accept()
            except OSError:
                continue
            klant.settimeout(2)
            try:
                data = klant.recv(4096).decode("latin1")
            except OSError:
                data = ""
            self.ontvangen.append(data.splitlines()[0] if data else "(leeg)")
            klant.close()

    def sluit(self) -> None:
        self._stop.wait(0.5)  # een late verbinding nog laten tellen
        self._stop.set()
        self._draad.join(timeout=5)
        self.sock.close()


class NepCdp:
    """Nep-CDP op 127.0.0.1: ``/json/list`` naar keuze, en elke andere GET (ook een WebSocket-upgrade) opgeschreven."""

    def __init__(self, lijst: list[dict] | None = None, doorverwijzing: str | None = None) -> None:
        nep = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - naam van http.server
                nep.verzoeken.append((self.path, self.headers.get("Upgrade", "")))
                if self.path == "/json/list" and doorverwijzing:
                    self.send_response(302)
                    self.send_header("Location", doorverwijzing)
                    self.end_headers()
                    return
                if self.path == "/json/list":
                    body = json.dumps(lijst or []).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(404)  # geen echte WebSocket: de koppeling faalt, het verzoek is wel gezien
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_a: object) -> None:
                pass

        self.verzoeken: list[tuple[str, str]] = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.poort: int = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def sluit(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def cdp(poort: int, actie: str, **velden: object) -> dict:
    cfg = json.dumps({"poort": poort, "actie": actie, "server": SERVER, **velden})
    r = subprocess.run([_node(), str(CDP_JS), cfg], capture_output=True, text=True, timeout=60, check=False)
    regels = r.stdout.strip().splitlines()
    assert r.returncode == 0 and regels, r.stderr[-500:]
    return json.loads(regels[-1])


def _pagina(ws_url: str) -> list[dict]:
    return [{"type": "page", "url": f"{SERVER}/web/index.html", "webSocketDebuggerUrl": ws_url}]


@pytest.fixture
def lokker():
    lo = Lokker()
    yield lo
    lo.sluit()


@pytest.mark.parametrize("actie", ["verbind", "inloggen", "teksten"])
@pytest.mark.parametrize("ws_pad", [
    "/websocket-uit-de-container",  # de aanval van de review: een eigen pad naar een andere dienst
    "/devtools/page/ABC?x=1",  # extra's na het pad
    "/devtools/page/../../json",  # geen vast paginapad
    "/devtools/browser/ABC",  # alleen een paginadoel
])
def test_vreemd_websocketadres_uit_de_container_wordt_geweigerd(lokker, actie, ws_pad):
    nep = NepCdp(_pagina(f"ws://127.0.0.1:{lokker.poort}{ws_pad}"))
    try:
        uit = cdp(nep.poort, actie, gebruiker="jc3kijker", wachtwoord="Abc123willekeurig")
    finally:
        nep.sluit()
    lokker.sluit()
    assert uit["ok"] is False and "webSocketDebuggerUrl geweigerd" in uit.get("fout", ""), uit
    assert lokker.ontvangen == []  # nooit naar het adres uit de container
    assert [p for p, _u in nep.verzoeken] == ["/json/list"]  # en ook geen WebSocket naar de doorgifte


@pytest.mark.parametrize("actie", ["doelen", "verbind", "inloggen"])
def test_doorverwijzing_van_json_list_wordt_niet_gevolgd(lokker, actie):
    nep = NepCdp(doorverwijzing=f"http://127.0.0.1:{lokker.poort}/redirect-uit-de-container")
    try:
        uit = cdp(nep.poort, actie, gebruiker="jc3kijker", wachtwoord="Abc123willekeurig")
    finally:
        nep.sluit()
    lokker.sluit()
    assert uit["ok"] is False and uit.get("fout"), uit
    assert lokker.ontvangen == []
    assert [p for p, _u in nep.verzoeken] == ["/json/list"]


def test_websocket_gaat_altijd_naar_de_doorgifte_op_127_0_0_1_met_alleen_het_pad(lokker):
    """Een geldig paginapad met een vreemd adres: de WebSocket gaat naar de doorgifte (nep-CDP), niet naar de lokker."""
    nep = NepCdp(_pagina(f"ws://127.0.0.1:{lokker.poort}/devtools/page/ABC-123def"))
    try:
        uit = cdp(nep.poort, "teksten")
    finally:
        nep.sluit()
    lokker.sluit()
    assert uit["ok"] is False  # de nep-CDP spreekt geen WebSocket
    assert lokker.ontvangen == []
    assert nep.verzoeken[0] == ("/json/list", "")
    assert nep.verzoeken[1][0] == "/devtools/page/ABC-123def" and nep.verzoeken[1][1].lower() == "websocket"


def test_het_vaste_padpatroon_staat_in_de_besturing():
    bron = CDP_JS.read_text(encoding="utf-8")
    assert "redirect: 'error'" in bron
    assert re.search(r"/\^\\/devtools\\/page\\/\[A-Za-z0-9-\]\+\$/", bron)
    assert "new WebSocket(doel.webSocketDebuggerUrl)" not in bron
