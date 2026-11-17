"""Eigen, afgeschermd Docker-netwerk per testrun en de proef dat het afgeschermd is (S-P40-72; ADR-0011, besluit 15).

De emulator- en de desktopcontainer draaiden eerst op het hostnetwerk: dan zagen ze elke dienst op de
ontwikkelmachine (ook wat alleen op 127.0.0.1 luistert). Nu krijgt elke testserver een eigen netwerk; de emulator of
desktop hangt alleen aan dat netwerk en bereikt de server op ``http://testserver:8096``.

Gemeten op deze machine (Docker 29.1.3): een netwerk met alleen ``--internal`` laat de container de host nog bereiken
via het gateway-adres van het netwerk (een luisteraar op 0.0.0.0 kreeg de verbinding). Daarom ook de bridge-optie
``inhibit_ipv4``: de bridge krijgt op de host geen IPv4-adres, de container heeft alleen een route naar het eigen subnet
en elk adres van de host is "Network is unreachable". De server hangt daarnaast aan het standaard-bridgenetwerk met
``-p 127.0.0.1:<poort>:8096``, zodat het harnas op de host hem blijft bereiken.

IPv6 (review R-VEILIG-2): het netwerk is expliciet zonder IPv6 (``--ipv6=false``). Gemeten: met IPv6 op het netwerk
bereikte een container de host via het IPv6-adres van de bridge, terwijl de proef op IPv4 "geslaagd" gaf.

``afscherming`` toont dat bij elke start opnieuw aan (fail-closed): een tijdelijke dual-stack-luisteraar op alle IPv4-
én IPv6-adressen van de host (``::``), en vanuit de container een TCP-verbinding naar het eerste adres van het subnet
(waar anders de gateway, dus de host, zit), naar elk IPv4-adres en naar elk IPv6-adres van de host; de host mag geen
adres in het subnet hebben en de container geen IPv6-adres buiten ``lo`` (``/proc/net/if_inet6``). Verwacht: geen
enkele verbinding. Controles laten zien dat de proef kan falen: de luisteraar is vanaf de host zelf bereikbaar (IPv4
en IPv6), en de testserver is vanuit de container bereikbaar. In het bewijs staan geen adressen en geen interfacenamen
(die kunnen een MAC-adres bevatten), alleen het soort interface en de uitkomst.

Opruimen: elk testnetwerk krijgt ``LABEL`` en het eigenaarproces (pid, starttijd en PID-namespace,
``EIGENAAR_LABEL``). Vóór een nieuw netwerk ruimt ``ruim_verweesde_netwerken`` de testnetwerken op van een harnasproces
in dezelfde PID-namespace dat niet meer bestaat (bv. na SIGKILL); een netwerk van een lopend proces, ook van een andere
agent, blijft staan. Een pid zegt alleen iets binnen de eigen PID-namespace: een netwerk uit een andere (of onbekende)
PID-namespace, bijvoorbeeld van een harnas in een container of sandbox, blijft altijd staan (review R-HERREV-1).
Hetzelfde geldt voor de server-, emulator- en desktopcontainer (``ruim_verweesde_containers``); containers hebben per
run een unieke naam.

De sleutel van het eigenaarlabel is ``jelly-leon-clients.compat.eigenaar2`` (review R-HERREV2-1). Een oudere
harnasversie (381ad53 t/m efe0daa) las onder de oude sleutel ``jelly-leon-clients.compat.eigenaar`` alleen
``<pid>:<starttijd>`` en hield de waarde met drie delen voor een dode eigenaar: zij haalde dan het netwerk van een
levende nieuwe run weg. Onder de nieuwe sleutel ziet zo'n versie geen eigenaarlabel en laat het object staan. Andersom
leest deze versie alleen de nieuwe sleutel: een object met alleen de oude sleutel blijft staan (bij twijfel blijven
staan; een netwerk van een oude, afgebroken run moet dan met de hand weg).

Is ``/proc/<pid>`` niet leesbaar terwijl het eigen ``/proc`` dat wel is (``/proc`` met ``hidepid``: een proces van een
andere gebruiker is onzichtbaar), dan beslist ``os.kill(pid, 0)``: alleen ``ProcessLookupError`` betekent dood;
``PermissionError`` of geen fout betekent levend (review R-HERREV2-2).
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import subprocess
import threading
from pathlib import Path
from typing import Any

from .scenario import GESLAAGD, MISLUKT

NETWERK_OPTIES = ("--internal", "--ipv6=false", "-o", "com.docker.network.bridge.inhibit_ipv4=true")
LABEL = "jelly-leon-clients.compat=testnetwerk"
# "<pid>:<starttijd>:<PID-namespace>" van het harnasproces dat het netwerk (of de container) maakte. Bewust een nieuwe
# sleutel (review R-HERREV2-1): een oudere harnasversie las de oude sleutel ("jelly-leon-clients.compat.eigenaar") als
# "<pid>:<starttijd>" en ruimde dan het netwerk van een levende run op. Deze versie leest de oude sleutel niet: een
# object met alleen die sleutel blijft staan.
EIGENAAR_LABEL = "jelly-leon-clients.compat.eigenaar2"
SERVER_ALIAS = "testserver"
SERVER_POORT = 8096
BESCHRIJVING = (
    "eigen Docker-netwerk per run (--internal, zonder IPv6, bridge zonder IPv4-adres op de host); "
    "alleen de testserver erop"
)


def docker(*args: str, check: bool = True, timeout: float = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=timeout)


class Testnetwerk:
    """Eén afgeschermd netwerk; de naam hoort bij één testserver (en is dus per run uniek, V-008)."""

    def __init__(self, naam: str) -> None:
        self.naam = naam

    def maak(self) -> None:
        ruim_verweesde_netwerken()  # netwerken van een afgebroken harnasproces (op label en eigenaar)
        self.verwijder()  # een achtergebleven netwerk van een afgebroken run met dezelfde naam
        docker(
            "network", "create", *NETWERK_OPTIES, "--label", LABEL, "--label", f"{EIGENAAR_LABEL}={eigenaar()}",
            self.naam,
        )  # fmt: skip

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


def _starttijd(pid: int) -> str | None:
    """Starttijd van een proces (veld 22 van ``/proc/<pid>/stat``); None als het niet leesbaar is: het proces bestaat
    niet, of ``/proc`` verbergt het (``hidepid``, een proces van een andere gebruiker). ``eigenaar_leeft`` maakt dat
    onderscheid met ``os.kill(pid, 0)``."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return stat.rsplit(")", 1)[1].split()[19]
    except IndexError:
        return None


