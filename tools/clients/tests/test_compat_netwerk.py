"""Afschermingsproef van het testnetwerk (compat/netwerk.py; S-P40-72) zonder echte Docker.

De echte proef draait bij elke emulator- en desktopstart (fail-closed) en staat per run in het bewijs
(``netwerkafscherming``). Hier: de beoordeling, de echte luisteraar op de host en dat er geen adressen in de uitkomst
komen. Testadressen komen uit de documentatiereeksen van RFC 5737 (geen echte apparaten).
"""

from __future__ import annotations

import json
import socket

import pytest
from compat import netwerk
from compat import scenario as sc

HOST = [("eth0", "192.0.2.10"), ("docker0", "198.51.100.1")]  # eth0 staat hier voor bv. enx<mac>
SUBNET = "203.0.113.0/24"


class NepNetwerk(netwerk.Testnetwerk):
    def __init__(self, subnet: str = SUBNET) -> None:
        super().__init__("jlc-net-proef")
        self._subnet = subnet

    def subnet(self) -> str:
        return self._subnet


def _zet(monkeypatch, host=HOST, bereikbaar=(), server=True):
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
    return pogingen


def test_afgeschermd_als_geen_hostadres_bereikbaar_is_en_de_server_wel(monkeypatch):
    pogingen = _zet(monkeypatch)
    uit = netwerk.afscherming("jlc-jc3-emulator", NepNetwerk())
    assert uit["uitkomst"] == sc.GESLAAGD and "reden" not in uit
    assert uit["controle_luisteraar_vanaf_host"] == "bereikt" and uit["controle_testserver"] == "bereikt"
    assert uit["verbindingen_bij_luisteraar"] == 0 and uit["host_adres_in_testnetwerk"] is False
    # elk hostadres en het eerste adres van het subnet geprobeerd, op de poort van de tijdelijke luisteraar
    geprobeerd = {a for _c, a, _p in pogingen}
    assert {"192.0.2.10", "198.51.100.1", "203.0.113.1", netwerk.SERVER_ALIAS} == geprobeerd
    doelen = [d["doel"] for d in uit["pogingen"]]
    assert doelen[1:] == ["hostadres 1 (netwerkinterface)", "hostadres 2 (Docker-bridge)"]
    # geen adressen en geen interfacenamen (enx<mac>) in het bewijs
    tekst = json.dumps(uit)
    assert not any(a in tekst for a in ("192.0.2.10", "198.51.100.1", "203.0.113", "eth0", "docker0"))


@pytest.mark.parametrize(("instelling", "reden"), [
    # de negatieve test: een poort van de host is bereikbaar
    ({"bereikbaar": ("192.0.2.10",)}, "hostadres 1 (netwerkinterface): bereikt"),
    ({"bereikbaar": ("203.0.113.1",)}, "eerste adres van het subnet"),
    ({"server": False}, "testserver is vanuit de container niet bereikbaar"),  # proef kan niet slagen = ongeldig
    # zonder inhibit_ipv4 heeft de host een adres in het subnet
    ({"host": [("br-x", "203.0.113.1"), *HOST]}, "de host heeft een adres in het testnetwerk"),
    ({"host": []}, "geen hostadres gevonden"),
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


def test_luisteraar_luistert_op_alle_adressen_en_telt_de_hostcontrole_niet():
    lu = netwerk.Luisteraar()
    try:
        assert lu.sock.getsockname()[0] == "0.0.0.0"
        assert lu.controle_vanaf_host() and lu.verbindingen == 0
    finally:
        lu.sluit()


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
    assert netwerk.gateway_adres(SUBNET) == "203.0.113.1" and netwerk.gateway_adres("") == ""
