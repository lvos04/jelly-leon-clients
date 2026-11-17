"""Afschermingsproef van het testnetwerk (compat/netwerk.py; S-P40-72) zonder echte Docker.

De echte proef draait bij elke emulator- en desktopstart (fail-closed) en staat per run in het bewijs
(``netwerkafscherming``). Hier: de beoordeling, de echte luisteraar op de host en dat er geen adressen in de uitkomst
komen. Testadressen komen uit de documentatiereeksen van RFC 5737 en RFC 3849 (geen echte apparaten).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess

import pytest
from compat import netwerk
from compat import scenario as sc

HOST = [("eth0", "192.0.2.10"), ("docker0", "198.51.100.1")]  # eth0 staat hier voor bv. enx<mac>
HOST6 = [("br-0123456789ab", "fe80::db8:1%eth0", "link"), ("eth0", "2001:db8::10", "global")]
SUBNET = "203.0.113.0/24"


class NepNetwerk(netwerk.Testnetwerk):
    def __init__(self, subnet: str = SUBNET) -> None:
        super().__init__("jlc-net-proef")
        self._subnet = subnet

    def subnet(self) -> str:
        return self._subnet


def _zet(monkeypatch, host=HOST, bereikbaar=(), server=True, host6=HOST6, ipv6=(0, "alleen lo")):
    pogingen = []

    def nep_poging(container, adres, poort, timeout=5):
        pogingen.append((container, adres, poort))
        if adres == netwerk.SERVER_ALIAS:
            return (True, "bereikt") if server else (False, "Name or service not known")
        if adres in bereikbaar:
            return True, "bereikt"
        return False, "Network is unreachable"

    monkeypatch.setattr(netwerk, "tcp_poging", nep_poging)
    monkeypatch.setattr(netwerk, "hostadressen", lambda: list(host))
    monkeypatch.setattr(netwerk, "hostadressen_v6", lambda: list(host6))
    monkeypatch.setattr(netwerk, "ipv6_in_container", lambda container: ipv6)
    return pogingen


def test_afgeschermd_als_geen_hostadres_bereikbaar_is_en_de_server_wel(monkeypatch):
    pogingen = _zet(monkeypatch)
    uit = netwerk.afscherming("jlc-jc3-emulator", NepNetwerk())
    assert uit["uitkomst"] == sc.GESLAAGD and "reden" not in uit
    assert uit["controle_luisteraar_vanaf_host"] == "bereikt" and uit["controle_testserver"] == "bereikt"
    assert uit["verbindingen_bij_luisteraar"] == 0 and uit["host_adres_in_testnetwerk"] is False
    # elk hostadres (IPv4 en IPv6) en het eerste adres van het subnet, op de poort van de tijdelijke luisteraar
    geprobeerd = {a for _c, a, _p in pogingen}
    assert {"192.0.2.10", "198.51.100.1", "203.0.113.1", "fe80::db8:1%eth0", "2001:db8::10",
            netwerk.SERVER_ALIAS} == geprobeerd
    doelen = [d["doel"] for d in uit["pogingen"]]
    assert doelen[1:] == [
        "hostadres 1 (netwerkinterface)", "hostadres 2 (Docker-bridge)",
        "IPv6-hostadres 1 (Docker-bridge, link-local)", "IPv6-hostadres 2 (netwerkinterface, globaal)",
    ]
    assert uit["ipv6_in_container"] == "alleen lo" and uit["controle_luisteraar_vanaf_host_ipv6"] == "bereikt"
    # geen adressen en geen interfacenamen (enx<mac>) in het bewijs
    tekst = json.dumps(uit)
    assert not any(a in tekst for a in ("192.0.2.10", "198.51.100.1", "203.0.113", "eth0", "docker0", "fe80",
                                        "2001:db8", "br-0123"))


@pytest.mark.parametrize(("instelling", "reden"), [
    # de negatieve test: een poort van de host is bereikbaar
    ({"bereikbaar": ("192.0.2.10",)}, "hostadres 1 (netwerkinterface): bereikt"),
    ({"bereikbaar": ("203.0.113.1",)}, "eerste adres van het subnet"),
    ({"server": False}, "testserver is vanuit de container niet bereikbaar"),  # proef kan niet slagen = ongeldig
    # zonder inhibit_ipv4 heeft de host een adres in het subnet
    ({"host": [("br-x", "203.0.113.1"), *HOST]}, "de host heeft een adres in het testnetwerk"),
    ({"host": []}, "geen hostadres gevonden"),
    # IPv6 (review R-VEILIG-2): een IPv6-pad naar de host, IPv6 in de container of geen meting is mislukt
    ({"bereikbaar": ("2001:db8::10",)}, "IPv6-hostadres 2 (netwerkinterface, globaal): bereikt"),
    ({"bereikbaar": ("fe80::db8:1%eth0",)}, "IPv6-hostadres 1 (Docker-bridge, link-local): bereikt"),
    ({"ipv6": (2, "2 IPv6-adres(sen) buiten lo")}, "de container heeft IPv6"),
    ({"ipv6": (None, "IPv6-adressen in de container niet leesbaar (exitcode 1)")}, "niet leesbaar"),
])
def test_niet_afgeschermd_of_ongeldig_is_mislukt(monkeypatch, instelling, reden):
    _zet(monkeypatch, **instelling)
    uit = netwerk.afscherming("c", NepNetwerk())
    assert uit["uitkomst"] == sc.MISLUKT and reden in uit["reden"]
    with pytest.raises(RuntimeError, match="niet afgeschermd"):
        netwerk.eis_afscherming("c", NepNetwerk())


def test_onbekend_subnet_is_mislukt(monkeypatch):
    _zet(monkeypatch)
    uit = netwerk.afscherming("c", NepNetwerk(subnet=""))
    assert uit["uitkomst"] == sc.MISLUKT and "subnet" in uit["reden"]


def test_een_verbinding_bij_de_echte_luisteraar_telt_als_lek(monkeypatch):
    """Ook als de poging zelf 'niet bereikt' meldt: een verbinding die de luisteraar op de host ziet, is een lek."""
    monkeypatch.setattr(netwerk, "hostadressen", lambda: [("lo-test", "127.0.0.2")])

    def stiekem(container, adres, poort, timeout=5):
        if adres == netwerk.SERVER_ALIAS:
            return True, "bereikt"
        with socket.create_connection(("127.0.0.1", poort), timeout=5):
            pass
        return False, "time-out"

    monkeypatch.setattr(netwerk, "tcp_poging", stiekem)
    uit = netwerk.afscherming("c", NepNetwerk())
    assert uit["uitkomst"] == sc.MISLUKT and uit["verbindingen_bij_luisteraar"] >= 1


def test_een_ipv6_verbinding_bij_de_echte_luisteraar_telt_als_lek(monkeypatch):
    """De luisteraar is dual-stack: ook een verbinding over IPv6 (hier ::1) telt als lek (review R-VEILIG-2)."""
    monkeypatch.setattr(netwerk, "hostadressen", lambda: [("lo-test", "127.0.0.2")])
    monkeypatch.setattr(netwerk, "hostadressen_v6", lambda: [])
    monkeypatch.setattr(netwerk, "ipv6_in_container", lambda container: (0, "alleen lo"))

    def via_ipv6(container, adres, poort, timeout=5):
        if adres == netwerk.SERVER_ALIAS:
            return True, "bereikt"
        with socket.create_connection(("::1", poort), timeout=5):
            pass
        return False, "time-out"

    monkeypatch.setattr(netwerk, "tcp_poging", via_ipv6)
    uit = netwerk.afscherming("c", NepNetwerk())
    assert uit["uitkomst"] == sc.MISLUKT and uit["verbindingen_bij_luisteraar"] >= 1


def test_luisteraar_luistert_op_alle_adressen_en_telt_de_hostcontrole_niet():
    lu = netwerk.Luisteraar()
    try:
        # dual-stack: alle IPv4- én IPv6-adressen (review R-VEILIG-2)
        assert lu.dual_stack and lu.sock.family == socket.AF_INET6 and lu.sock.getsockname()[0] == "::"
        assert lu.sock.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY) == 0
        assert lu.controle_vanaf_host("127.0.0.1") and lu.controle_vanaf_host("::1") and lu.verbindingen == 0
    finally:
        lu.sluit()


def test_host_met_ipv6_maar_luisteraar_niet_via_ipv6_bereikbaar_is_mislukt(monkeypatch):
    _zet(monkeypatch)
    monkeypatch.setattr(netwerk.Luisteraar, "controle_vanaf_host", lambda self, adres="127.0.0.1": adres != "::1")
    uit = netwerk.afscherming("c", NepNetwerk())
    assert uit["uitkomst"] == sc.MISLUKT and "via IPv6" in uit["reden"]


class _Uit:
    def __init__(self, code: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode, self.stdout, self.stderr = code, stdout, stderr


IF_INET6_LO = "00000000000000000000000000000001 01 80 10 80       lo\n"
IF_INET6_ETH0 = "fe800000000000000000000000000db8 2a 40 20 80     eth0\n"


@pytest.mark.parametrize(("uitvoer", "verwacht"), [
    (_Uit(0, IF_INET6_LO), (0, "alleen lo")),
    (_Uit(0, ""), (0, "alleen lo")),
    (_Uit(0, IF_INET6_LO + IF_INET6_ETH0), (1, "1 IPv6-adres(sen) buiten lo")),
    (_Uit(1, stderr="cat: /proc/net/if_inet6: No such file or directory"),
     (0, "geen IPv6 in de kernel van de container")),
    (_Uit(1, stderr="Error response from daemon: container is not running"), (None, None)),
])
def test_ipv6_in_de_container_leest_if_inet6(monkeypatch, uitvoer, verwacht):
    aanroepen = []
    monkeypatch.setattr(netwerk.subprocess, "run", lambda args, **k: (aanroepen.append(args), uitvoer)[1])
    aantal, tekst = netwerk.ipv6_in_container("c")
    assert aanroepen == [["docker", "exec", "c", "cat", "/proc/net/if_inet6"]]
    assert aantal == verwacht[0] and (verwacht[1] is None or tekst == verwacht[1])
    assert "eth0" not in tekst  # geen interfacenamen in het bewijs


def test_hostadressen_v6_zonder_loopback_en_link_local_met_de_zone_van_de_container(monkeypatch):
    ip_uit = json.dumps([
        {"ifname": "lo", "addr_info": [{"local": "::1", "scope": "host"}]},
        {"ifname": "br-0123456789ab", "addr_info": [{"local": "fe80::db8:1", "scope": "link"}]},
        {"ifname": "eth0", "addr_info": [{"local": "2001:db8::10", "scope": "global"}]},
    ])
    monkeypatch.setattr(netwerk.subprocess, "run", lambda args, **k: _Uit(0, ip_uit))
    assert netwerk.hostadressen_v6() == [("br-0123456789ab", "fe80::db8:1%eth0", "link"),
                                         ("eth0", "2001:db8::10", "global")]


# --- opruimen van netwerken van een afgebroken harnasproces (vervolgpunt R-TECH) ------------------------------------

NS = os.readlink("/proc/self/ns/pid")  # de eigen PID-namespace


def test_eigenaar_leeft_alleen_met_hetzelfde_pid_en_dezelfde_starttijd():
    assert netwerk.eigenaar_leeft(netwerk.eigenaar())  # dit proces
    pid, start, ns = netwerk.eigenaar().split(":", 2)
    assert start != "onbekend" and ns == NS
    assert not netwerk.eigenaar_leeft(f"{pid}:1:{NS}")  # zelfde pid, andere starttijd: hergebruikt pid
    assert not netwerk.eigenaar_leeft(f"999999999:1:{NS}")  # bestaat niet (boven pid_max)
    assert netwerk.eigenaar_leeft("geen-pid")  # onbekende vorm: niet aanraken


def test_eigenaar_in_een_andere_of_onbekende_pid_namespace_telt_als_levend():
    """Review R-HERREV-1: een pid zegt alleen iets in de eigen PID-namespace; bij twijfel blijft het netwerk staan."""
    assert netwerk.eigenaar_leeft("999999999:1:pid:[1]")  # andere namespace, pid bestaat hier niet
    assert netwerk.eigenaar_leeft(f"{os.getpid()}:1:pid:[1]")  # andere namespace, hier een ander proces
    assert netwerk.eigenaar_leeft("999999999:1")  # oude vorm zonder namespace
    assert netwerk.eigenaar_leeft("999999999:1:onbekend")


def test_alleen_netwerken_van_een_afgebroken_proces_worden_opgeruimd(monkeypatch):
    levend = netwerk.eigenaar()
    lijst = (f"jlc-dood-net\t999999999:1:{NS}\njlc-levend-net\t{levend}\njlc-oud-net\t\n"
             f"jlc-hergebruikt-net\t{os.getpid()}:1:{NS}\njlc-andere-ns-net\t999999999:1:pid:[1]\n")
    aanroepen = []

    def nep(*args, check=True, timeout=600):
        aanroepen.append(args)
        if args[:2] == ("network", "ls"):
            return subprocess.CompletedProcess(args, 0, stdout=lijst, stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(netwerk, "docker", nep)
    assert netwerk.ruim_verweesde_netwerken() == ["jlc-dood-net", "jlc-hergebruikt-net"]
    ls = next(a for a in aanroepen if a[:2] == ("network", "ls"))
    assert f"label={netwerk.LABEL}" in ls
    weg = [a[2] for a in aanroepen if a[:2] == ("network", "rm")]
    assert weg == ["jlc-dood-net", "jlc-hergebruikt-net"]  # levend, zonder eigenaarlabel of andere namespace: staan


def test_maak_ruimt_eerst_verweesde_netwerken_op_en_zet_de_eigenaar(monkeypatch):
    aanroepen = []

    def nep(*args, check=True, timeout=600):
        aanroepen.append(args)
        uit = f"jlc-dood-net\t999999999:1:{NS}\n" if args[:2] == ("network", "ls") else ""
        return subprocess.CompletedProcess(args, 0, stdout=uit, stderr="")

    monkeypatch.setattr(netwerk, "docker", nep)
    netwerk.Testnetwerk("jlc-nieuw-net").maak()
    soorten = [a[:2] for a in aanroepen]
    assert soorten.index(("network", "ls")) < soorten.index(("network", "create"))
    assert ("network", "rm", "jlc-dood-net") in aanroepen
    maak = next(a for a in aanroepen if a[:2] == ("network", "create"))
    assert f"{netwerk.EIGENAAR_LABEL}={netwerk.eigenaar()}" in maak and netwerk.LABEL in maak


def test_tcp_poging_meldt_geen_adres(monkeypatch):
    class R:
        returncode = 1
        stderr = "198.51.100.1: line 1: /dev/tcp/198.51.100.1/4: Network is unreachable\n"

    monkeypatch.setattr(netwerk.subprocess, "run", lambda *a, **k: R())
    assert netwerk.tcp_poging("c", "198.51.100.1", 4) == (False, "Network is unreachable")
    R.returncode = 124
    assert netwerk.tcp_poging("c", "198.51.100.1", 4) == (False, "time-out")
    R.returncode = 0
    assert netwerk.tcp_poging("c", "198.51.100.1", 4) == (True, "bereikt")


def test_netwerkopties_internal_en_geen_bridge_adres():
    assert "--internal" in netwerk.NETWERK_OPTIES
    assert "com.docker.network.bridge.inhibit_ipv4=true" in netwerk.NETWERK_OPTIES
    assert "--ipv6=false" in netwerk.NETWERK_OPTIES  # expliciet zonder IPv6 (review R-VEILIG-2)
    assert netwerk.gateway_adres(SUBNET) == "203.0.113.1" and netwerk.gateway_adres("") == ""