def pid_namespace() -> str | None:
    """PID-namespace van dit proces (``pid:[<inode>]`` uit ``/proc/self/ns/pid``); None als dat niet leesbaar is."""
    try:
        return os.readlink("/proc/self/ns/pid")
    except OSError:
        return None


def eigenaar() -> str:
    """``<pid>:<starttijd>:<PID-namespace>`` van dit proces (de starttijd beschermt tegen een hergebruikt pid, de
    namespace tegen hetzelfde pid in een container of sandbox)."""
    return f"{os.getpid()}:{_starttijd(os.getpid()) or 'onbekend'}:{pid_namespace() or 'onbekend'}"


def eigenaar_leeft(waarde: str) -> bool:
    """Bestaat het proces uit ``EIGENAAR_LABEL`` nog? Bij twijfel ja: dan blijft het netwerk staan. Alleen binnen
    dezelfde PID-namespace is dat vast te stellen; een andere, onbekende of ontbrekende namespace telt als levend
    (review R-HERREV-1). Is ``/proc/<pid>`` niet leesbaar, dan beslist ``os.kill(pid, 0)``: alleen
    ``ProcessLookupError`` is dood; ``PermissionError`` (een proces van een andere gebruiker dat ``/proc`` met
    ``hidepid`` verbergt), geen fout of een andere fout is levend (review R-HERREV2-2). Een pid van 0 of lager (in
    ``os.kill`` een procesgroep of alle processen) telt als levend."""
    pid_tekst, start, namespace = ([*waarde.split(":", 2), "", ""])[:3]
    try:
        pid = int(pid_tekst)
    except ValueError:
        return True
    if pid <= 0:
        return True  # geen enkel proces: os.kill zou een groep of alle processen bedoelen
    eigen = pid_namespace()
    if eigen is None or namespace != eigen:
        return True  # andere of onbekende PID-namespace: dit pid zegt hier niets
    if _starttijd(os.getpid()) is None:
        return True  # /proc niet leesbaar: niets vast te stellen
    huidig = _starttijd(pid)
    if huidig is None:
        return not _bestaat_niet(pid)  # /proc/<pid> niet leesbaar: weg, of verborgen (hidepid)
    return start in ("", "onbekend") or huidig == start  # andere starttijd: het pid is hergebruikt


