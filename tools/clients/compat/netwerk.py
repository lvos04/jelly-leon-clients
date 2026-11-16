"""Eigen, afgeschermd Docker-netwerk per testrun en de proef dat het afgeschermd is (S-P40-72; ADR-0011, besluit 15).

De emulator- en de desktopcontainer draaiden eerst op het hostnetwerk: dan zagen ze elke dienst op de
ontwikkelmachine (ook wat alleen op 127.0.0.1 luistert). Nu krijgt elke testserver een eigen netwerk; de emulator of
desktop hangt alleen aan dat netwerk en bereikt de server op ``http://testserver:8096``.

Gemeten op deze machine (Docker 29.1.3): een netwerk met alleen ``--internal`` laat de container de host nog bereiken
via het gateway-adres van het netwerk (een luisteraar op 0.0.0.0 kreeg de verbinding). Daarom ook de bridge-optie
``inhibit_ipv4``: de bridge krijgt op de host geen IPv4-adres, de container heeft alleen een route naar het eigen subnet
en elk adres van de host is "Network is unreachable". De server hangt daarnaast aan het standaard-bridgenetwerk met
``-p 127.0.0.1:<poort>:8096``, zodat het harnas op de host hem blijft bereiken.

``afscherming`` toont dat bij elke start opnieuw aan (fail-closed): een tijdelijke luisteraar op alle IPv4-adressen
van de host, en vanuit de container een TCP-verbinding naar het eerste adres van het subnet (waar anders de gateway,
dus de host, zit) en naar elk IPv4-adres van de host; de host mag ook geen adres in het subnet hebben. Verwacht: geen
enkele verbinding. Twee controles laten zien dat de proef kan falen: de luisteraar is vanaf de host zelf bereikbaar, en
de testserver is vanuit de container bereikbaar. In het bewijs staan
geen adressen en geen interfacenamen (die kunnen een MAC-adres bevatten), alleen het soort interface en de uitkomst.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import subprocess
import threading
from typing import Any

from .scenario import GESLAAGD, MISLUKT

NETWERK_OPTIES = ("--internal", "-o", "com.docker.network.bridge.inhibit_ipv4=true")
LABEL = "jelly-leon-clients.compat=testnetwerk"
SERVER_ALIAS = "testserver"
SERVER_POORT = 8096
BESCHRIJVING = (
    "eigen Docker-netwerk per run (--internal, bridge zonder IPv4-adres op de host); alleen de testserver erop"
)


def docker(*args: str, check: bool = True, timeout: float = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=timeout)


class Testnetwerk:
    """Eén afgeschermd netwerk; de naam hoort bij één testserver (en is dus per run uniek, V-008)."""

    def __init__(self, naam: str) -> None:
        self.naam = naam

    def maak(self) -> None:
        self.verwijder()  # een achtergebleven netwerk van een afgebroken run met dezelfde naam
        docker("network", "create", *NETWERK_OPTIES, "--label", LABEL, self.naam)

    def verbind(self, container: str, alias: str | None = None) -> None:
        docker("network", "connect", *(["--alias", alias] if alias else []), self.naam, container)

    def subnet(self) -> str:
        r = docker("network", "inspect", "--format", "{{json .IPAM.Config}}", self.naam, check=False)
        try:
            return json.loads(r.stdout or "[]")[0]["Subnet"]
        except (ValueError, IndexError, KeyError):
            return ""

    def verwijder(self) -> None:
        """Netwerk weg, ook als er nog een eigen container aan hangt (die wordt eerst losgekoppeld)."""
        if docker("network", "rm", self.naam, check=False).returncode == 0:
            return
        r = docker("network", "inspect", "--format", "{{range .Containers}}{{.Name}} {{end}}", self.naam, check=False)
        if r.returncode != 0:
            return  # bestaat niet (meer)
        for container in r.stdout.split():
            docker("network", "disconnect", "-f", self.naam, container, check=False)
        docker("network", "rm", self.naam, check=False)


def tcp_poging(container: str, adres: str, poort: int, timeout: int = 5) -> tuple[bool, str]:
    """Eén TCP-verbinding vanuit ``container`` (bash ``/dev/tcp``; bash en ``timeout`` staan in beide images).
    Geeft (bereikt, uitkomst); het adres zelf komt niet in de uitkomst."""
    r = subprocess.run(
        ["docker", "exec", container, "timeout", str(timeout), "bash", "-c", 'exec 3<>/dev/tcp/"$0"/"$1"', adres,
         str(poort)],
        capture_output=True,
        text=True,
        timeout=timeout + 60,
        check=False,
    )  # fmt: skip
    if r.returncode == 0:
        return True, "bereikt"
    if r.returncode == 124:
        return False, "time-out"
    regels = [x for x in r.stderr.strip().splitlines() if x.strip()]
    tekst = regels[-1].rsplit(":", 1)[-1].strip() if regels else f"exitcode {r.returncode}"
    return False, tekst.replace(adres, "<adres>")


def soort_interface(naam: str) -> str:
    """Alleen het soort interface in het bewijs: een interfacenaam kan een MAC-adres bevatten (``enx<mac>``)."""
    return "Docker-bridge" if naam == "docker0" or naam.startswith("br-") else "netwerkinterface"


def hostadressen() -> list[tuple[str, str]]:
    """(interface, IPv4-adres) van elke interface van de host behalve loopback (``ip -j -4 addr``)."""
    r = subprocess.run(["ip", "-j", "-4", "addr", "show"], capture_output=True, text=True, check=True, timeout=30)
    uit = []
    for iface in json.loads(r.stdout or "[]"):
        for info in iface.get("addr_info", []):
            adres = info.get("local", "")
            if adres and not ipaddress.ip_address(adres).is_loopback:
                uit.append((iface.get("ifname", "?"), adres))
    return uit


class Luisteraar:
    """Tijdelijke TCP-luisteraar op alle IPv4-adressen van de host (``0.0.0.0``, vrije poort); telt verbindingen."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", 0))  # noqa: S104 - bewust: de proef zoekt juist een dienst op alle adressen
        self.sock.listen(16)
        self.sock.settimeout(0.5)
        self.poort: int = self.sock.getsockname()[1]
        self.verbindingen = 0
        self._stop = threading.Event()
        self._draad = threading.Thread(target=self._accepteer, daemon=True)
        self._draad.start()

    def _accepteer(self) -> None:
        while not self._stop.is_set():
            try:
                klant, _ = self.sock.accept()
            except (TimeoutError, OSError):
                continue
            self.verbindingen += 1
            klant.close()

    def controle_vanaf_host(self) -> bool:
        """De luisteraar werkt (anders bewijst 'niet bereikt' niets); telt niet mee bij de verbindingen."""
        voor = self.verbindingen
        try:
            with socket.create_connection(("127.0.0.1", self.poort), timeout=5):
                pass
        except OSError:
            return False
        for _ in range(20):
            if self.verbindingen > voor:
                self.verbindingen = voor
                return True
            self._stop.wait(0.1)
        return False

    def sluit(self) -> None:
        self._stop.set()
        self._draad.join(timeout=5)
        self.sock.close()