def _bestaat_niet(pid: int) -> bool:
    """Alleen True als de kernel zegt dat ``pid`` niet bestaat (``os.kill(pid, 0)`` geeft ``ProcessLookupError``).
    ``PermissionError`` (het proces bestaat, van een andere gebruiker), geen fout of een andere fout: False."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except (OSError, OverflowError):
        return False  # PermissionError en al het andere: bij twijfel levend
    return False


def ruim_verweesde_netwerken() -> list[str]:
    """Testnetwerken (``LABEL``) waarvan het eigenaarproces aantoonbaar niet meer bestaat, weghalen (vervolgpunt van de
    review R-TECH: na een SIGKILL bleef het netwerk staan). Zonder eigenaarlabel, met een levend eigenaarproces of uit
    een andere PID-namespace blijft een netwerk staan. Geeft de namen van de verwijderde netwerken."""
    r = docker(
        "network", "ls", "--filter", f"label={LABEL}", "--format", '{{.Name}}\t{{.Label "' + EIGENAAR_LABEL + '"}}',
        check=False,
    )  # fmt: skip
    weg: list[str] = []
    if r.returncode != 0:
        return weg
    for regel in r.stdout.splitlines():
        naam, _, waarde = regel.partition("\t")
        if naam.strip() and waarde.strip() and not eigenaar_leeft(waarde.strip()):
            Testnetwerk(naam.strip()).verwijder()
            weg.append(naam.strip())
    return weg


def ruim_verweesde_containers(label: str) -> list[str]:
    """Containers met ``label`` waarvan het eigenaarproces aantoonbaar niet meer bestaat (zelfde regels als
    ``ruim_verweesde_netwerken``) weghalen. Nodig omdat containers per run een unieke naam hebben: een vaste naam die de
    volgende run eerst weghaalt, kon ook de container van een andere lopende run raken. Geeft de verwijderde namen."""
    r = docker(
        "ps", "-a", "--filter", f"label={label}", "--format", '{{.Names}}\t{{.Label "' + EIGENAAR_LABEL + '"}}',
        check=False,
    )  # fmt: skip
    weg: list[str] = []
    if r.returncode != 0:
        return weg
    for regel in r.stdout.splitlines():
        naam, _, waarde = regel.partition("\t")
        if naam.strip() and waarde.strip() and not eigenaar_leeft(waarde.strip()):
            docker("rm", "-f", naam.strip(), check=False)
            weg.append(naam.strip())
    return weg


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


def hostadressen_v6() -> list[tuple[str, str, str]]:
    """(interface, IPv6-adres om te proberen, scope) van elke interface van de host behalve loopback (``ip -j -6
    addr``). Een link-local adres krijgt de zone ``%eth0``: zo heet de netwerkinterface van de container."""
    r = subprocess.run(["ip", "-j", "-6", "addr", "show"], capture_output=True, text=True, check=True, timeout=30)
    uit = []
    for iface in json.loads(r.stdout or "[]"):
        for info in iface.get("addr_info", []):
            adres, scope = info.get("local", ""), info.get("scope", "")
            if not adres or scope == "host" or ipaddress.ip_address(adres).is_loopback:
                continue
            uit.append((iface.get("ifname", "?"), f"{adres}%eth0" if scope == "link" else adres, scope))
    return uit


def ipv6_in_container(container: str) -> tuple[int | None, str]:
    """Aantal IPv6-adressen in de container buiten ``lo`` (``/proc/net/if_inet6``; de laatste kolom is de interface).
    ``None`` als het niet vast te stellen is (telt als mislukt, fail-closed). De interfacenamen komen niet in de
    uitkomst."""
    r = subprocess.run(
        ["docker", "exec", container, "cat", "/proc/net/if_inet6"], capture_output=True, text=True, timeout=60,
        check=False,
    )  # fmt: skip
    if r.returncode != 0:
        if "No such file" in r.stderr:
            return 0, "geen IPv6 in de kernel van de container"
        return None, f"IPv6-adressen in de container niet leesbaar (exitcode {r.returncode})"
    buiten_lo = [regel for regel in r.stdout.splitlines() if regel.split() and regel.split()[-1] != "lo"]
    return len(buiten_lo), ("alleen lo" if not buiten_lo else f"{len(buiten_lo)} IPv6-adres(sen) buiten lo")


class Luisteraar:
    """Tijdelijke TCP-luisteraar op alle IPv4- en IPv6-adressen van de host (dual-stack ``::``, vrije poort); telt
    verbindingen. Zonder IPv6 op de host alleen ``0.0.0.0`` (``dual_stack`` False)."""

    def __init__(self) -> None:
        try:
            self.sock = socket.socket(socket.AF_INET6)
            self.sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("::", 0))  # bewust: de proef zoekt juist een dienst op alle adressen
            self.dual_stack = True
        except OSError:
            self.sock = socket.socket()
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("0.0.0.0", 0))  # noqa: S104 - bewust: de proef zoekt juist een dienst op alle adressen
            self.dual_stack = False
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

    def controle_vanaf_host(self, adres: str = "127.0.0.1") -> bool:
        """De luisteraar werkt (anders bewijst 'niet bereikt' niets); telt niet mee bij de verbindingen."""
        voor = self.verbindingen
        try:
            with socket.create_connection((adres, self.poort), timeout=5):
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
        controle_host = luisteraar.controle_vanaf_host("127.0.0.1")
        controle_host6 = luisteraar.dual_stack and luisteraar.controle_vanaf_host("::1")
        subnet = netwerk.subnet()
        host = hostadressen()
        host6 = hostadressen_v6()
        # Zonder inhibit_ipv4 heeft de host een adres in het subnet (de gateway); dat mag hier niet zo zijn.
        labels = [f"hostadres {n} ({soort_interface(iface)})" for n, (iface, _a) in enumerate(host, 1)]
        host_in_subnet = [
            lbl for lbl, (_i, a) in zip(labels, host, strict=True)
            if subnet and ipaddress.ip_address(a) in ipaddress.ip_network(subnet)
        ]  # fmt: skip
        doelen = [("eerste adres van het subnet (zonder inhibit_ipv4 de host)", gateway_adres(subnet))]
        doelen += [(lbl, adres) for lbl, (_i, adres) in zip(labels, host, strict=True)]
        doelen += [
            (f"IPv6-hostadres {n} ({soort_interface(iface)}, {'link-local' if scope == 'link' else 'globaal'})", adres)
            for n, (iface, adres, scope) in enumerate(host6, 1)
        ]
        ipv6_aantal, ipv6_tekst = ipv6_in_container(container)
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
    if host6 and not controle_host6:
        redenen.append("de tijdelijke luisteraar was via IPv6 vanaf de host zelf niet bereikbaar (proef ongeldig)")
    if ipv6_aantal is None:
        redenen.append(ipv6_tekst)
    elif ipv6_aantal:
        redenen.append(f"de container heeft IPv6 ({ipv6_tekst}); het testnetwerk moet zonder IPv6 zijn")
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
        "luisteraar": (
            "tijdelijke TCP-luisteraar op alle IPv4- en IPv6-adressen van de host (dual-stack ::, vrije poort)"
            if luisteraar.dual_stack
            else "tijdelijke TCP-luisteraar op alle IPv4-adressen van de host (0.0.0.0, vrije poort; host zonder IPv6)"
        ),
        "controle_luisteraar_vanaf_host": "bereikt" if controle_host else "niet bereikt",
        "controle_luisteraar_vanaf_host_ipv6": "bereikt" if controle_host6 else "niet bereikt",
        "ipv6_in_container": ipv6_tekst,
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