def gateway_adres(subnet: str) -> str:
    """Het eerste adres van het subnet: daar zou de gateway zitten (zonder ``inhibit_ipv4`` de host zelf)."""
    return str(next(ipaddress.ip_network(subnet, strict=False).hosts())) if subnet else ""


def afscherming(container: str, netwerk: Testnetwerk) -> dict[str, Any]:
    """Proef: vanuit ``container`` is geen poort van de host bereikbaar, de testserver wel. Fail-closed: elk
    twijfelgeval (luisteraar werkt niet, server niet bereikbaar, geen hostadres gevonden) is ``mislukt``."""
    luisteraar = Luisteraar()
    try:
        controle_host = luisteraar.controle_vanaf_host()
        subnet = netwerk.subnet()
        host = hostadressen()
        # Zonder inhibit_ipv4 heeft de host een adres in het subnet (de gateway); dat mag hier niet zo zijn.
        labels = [f"hostadres {n} ({soort_interface(iface)})" for n, (iface, _a) in enumerate(host, 1)]
        host_in_subnet = [
            lbl for lbl, (_i, a) in zip(labels, host, strict=True)
            if subnet and ipaddress.ip_address(a) in ipaddress.ip_network(subnet)
        ]  # fmt: skip
        doelen = [("eerste adres van het subnet (zonder inhibit_ipv4 de host)", gateway_adres(subnet))]
        doelen += [(lbl, adres) for lbl, (_i, adres) in zip(labels, host, strict=True)]
        pogingen = []
        for doel, adres in doelen:
            if not adres:
                pogingen.append({"doel": doel, "bereikt": None, "uitkomst": "adres onbekend"})
                continue
            bereikt, tekst = tcp_poging(container, adres, luisteraar.poort)
            pogingen.append({"doel": doel, "bereikt": bereikt, "uitkomst": tekst})
        server_bereikt, server_tekst = tcp_poging(container, SERVER_ALIAS, SERVER_POORT, timeout=10)
        luisteraar._stop.wait(1.0)  # een late verbinding nog laten tellen
        verbindingen = luisteraar.verbindingen
    finally:
        luisteraar.sluit()
    redenen = []
    if not subnet:
        redenen.append("subnet van het testnetwerk onbekend")
    if host_in_subnet:
        redenen.append(f"de host heeft een adres in het testnetwerk (gateway): {', '.join(host_in_subnet)}")
    if not controle_host:
        redenen.append("de tijdelijke luisteraar was vanaf de host zelf niet bereikbaar (proef ongeldig)")
    if not server_bereikt:
        redenen.append(f"de testserver is vanuit de container niet bereikbaar ({server_tekst})")
    if not any(p["doel"].startswith("hostadres") for p in pogingen):
        redenen.append("geen hostadres gevonden om te proberen")
    redenen += [f"{p['doel']}: {p['uitkomst']}" for p in pogingen if p["bereikt"] is not False]
    if verbindingen:
        redenen.append(f"de luisteraar op de host kreeg {verbindingen} verbinding(en) vanuit de container")
    return {
        "uitkomst": MISLUKT if redenen else GESLAAGD,
        "netwerk": BESCHRIJVING,
        "luisteraar": "tijdelijke TCP-luisteraar op alle IPv4-adressen van de host (0.0.0.0, vrije poort)",
        "controle_luisteraar_vanaf_host": "bereikt" if controle_host else "niet bereikt",
        "controle_testserver": server_tekst,
        "host_adres_in_testnetwerk": bool(host_in_subnet),
        "pogingen": pogingen,
        "verbindingen_bij_luisteraar": verbindingen,
        **({"reden": "; ".join(redenen)} if redenen else {}),
    }


def eis_afscherming(container: str, netwerk: Testnetwerk) -> dict[str, Any]:
    """``afscherming`` en weigeren (RuntimeError) als de container meer ziet dan de testserver."""
    uit = afscherming(container, netwerk)
    if uit["uitkomst"] != GESLAAGD:
        raise RuntimeError(f"testnetwerk niet afgeschermd: {uit.get('reden')}")
    return uit
