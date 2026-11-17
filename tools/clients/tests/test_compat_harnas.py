"""Regels van het compatibiliteitsharnas (compat/; P4-0, JC3) zonder echte Docker, emulator of server.

Bewaakt de veiligheidsregels van de containers (03_RISICO_AUTONOMIE en B03 §10.14): emulator alleen met
``--device /dev/kvm``, 4 GiB (geheugen = swap), ``--cap-drop ALL``, ``no-new-privileges``, SDK en APK's alleen-lezen,
nooit ``--privileged`` of de Docker-socket; de testserver op 127.0.0.1 met het corpus alleen-lezen en zonder beperkt
gelicentieerde testdata (BG-37); de desktop met ``--shm-size 1g`` (gemeten oorzaak van de eerdere blokkade). Verder:
uiautomator-dumps lezen, de regressievergelijking met stock en de geheimencontrole van het bewijs.

S-P40-72: nooit ``--network host``; emulator en desktop alleen op het eigen afgeschermde netwerk van de server (met de
afschermingsproef vóór de start, fail-closed), CDP niet gepubliceerd maar via een doorgifte, en testwachtwoorden die per
server willekeurig zijn en in geen enkel bewijs mogen staan.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import re
import socket
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from compat import android, apk, bewijs, cli, desktop, emulator, netwerk, server
from compat import scenario as sc

COMPAT = Path(__file__).resolve().parents[1] / "compat"

UI_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation="0">
<node index="0" text="" resource-id="" class="android.widget.FrameLayout" content-desc="" focused="false"
 clickable="false" bounds="[0,0][720,1600]">
<node index="1" text="Resume" resource-id="" class="android.widget.Button" content-desc="" focused="true"
 clickable="true" bounds="[169,666][248,745]" />
<node index="2" text="" resource-id="org.jellyfin.androidtv.jellyleon:id/address" class="android.widget.EditText"
 content-desc="Server" focused="false" clickable="true" bounds="[64,174][640,229]" />
</node></hierarchy>"""


class DockerOpname:
    """Vangt docker-aanroepen op in plaats van ze uit te voeren."""

    def __init__(self) -> None:
        self.aanroepen: list[tuple[str, ...]] = []

    def __call__(self, *args: str, check: bool = True, timeout: float = 600) -> subprocess.CompletedProcess[str]:
        self.aanroepen.append(args)
        return subprocess.CompletedProcess(["docker", *args], 0, stdout="cid123\n", stderr="")

    def run(self) -> tuple[str, ...]:
        return next(a for a in self.aanroepen if a and a[0] == "run")


class _DockerMetLijst(DockerOpname):
    """Als DockerOpname, maar ``docker network ls`` en ``docker ps -a`` geven de meegegeven regels (naam TAB label)."""

    def __init__(self, netwerken: str = "", containers: str = "") -> None:
        super().__init__()
        self.netwerken, self.containers = netwerken, containers

    def __call__(self, *args: str, check: bool = True, timeout: float = 600) -> subprocess.CompletedProcess[str]:
        self.aanroepen.append(args)
        uit = {("network", "ls"): self.netwerken, ("ps", "-a"): self.containers}.get(args[:2], "cid123\n")
        return subprocess.CompletedProcess(["docker", *args], 0, stdout=uit, stderr="")

    def weg(self) -> list[tuple[str, ...]]:
        """Alles wat iets verwijdert of loskoppelt."""
        return [a for a in self.aanroepen if a[:2] in {("network", "rm"), ("network", "disconnect"), ("rm", "-f")}]


NS = os.readlink("/proc/self/ns/pid")  # de eigen PID-namespace


def waarde_na(args: tuple[str, ...], vlag: str) -> list[str]:
    return [args[i + 1] for i, a in enumerate(args[:-1]) if a == vlag]


# --- uiautomator --------------------------------------------------------------------------------------------------

def test_parse_ui_leest_tekst_id_focus_en_bounds():
    knopen = emulator.parse_ui("rommel ervoor " + UI_XML)
    assert [k.label for k in knopen] == ["", "Resume", "Server"]
    resume = emulator.zoek(knopen, r"^Resume$")
    assert resume and resume.focus and resume.klikbaar and resume.midden == (208, 705)
    assert emulator.zoek(knopen, r"id/address$", klasse="EditText").omschrijving == "Server"
    assert emulator.zoek(knopen, r"id/address$", klasse="Button") is None
    assert emulator.parse_ui("") == [] and emulator.parse_ui("<hierarchy><node") == []


def test_dpad_bevat_kijkt_naar_het_midden_van_het_doel():
    buiten = emulator.Knoop("", "", "FrameLayout", "", (226, 468, 339, 565), True, True)
    label = emulator.Knoop("Resume from 5:00", "", "TextView", "", (226, 524, 339, 565), False, False)
    ander = emulator.Knoop("Play", "", "TextView", "", (339, 524, 452, 546), False, False)
    assert android.bevat(buiten, label) and not android.bevat(buiten, ander)


# --- containers ---------------------------------------------------------------------------------------------------

def _afscherming_ok(proeven: list | None = None):
    def nep(container, net):
        if proeven is not None:
            proeven.append((container, net.naam))
        return {"uitkomst": sc.GESLAAGD, "pogingen": []}
    return nep


def test_emulator_container_volgt_de_regels(monkeypatch, tmp_path):
    opname = DockerOpname()
    proeven: list = []
    monkeypatch.setattr(emulator, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)
    monkeypatch.setattr(emulator, "maak_avd", lambda soort, avd_map: f"jlc-jc3-{soort}")
    monkeypatch.setattr(emulator, "kvm_groep", lambda: 992)
    monkeypatch.setattr(emulator.nw, "eis_afscherming", _afscherming_ok(proeven))
    monkeypatch.setattr(emulator.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="1\n", stderr=""))
    e = emulator.Emulator("tv", tmp_path / "apk", avd_map=tmp_path / "avd", netwerk=netwerk.Testnetwerk("jlc-net-x"))
    assert e.start() >= 0
    args = opname.run()
    # S-P40-72: alleen het eigen testnetwerk, nooit het hostnetwerk; de afschermingsproef draait vóór het opstarten.
    assert waarde_na(args, "--network") == ["jlc-net-x"] and "host" not in args
    assert proeven == [(e.naam, "jlc-net-x")] and e.afscherming["uitkomst"] == sc.GESLAAGD
    assert not waarde_na(args, "-p")  # niets gepubliceerd
    assert "/dev/kvm" in waarde_na(args, "--device") and waarde_na(args, "--group-add") == ["992"]
    assert waarde_na(args, "--memory") == ["4g"] and waarde_na(args, "--memory-swap") == ["4g"]
    assert waarde_na(args, "--cap-drop") == ["ALL"] and "no-new-privileges" in waarde_na(args, "--security-opt")
    koppelingen = waarde_na(args, "-v")
    assert f"{emulator.SDK}:{emulator.SDK}:ro" in koppelingen and f"{tmp_path / 'apk'}:/apk:ro" in koppelingen
    assert not any("docker.sock" in k for k in koppelingen)
    assert "--privileged" not in args and emulator.RUNNER_IMAGE in args


def test_emulatorcontainer_heeft_een_unieke_naam_en_raakt_geen_andere_container(monkeypatch, tmp_path):
    """Herstel 2 van S-P40-72: geen vaste naam jlc-jc3-emulator meer. Elke Emulator heeft een eigen naam met een
    eigenaarlabel; 'docker rm -f' raakt alleen de eigen container en een emulatorcontainer van een dode eigenaar in de
    eigen PID-namespace (niet een levende, en niet een uit een andere namespace)."""
    opname = _DockerMetLijst(containers=(
        f"jlc-jc3-emulator-dood\t999999999:1:{NS}\n"
        "jlc-jc3-emulator-ander-ns\t1:5:pid:[4026532759]\n"
        f"jlc-jc3-emulator-levend\t{netwerk.eigenaar()}\n"
        "jlc-jc3-emulator\t\n"
    ))
    monkeypatch.setattr(emulator, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)
    monkeypatch.setattr(emulator, "maak_avd", lambda soort, avd_map: f"jlc-jc3-{soort}")
    monkeypatch.setattr(emulator, "kvm_groep", lambda: 992)
    proeven: list = []
    monkeypatch.setattr(emulator.nw, "eis_afscherming", _afscherming_ok(proeven))
    execs: list = []

    def nep_run(a, **k):
        execs.append(a)
        return subprocess.CompletedProcess(a, 0, stdout=b"" if "screencap" in a else "1\n", stderr="")

    monkeypatch.setattr(emulator.subprocess, "run", nep_run)
    a = emulator.Emulator("telefoon", tmp_path / "apk", avd_map=tmp_path / "avd", netwerk=netwerk.Testnetwerk("n-a"))
    b = emulator.Emulator("telefoon", tmp_path / "apk", avd_map=tmp_path / "avd", netwerk=netwerk.Testnetwerk("n-b"))
    assert a.naam != b.naam and a.naam.startswith(emulator.NAAM_VOORVOEGSEL) and a.naam != "jlc-jc3-emulator"
    assert not hasattr(emulator, "NAAM")
    a.start()
    a.schermafdruk(tmp_path / "s.png")
    a.stop()
    run = opname.run()
    assert waarde_na(run, "--name") == [a.naam]
    assert waarde_na(run, "--label") == [emulator.CONTAINER_LABEL, f"{netwerk.EIGENAAR_LABEL}={netwerk.eigenaar()}"]
    assert [x for x in opname.weg() if x[0] == "rm"] == [("rm", "-f", "jlc-jc3-emulator-dood"), ("rm", "-f", a.naam)]
    assert opname.aanroepen.index(("rm", "-f", "jlc-jc3-emulator-dood")) < opname.aanroepen.index(run)
    assert proeven == [(a.naam, "n-a")]
    docker_exec = [x for x in execs if x[:2] == ["docker", "exec"]]
    assert len(docker_exec) >= 3 and all(a.naam in x and "jlc-jc3-emulator" not in x for x in docker_exec)


def test_emulator_zonder_testnetwerk_start_niet(monkeypatch, tmp_path):
    opname = DockerOpname()
    monkeypatch.setattr(emulator, "docker", opname)
    monkeypatch.setattr(emulator, "maak_avd", lambda soort, avd_map: pytest.fail("geen AVD zonder netwerk"))
    with pytest.raises(RuntimeError, match="testnetwerk"):
        emulator.Emulator("telefoon", tmp_path / "apk", avd_map=tmp_path / "avd").start()
    assert opname.aanroepen == []


def test_emulator_stopt_als_het_netwerk_niet_afgeschermd_is(monkeypatch, tmp_path):
    """Fail-closed: bereikt de container een poort van de host, dan start de emulator niet op."""
    opname = DockerOpname()
    opgestart = []
    monkeypatch.setattr(emulator, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)
    monkeypatch.setattr(emulator, "maak_avd", lambda soort, avd_map: f"jlc-jc3-{soort}")
    monkeypatch.setattr(emulator, "kvm_groep", lambda: 992)
    monkeypatch.setattr(emulator.subprocess, "run", lambda *a, **k: opgestart.append(a))

    def lek(container, net):
        raise RuntimeError("testnetwerk niet afgeschermd: hostadres op eth0: bereikt")

    monkeypatch.setattr(emulator.nw, "eis_afscherming", lek)
    e = emulator.Emulator("telefoon", tmp_path / "apk", avd_map=tmp_path / "avd", netwerk=netwerk.Testnetwerk("n"))
    with pytest.raises(RuntimeError, match="niet afgeschermd"):
        e.start()
    assert opgestart == []  # geen adb-server en geen emulator gestart


def test_geen_hostnetwerk_meer_in_het_harnas():
    """S-P40-72: geen enkele container van het harnas op het hostnetwerk (ook niet als ``--network=host``)."""
    patroon = re.compile(r"""--network[\s"',=]+host\b|network_mode.{0,5}host""")
    for bron in sorted(COMPAT.glob("*")):
        if bron.suffix in {".py", ".mjs", ".sh"} or bron.name.endswith("Dockerfile"):
            assert not patroon.search(bron.read_text(encoding="utf-8")), bron.name
    assert "10.0.2.2:" not in (COMPAT / "android.py").read_text(encoding="utf-8")
    assert "10.0.2.2:" not in (COMPAT / "hervatproef.py").read_text(encoding="utf-8")


def test_avds_alleen_met_geinstalleerde_systeemimages_en_klein_scherm():
    for soort, a in emulator.AVDS.items():
        assert a["image"].startswith("system-images;android-3"), soort
        assert a["app"] in apk.FORK
    assert emulator.AVDS["telefoon"]["config"]["hw.lcd.width"] == "720"  # pixel_6 op 1080x2400 gaf een OOM-kill


def test_testserver_corpus_alleen_lezen_en_alleen_vrije_testdata(monkeypatch, tmp_path):
    for bron in {**server.FILMS, **server.SERIES}.values():
        assert "pioneer-one" not in bron.lower() and "movielens" not in bron.lower()  # BG-37
        (tmp_path / bron).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / bron).write_bytes(b"x")
    opname = DockerOpname()
    monkeypatch.setattr(server, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)
    monkeypatch.setattr(server, "wacht_klaar", lambda url, **k: {"Version": "12.4.0"})
    s = server.TestServer("img@sha256:" + "0" * 64, werk=tmp_path / "werk", corpus=tmp_path)
    s.start()
    args = opname.run()
    poorten = waarde_na(args, "-p")
    assert len(poorten) == 1 and poorten[0].startswith("127.0.0.1:") and poorten[0].endswith(":8096")
    assert waarde_na(args, "--network") == ["bridge"]
    # Eigen afgeschermd netwerk: --internal én geen bridge-adres op de host; de server hangt eraan als 'testserver'.
    maak = next(a for a in opname.aanroepen if a[:2] == ("network", "create"))
    assert "--internal" in maak and "com.docker.network.bridge.inhibit_ipv4=true" in waarde_na(maak, "-o")
    assert maak[-1] == s.netwerk.naam == f"{s.naam}-net"
    assert ("network", "connect", "--alias", "testserver", s.netwerk.naam, s.naam) in opname.aanroepen
    assert opname.aanroepen.index(maak) < opname.aanroepen.index(args)
    assert s.intern_url == "http://testserver:8096" and s.url.startswith("http://127.0.0.1:")
    media = [k for k in waarde_na(args, "-v") if ":/media/" in k]
    assert len(media) == len(server.FILMS) + len(server.SERIES) and all(k.endswith(":ro") for k in media)
    assert waarde_na(args, "--cap-drop") == ["ALL"] and "--privileged" not in args
    assert not any("docker.sock" in k for k in waarde_na(args, "-v"))


def test_servercontainer_met_eigenaarlabel_en_verweesde_servers_worden_opgeruimd(monkeypatch, tmp_path):
    """Herstel 2 van S-P40-72: de servercontainer krijgt een eigenaarlabel. Vóór de start gaat alleen een
    servercontainer van een dode eigenaar in de eigen PID-namespace weg (vóór de netwerken, dan is losmaken niet
    nodig); een levende eigenaar, een andere namespace en een container zonder eigenaar blijven staan."""
    corpus = tmp_path / "corpus"
    for bron in {**server.FILMS, **server.SERIES}.values():
        (corpus / bron).parent.mkdir(parents=True, exist_ok=True)
        (corpus / bron).write_bytes(b"x")
    opname = _DockerMetLijst(containers=(
        f"jlc-jc3-server-1-1-dood\t999999999:1:{NS}\n"
        "jlc-jc3-server-1-1-ander-ns\t1:5:pid:[4026532759]\n"
        f"jlc-jc3-server-1-1-levend\t{netwerk.eigenaar()}\n"
        "jlc-jc3-server-zonder-eigenaar\t\n"
    ))
    monkeypatch.setattr(server, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)
    monkeypatch.setattr(server, "wacht_klaar", lambda url, **k: {})
    s = server.TestServer("img", werk=tmp_path / "werk", corpus=corpus)
    s.start()
    run = opname.run()
    assert waarde_na(run, "--label") == [server.CONTAINER_LABEL, f"{netwerk.EIGENAAR_LABEL}={netwerk.eigenaar()}"]
    ps = next(a for a in opname.aanroepen if a[:2] == ("ps", "-a"))
    assert f"label={server.CONTAINER_LABEL}" in ps
    rm = [x for x in opname.weg() if x[0] == "rm"]
    assert rm == [("rm", "-f", "jlc-jc3-server-1-1-dood"), ("rm", "-f", s.naam)]  # de tweede: de eigen naam vóór run
    volgorde = opname.aanroepen
    assert volgorde.index(rm[0]) < volgorde.index(next(a for a in volgorde if a[:2] == ("network", "ls")))
    assert volgorde.index(rm[0]) < volgorde.index(run)


DOOD = "jlc-jc3-server-41-1-0123456789ab"
LEVEND = "jlc-jc3-server-42-1-ba9876543210"


def _datamap(werk: Path, naam: str, extra: str | None = None) -> Path:
    for sub in ("config", "cache"):
        (werk / naam / sub).mkdir(parents=True, exist_ok=True)
    (werk / naam / "config" / "db").write_bytes(b"x")
    if extra:
        (werk / naam / extra).write_bytes(b"x")
    return werk / naam


def test_datamap_van_een_verweesde_server_alleen_onder_de_eigen_werkmap(monkeypatch, tmp_path):
    """Herstel 2 van S-P40-72: de datamap van een opgeruimde verweesde server gaat alleen weg als het precies
    <werkmap>/<servernaam> is, met een naam die TestServer zelf kiest en alleen config en cache erin. Elk ander pad
    (andere naam, '..', symlink naar buiten, map met andere inhoud, map buiten de werkmap) blijft staan."""
    werk, buiten = tmp_path / "werk", tmp_path / "buiten"
    assert server.ruim_verweesde_datamap(werk, DOOD) is False  # bestaat niet
    dood = _datamap(werk, DOOD)
    assert server.ruim_verweesde_datamap(werk, DOOD) and not dood.exists() and werk.exists()
    doel = _datamap(buiten, "jlc-jc3-server-43-1-aaaaaaaaaaaa")
    (werk / "jlc-jc3-server-43-1-aaaaaaaaaaaa").symlink_to(doel, target_is_directory=True)
    vreemd = _datamap(werk, "jlc-jc3-server-44-1-bbbbbbbbbbbb", extra="iets-anders")
    oud = _datamap(werk, "jlc-jc3-server-45-1")  # zonder willekeurig achtervoegsel: geen naam van deze code
    weggehaald: list = []  # rmtree mag voor een geweigerd pad niet eens aangeroepen worden (ook niet op een symlink)
    monkeypatch.setattr(server.shutil, "rmtree", lambda pad, **k: weggehaald.append(pad))
    for naam in ("jlc-jc3-server-43-1-aaaaaaaaaaaa", "jlc-jc3-server-44-1-bbbbbbbbbbbb", "jlc-jc3-server-45-1",
                 "../buiten", f"../buiten/{DOOD}", "", ".", "jlc-jc3-desktop-0123456789ab", f"{DOOD}/config"):
        assert server.ruim_verweesde_datamap(werk, naam) is False, naam
    assert weggehaald == []
    assert doel.exists() and (doel / "config" / "db").exists() and vreemd.exists() and oud.exists()


def test_start_ruimt_de_datamap_van_een_verweesde_server_op_en_laat_de_rest_staan(monkeypatch, tmp_path):
    corpus, werk = tmp_path / "corpus", tmp_path / "werk"
    for bron in {**server.FILMS, **server.SERIES}.values():
        (corpus / bron).parent.mkdir(parents=True, exist_ok=True)
        (corpus / bron).write_bytes(b"x")
    dood, levend = _datamap(werk, DOOD), _datamap(werk, LEVEND)
    ander_ns = _datamap(werk, "jlc-jc3-server-1-1-cccccccccccc")
    opname = _DockerMetLijst(containers=(
        f"{DOOD}\t999999999:1:{NS}\n{LEVEND}\t{netwerk.eigenaar()}\n"
        "jlc-jc3-server-1-1-cccccccccccc\t1:5:pid:[4026532759]\n"
    ))
    monkeypatch.setattr(server, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)
    monkeypatch.setattr(server, "wacht_klaar", lambda url, **k: {})
    s = server.TestServer("img", werk=werk, corpus=corpus)
    s.start()
    assert ("rm", "-f", DOOD) in opname.aanroepen and not dood.exists()
    assert levend.exists() and ander_ns.exists() and s.map.exists()


def test_twee_testservers_krijgen_elk_een_eigen_naam_en_map(tmp_path):
    a, b = server.TestServer("img", werk=tmp_path), server.TestServer("img", werk=tmp_path)
    assert a.naam != b.naam and a.map != b.map and a.naam.startswith("jlc-jc3-server-")
    assert a.netwerk.naam != b.netwerk.naam  # ook een eigen netwerk per server (V-008)


def test_testwachtwoorden_per_server_willekeurig_en_alleen_letters_en_cijfers(tmp_path):
    a, b = server.TestServer("img", werk=tmp_path), server.TestServer("img", werk=tmp_path)
    alle = [a.beheer_ww, a.kijker_ww, b.beheer_ww, b.kijker_ww]
    assert len(set(alle)) == 4  # geen vaste waarde meer: per server en per account anders
    for ww in alle:
        assert len(ww) >= 20 and re.fullmatch(r"[A-Za-z0-9]+", ww)  # adb 'input text' typt alleen dit betrouwbaar
        assert ww not in {"Jc3Beheer2026", "Jc3Kijker2026"}  # de oude vaste waarden
    assert set(alle) <= set(server.run_wachtwoorden())
    assert not hasattr(server, "KIJKER_WW") and not hasattr(server, "BEHEER_WW")


def test_testserver_ruimt_container_en_netwerk_op(monkeypatch, tmp_path):
    opname = DockerOpname()
    monkeypatch.setattr(server, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)
    s = server.TestServer("img", werk=tmp_path)
    with s:
        pass
    assert opname.aanroepen[0] == ("rm", "-f", s.naam)
    assert opname.aanroepen[1] == ("network", "rm", s.netwerk.naam)


def test_netwerk_met_een_achtergebleven_container_wordt_toch_verwijderd(monkeypatch):
    aanroepen = []

    def nep(*args, check=True, timeout=600):
        aanroepen.append(args)
        if args[:2] == ("network", "rm") and len([a for a in aanroepen if a[:2] == ("network", "rm")]) == 1:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="has active endpoints")
        return subprocess.CompletedProcess(args, 0, stdout="jlc-jc3-emulator " if args[1] == "inspect" else "",
                                           stderr="")

    monkeypatch.setattr(netwerk, "docker", nep)
    netwerk.Testnetwerk("n1").verwijder()
    assert ("network", "disconnect", "-f", "n1", "jlc-jc3-emulator") in aanroepen
    assert aanroepen[-1] == ("network", "rm", "n1")


def test_eigenaarlabel_bevat_pid_starttijd_en_pid_namespace():
    pid, start, ns = netwerk.eigenaar().split(":", 2)
    assert pid == str(os.getpid()) and start.isdigit() and ns == NS and ns.startswith("pid:[")


def test_netwerk_uit_een_andere_pid_namespace_wordt_niet_opgeruimd(monkeypatch):
    """Review R-HERREV-1: een harnas in een container of sandbox heeft een eigen PID-namespace; zijn pid (hier pid 1 of
    een pid dat in de eigen namespace niet bestaat) zegt hier niets. Alleen een dode eigenaar in de eigen namespace
    wordt opgeruimd; netwerken uit een andere of onbekende namespace blijven staan (geen rm en geen disconnect)."""
    opname = _DockerMetLijst(netwerken=(
        "jlc-ander-ns-1-net\t1:119025387:pid:[4026532759]\n"
        "jlc-ander-ns-2-net\t999999999:1:pid:[4026532760]\n"
        "jlc-oude-vorm-net\t999999999:1\n"
        "jlc-onbekend-ns-net\t999999999:1:onbekend\n"
        f"jlc-dood-net\t999999999:1:{NS}\n"
    ))
    monkeypatch.setattr(netwerk, "docker", opname)
    assert netwerk.ruim_verweesde_netwerken() == ["jlc-dood-net"]
    assert {a[-1] if a[1] != "disconnect" else a[3] for a in opname.weg()} == {"jlc-dood-net"}


def test_netwerk_uit_een_andere_pid_namespace_blijft_staan_bij_maak(monkeypatch):
    opname = _DockerMetLijst(netwerken="jlc-ander-ns-net\t1:5:pid:[4026532759]\n")
    monkeypatch.setattr(netwerk, "docker", opname)
    netwerk.Testnetwerk("jlc-nieuw-net").maak()
    assert all(a[-1] == "jlc-nieuw-net" for a in opname.weg())  # alleen de eigen naam (een oude eigen run)
    maak = next(a for a in opname.aanroepen if a[:2] == ("network", "create"))
    assert f"{netwerk.EIGENAAR_LABEL}={netwerk.eigenaar()}" in maak and netwerk.eigenaar().endswith(f":{NS}")


def test_proc_onleesbaar_ruimt_niets_op(monkeypatch):
    """Review R-HERREV-2 (mutatie N4): is /proc niet leesbaar (geen starttijd voor het eigen pid), dan is niets vast te
    stellen: de eigenaar telt als levend en er gaat geen netwerk weg, ook niet van een ander."""
    monkeypatch.setattr(netwerk, "_starttijd", lambda pid: None)
    assert netwerk.eigenaar_leeft(f"123:456:{NS}")
    opname = _DockerMetLijst(netwerken=f"jlc-ander-net\t123:456:{NS}\njlc-ander2-net\t999999999:1:{NS}\n")
    monkeypatch.setattr(netwerk, "docker", opname)
    assert netwerk.ruim_verweesde_netwerken() == []
    assert opname.weg() == []


def test_eigen_pid_namespace_onleesbaar_ruimt_niets_op(monkeypatch):
    """Review R-HERREV-1, bij twijfel blijven staan: is de eigen PID-namespace niet leesbaar, dan is niet vast te
    stellen of een pid uit een label hier iets betekent; er gaat niets weg, ook geen dode eigenaar."""
    monkeypatch.setattr(netwerk, "pid_namespace", lambda: None)
    assert netwerk.eigenaar_leeft(f"999999999:1:{NS}") and netwerk.eigenaar_leeft("999999999:1:onbekend")
    opname = _DockerMetLijst(netwerken=f"jlc-dood-net\t999999999:1:{NS}\njlc-onbekend-net\t999999999:1:onbekend\n",
                             containers=f"jlc-jc3-desktop-dood\t999999999:1:{NS}\n")
    monkeypatch.setattr(netwerk, "docker", opname)
    assert netwerk.ruim_verweesde_netwerken() == [] and netwerk.ruim_verweesde_containers(desktop.CONTAINER_LABEL) == []
    assert opname.weg() == []


def test_verweesde_desktopcontainer_alleen_van_een_dode_eigenaar_in_de_eigen_namespace(monkeypatch):
    opname = _DockerMetLijst(containers=(
        f"jlc-jc3-desktop-dood\t999999999:1:{NS}\n"
        f"jlc-jc3-desktop-levend\t{netwerk.eigenaar()}\n"
        "jlc-jc3-desktop-ander-ns\t999999999:1:pid:[4026532759]\n"
        "jlc-jc3-desktop-zonder-label\t\n"
    ))
    monkeypatch.setattr(netwerk, "docker", opname)
    assert netwerk.ruim_verweesde_containers(desktop.CONTAINER_LABEL) == ["jlc-jc3-desktop-dood"]
    ps = next(a for a in opname.aanroepen if a[:2] == ("ps", "-a"))
    assert f"label={desktop.CONTAINER_LABEL}" in ps
    assert opname.weg() == [("rm", "-f", "jlc-jc3-desktop-dood")]


class _FaalOpRun(DockerOpname):
    """``docker run`` faalt (zoals bij een ontbrekende image); de rest slaagt."""

    def __call__(self, *args: str, check: bool = True, timeout: float = 600) -> subprocess.CompletedProcess[str]:
        uit = super().__call__(*args, check=check, timeout=timeout)
        if args and args[0] == "run":
            raise subprocess.CalledProcessError(125, ["docker", *args], stderr="Unable to find image")
        return uit


@pytest.mark.parametrize("fout", ["docker_run", "corpus", "wacht_klaar"])
def test_mislukte_start_van_de_testserver_ruimt_container_netwerk_en_map_op(monkeypatch, tmp_path, fout):
    """Review R-TECH-1: faalt TestServer.start (docker run, ontbrekend corpusbestand, time-out), dan ruimt start zelf
    container, testnetwerk en datamap op en geeft de fout door."""
    corpus = tmp_path / "corpus"
    if fout != "corpus":
        for bron in {**server.FILMS, **server.SERIES}.values():
            (corpus / bron).parent.mkdir(parents=True, exist_ok=True)
            (corpus / bron).write_bytes(b"x")
    opname = _FaalOpRun() if fout == "docker_run" else DockerOpname()
    monkeypatch.setattr(server, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)

    def time_out(url, **k):
        raise TimeoutError("server antwoordt niet")

    monkeypatch.setattr(server, "wacht_klaar", time_out if fout == "wacht_klaar" else (lambda url, **k: {}))
    s = server.TestServer("img", werk=tmp_path / "werk", corpus=corpus)
    with pytest.raises((subprocess.CalledProcessError, FileNotFoundError, TimeoutError)):
        s.start()
    maak = next(i for i, a in enumerate(opname.aanroepen) if a[:2] == ("network", "create"))
    na = opname.aanroepen[maak + 1:]
    assert ("network", "rm", s.netwerk.naam) in na and ("rm", "-f", s.naam) in na
    assert not s.map.exists()


def test_keyboardinterrupt_in_de_serverstart_ruimt_op_en_wordt_doorgegeven(monkeypatch, tmp_path):
    """Review R-HERREV-2 (mutatie N14): ook bij Ctrl-C (KeyboardInterrupt, geen Exception) tijdens het wachten op de
    server gaan container, testnetwerk en datamap weg, en de onderbreking wordt doorgegeven."""
    corpus = tmp_path / "corpus"
    for bron in {**server.FILMS, **server.SERIES}.values():
        (corpus / bron).parent.mkdir(parents=True, exist_ok=True)
        (corpus / bron).write_bytes(b"x")
    opname = DockerOpname()
    monkeypatch.setattr(server, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)

    def onderbroken(url, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(server, "wacht_klaar", onderbroken)
    s = server.TestServer("img", werk=tmp_path / "werk", corpus=corpus)
    with pytest.raises(KeyboardInterrupt):
        s.start()
    maak = next(i for i, a in enumerate(opname.aanroepen) if a[:2] == ("network", "create"))
    na = opname.aanroepen[maak + 1:]
    assert ("rm", "-f", s.naam) in na and ("network", "rm", s.netwerk.naam) in na
    assert not s.map.exists()


def test_servernaam_uniek_ook_met_hetzelfde_pid_en_dezelfde_teller(monkeypatch, tmp_path):
    """Vervolgpunt herreview S-P40-72: pid en teller zijn alleen binnen één PID-namespace uniek. Twee harnassen in
    verschillende namespaces met hetzelfde pid mogen toch nooit dezelfde server- of netwerknaam krijgen (anders haalt
    'docker rm -f' de server van de andere run weg)."""
    monkeypatch.setattr(server.os, "getpid", lambda: 1)
    monkeypatch.setattr(server, "_TELLER", itertools.count(1))
    a = server.TestServer("img", werk=tmp_path)
    monkeypatch.setattr(server, "_TELLER", itertools.count(1))
    b = server.TestServer("img", werk=tmp_path)
    assert a.naam.startswith("jlc-jc3-server-1-1-") and b.naam.startswith("jlc-jc3-server-1-1-")
    assert a.naam != b.naam and a.netwerk.naam != b.netwerk.naam and a.map != b.map


def test_desktopcontainer_heeft_een_unieke_naam_en_raakt_geen_andere_container(monkeypatch, tmp_path):
    """Vervolgpunt herreview S-P40-72: geen vaste naam jlc-jc3-desktop meer. Elke Desktop heeft een eigen naam met een
    eigenaarlabel; vóór de start gaat alleen een desktopcontainer van een dode eigenaar in de eigen namespace weg."""
    opname = _DockerMetLijst(containers=(
        f"jlc-jc3-desktop-dood\t999999999:1:{NS}\n"
        "jlc-jc3-desktop-ander-ns\t1:5:pid:[4026532759]\n"
        f"jlc-jc3-desktop-levend\t{netwerk.eigenaar()}\n"
    ))
    monkeypatch.setattr(desktop, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)
    proeven: list = []
    monkeypatch.setattr(desktop.nw, "eis_afscherming", _afscherming_ok(proeven))
    doorgiften: list = []
    nep_doorgifte = SimpleNamespace(poort=1, sluit=lambda: None)
    monkeypatch.setattr(desktop, "CdpDoorgifte", lambda c: doorgiften.append(c) or nep_doorgifte)
    a = desktop.Desktop(tmp_path, netwerk=netwerk.Testnetwerk("jlc-net-a"))
    b = desktop.Desktop(tmp_path, netwerk=netwerk.Testnetwerk("jlc-net-b"))
    assert a.naam != b.naam and a.naam.startswith(desktop.NAAM_VOORVOEGSEL) and a.naam != "jlc-jc3-desktop"
    assert not hasattr(desktop, "NAAM")
    monkeypatch.setattr(a, "cdp", lambda actie, **k: {"doelen": [{"type": "page"}]})
    a.start()
    a.stop()
    run = opname.run()
    assert waarde_na(run, "--name") == [a.naam]
    assert waarde_na(run, "--label") == [desktop.CONTAINER_LABEL, f"{netwerk.EIGENAAR_LABEL}={netwerk.eigenaar()}"]
    # alleen de verweesde container (vóór de run) en de eigen container (bij stop) gaan weg
    assert [x for x in opname.weg() if x[0] == "rm"] == [("rm", "-f", "jlc-jc3-desktop-dood"), ("rm", "-f", a.naam)]
    assert opname.aanroepen.index(("rm", "-f", "jlc-jc3-desktop-dood")) < opname.aanroepen.index(run)
    execs = [x for x in opname.aanroepen if x[0] == "exec"]
    assert execs and all(x[2] == a.naam for x in execs)
    assert proeven == [(a.naam, "jlc-net-a")] and doorgiften == [a.naam]


def test_mislukte_serverstart_in_desktop_main_laat_geen_netwerk_achter(monkeypatch, tmp_path):
    """Review R-TECH-1: desktop.main zet de serverstart vóór try/finally; ook dan gaat het netwerk weg."""
    opname = _FaalOpRun()
    monkeypatch.setattr(server, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)
    monkeypatch.setattr(desktop.bewijs, "slot", _geen_slot)
    monkeypatch.setattr(cli, "image_herkomst", lambda img: {"image": img})
    corpus = tmp_path / "corpus"
    for bron in {**server.FILMS, **server.SERIES}.values():
        (corpus / bron).parent.mkdir(parents=True, exist_ok=True)
        (corpus / bron).write_bytes(b"x")
    monkeypatch.setattr(desktop, "TestServer", lambda image: server.TestServer(image, werk=tmp_path / "werk",
                                                                                corpus=corpus))
    with pytest.raises(subprocess.CalledProcessError):
        desktop.main(_desktop_args(tmp_path))
    gemaakt = [a[-1] for a in opname.aanroepen if a[:2] == ("network", "create")]
    assert len(gemaakt) == 1 and ("network", "rm", gemaakt[0]) in opname.aanroepen[-4:]
    assert not (tmp_path / "uit.json").exists()


def test_testserver_weigert_een_ontbrekend_corpusbestand(tmp_path):
    with pytest.raises(FileNotFoundError):
        server.TestServer("img", werk=tmp_path / "w", corpus=tmp_path / "leeg").koppelingen()


def test_desktop_container_met_grote_shm_en_zonder_rechten(monkeypatch, tmp_path):
    opname = DockerOpname()
    proeven: list = []
    monkeypatch.setattr(desktop, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)
    monkeypatch.setattr(desktop.nw, "eis_afscherming", _afscherming_ok(proeven))
    d = desktop.Desktop(tmp_path, netwerk=netwerk.Testnetwerk("jlc-net-d"))
    monkeypatch.setattr(d, "cdp", lambda actie, **k: {"doelen": [{"type": "page"}]})
    d.start()
    try:
        args = opname.run()
        assert waarde_na(args, "--shm-size") == ["1g"]
        assert waarde_na(args, "--cap-drop") == ["ALL"] and "no-new-privileges" in waarde_na(args, "--security-opt")
        assert waarde_na(args, "-v") == [f"{tmp_path}:/out:ro"] and "--privileged" not in args
        # S-P40-72: alleen het testnetwerk; CDP alleen in de container en niet gepubliceerd, wel een doorgifte.
        assert waarde_na(args, "--network") == ["jlc-net-d"] and "host" not in args and not waarde_na(args, "-p")
        app = next(a for a in opname.aanroepen if a[:2] == ("exec", "-d"))
        assert f"--remote-debugging-port {desktop.CDP_POORT} " in app[-1]
        assert proeven == [(d.naam, "jlc-net-d")]
        assert d.doorgifte is not None and d.poort == d.doorgifte.poort != desktop.CDP_POORT
    finally:
        d.stop()


def test_desktop_app_start_pas_na_de_afschermingsproef(monkeypatch, tmp_path):
    """Review R-VEILIG-3: de container start met 'sleep infinity'; eerst de afschermingsproef, dan pas Xvfb en de app
    met 'docker exec -d' (ADR-0011 besluit 15: vóór elke desktopstart)."""
    opname = DockerOpname()
    monkeypatch.setattr(desktop, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)

    def proef(container, net):
        opname.aanroepen.append(("afschermingsproef", container, net.naam))
        return {"uitkomst": sc.GESLAAGD, "pogingen": []}

    monkeypatch.setattr(desktop.nw, "eis_afscherming", proef)
    d = desktop.Desktop(tmp_path, netwerk=netwerk.Testnetwerk("jlc-net-d"))
    monkeypatch.setattr(d, "cdp", lambda actie, **k: {"doelen": [{"type": "page"}]})
    d.start()
    try:
        run = opname.run()
        assert run[-2:] == ("sleep", "infinity") and "jellyfin-desktop" not in " ".join(run)
        app = next(a for a in opname.aanroepen if a[:2] == ("exec", "-d"))
        assert app[2:5] == (d.naam, "sh", "-c") and "/out/build/src/jellyfin-desktop" in app[-1]
        assert "Xvfb :99" in app[-1] and f"--remote-debugging-port {desktop.CDP_POORT}" in app[-1]
        volgorde = [a[0] for a in opname.aanroepen]
        assert volgorde.index("run") < volgorde.index("afschermingsproef") < opname.aanroepen.index(app)
    finally:
        d.stop()


def test_desktop_app_start_niet_als_de_afschermingsproef_faalt(monkeypatch, tmp_path):
    opname = DockerOpname()
    monkeypatch.setattr(desktop, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)

    def lek(container, net):
        raise RuntimeError("testnetwerk niet afgeschermd: hostadres 1 (netwerkinterface): bereikt")

    monkeypatch.setattr(desktop.nw, "eis_afscherming", lek)
    monkeypatch.setattr(desktop, "CdpDoorgifte", lambda *a, **k: pytest.fail("geen CDP-doorgifte zonder proef"))
    d = desktop.Desktop(tmp_path, netwerk=netwerk.Testnetwerk("n"))
    with pytest.raises(RuntimeError, match="niet afgeschermd"):
        d.start()
    assert not [a for a in opname.aanroepen if a and a[0] == "exec"]  # geen Xvfb en geen app
    assert not any("jellyfin-desktop" in " ".join(a) for a in opname.aanroepen)


def test_desktop_zonder_testnetwerk_start_niet(monkeypatch, tmp_path):
    opname = DockerOpname()
    monkeypatch.setattr(desktop, "docker", opname)
    monkeypatch.setattr(netwerk, "docker", opname)
    with pytest.raises(RuntimeError, match="testnetwerk"):
        desktop.Desktop(tmp_path).start()
    assert opname.aanroepen == []


def test_cdp_doorgifte_geeft_bytes_heen_en_terug_door(monkeypatch):
    """De doorgifte met bash /dev/tcp (hier zonder docker: hetzelfde script op de host tegen een echoserver)."""
    echo = socket.socket()
    echo.bind(("127.0.0.1", 0))
    echo.listen(1)

    def bedien():
        k, _ = echo.accept()
        with k:
            while data := k.recv(1024):
                k.sendall(data[::-1])

    threading.Thread(target=bedien, daemon=True).start()
    echt_popen = subprocess.Popen
    gezien = []

    def zonder_docker(args, **k):
        gezien.append(args[:4])
        assert args[:4] == ["docker", "exec", "-i", "jlc-jc3-desktop"]
        return echt_popen(args[4:], **k)

    monkeypatch.setattr(desktop.subprocess, "Popen", zonder_docker)
    g = desktop.CdpDoorgifte("jlc-jc3-desktop", doelpoort=echo.getsockname()[1])
    try:
        with socket.create_connection(("127.0.0.1", g.poort), timeout=10) as c:
            c.settimeout(10)
            c.sendall(b"hallo cdp")
            ontvangen = b""
            while len(ontvangen) < 9 and (deel := c.recv(64)):
                ontvangen += deel
        assert ontvangen == b"pdc ollah" and gezien
    finally:
        g.sluit()
        echo.close()


def test_stockimage_en_desktopimage_vast(monkeypatch):
    assert server.STOCK_12_4.startswith("docker.io/jellyfin/jellyfin:12.4@sha256:")
    assert len(server.STOCK_12_4.split("@sha256:")[1]) == 64
    assert desktop.LAGE_BITRATE["maxbitrate-Video-true"] == "400000"


# --- APK's --------------------------------------------------------------------------------------------------------

def test_fork_en_officiele_pakketnamen_verschillen_en_officieel_heeft_sha256():
    for app in ("android", "androidtv"):
        assert apk.FORK[app]["pakket"] == apk.OFFICIEEL[app]["pakket"] + ".jellyleon"
        assert len(apk.OFFICIEEL[app]["sha256"]) == 64 and apk.OFFICIEEL[app]["url"].startswith("https://github.com/jellyfin/")
        assert "-unsigned.apk" in apk.FORK[app]["uitvoer"] and apk.FORK[app]["versie"].endswith("-jl.1")


def test_badging_regel():
    regel = ("package: name='org.jellyfin.mobile.jellyleon' versionCode='2070301' versionName='2.7.3-jl.1' "
             "platformBuildVersionName='16'")
    mt = apk.BADGING_RE.search(regel)
    assert mt and mt.groups() == ("org.jellyfin.mobile.jellyleon", "2070301", "2.7.3-jl.1")


def test_officiele_apk_met_verkeerde_sha256_wordt_niet_gebruikt(monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / apk.OFFICIEEL["android"]["naam"]).write_bytes(b"geen echte apk")
    with pytest.raises(RuntimeError, match="sha256"):
        apk.haal_officieel("android", tmp_path / "apk", cache)
    assert not list((tmp_path / "apk").glob("*.apk*"))  # geen half bestand achtergelaten


# --- bewijs ---------------------------------------------------------------------------------------------------------

def test_vergelijking_met_stock_markeert_alleen_echte_regressies():
    jl = {"a": {"uitkomst": sc.GESLAAGD}, "b": {"uitkomst": sc.MISLUKT}, "c": {"uitkomst": sc.MISLUKT},
          "seg": {"uitkomst": sc.NIET_AANWEZIG}}
    st = {"a": {"uitkomst": sc.GESLAAGD}, "b": {"uitkomst": sc.GESLAAGD}, "c": {"uitkomst": sc.MISLUKT},
          "seg": {"uitkomst": sc.NIET_AANWEZIG}}
    rij = {v["stap"]: v for v in bewijs.vergelijk(jl, st)}
    assert [s for s, v in rij.items() if v["regressie"]] == ["b"]
    assert rij["c"]["gelijk"] and not rij["c"]["regressie"]  # ook stock faalt: upstream-gedrag, geen regressie


def test_vergelijking_telt_een_ontbrekende_of_verdwenen_stap_op_jelly_leon_als_regressie():
    """Review P4-0: brak de Jelly Leon-run af (stap ontbreekt) of levert Jelly Leon een functie niet die stock wel
    levert, dan is dat een regressie — nooit '0 regressies' door een ontbrekende meting."""
    st = {"hervatten": {"uitkomst": sc.GESLAAGD}, "seg": {"uitkomst": sc.GESLAAGD},
          "extra": {"uitkomst": sc.NIET_AANWEZIG}}
    jl = {"seg": {"uitkomst": sc.NIET_AANWEZIG}, "extra": {"uitkomst": sc.GESLAAGD}}
    rij = {v["stap"]: v for v in bewijs.vergelijk(jl, st)}
    assert rij["hervatten"]["regressie"] and rij["hervatten"]["jelly_leon"] is None
    assert rij["seg"]["regressie"]
    assert not rij["extra"]["regressie"]  # beter dan stock is geen regressie


@pytest.mark.parametrize("document", [
    {"k": "MediaBrowser Client=\"x\", Token=\"abc123\""},
    {"AccessToken": "x"},
    {"url": "/Videos/1/master.m3u8?ApiKey=0123456789abcdef0123"},
    {"lijst": ["<KIJKER_WW>"]},
    {"app_log_staart": "login jc3kijker <BEHEER_WW> klaar"},
])
def test_bewijs_met_geheim_wordt_geweigerd(document, tmp_path):
    s = server.TestServer("img", werk=tmp_path)
    tekst = json.dumps(document).replace("<KIJKER_WW>", s.kijker_ww).replace("<BEHEER_WW>", s.beheer_ww)
    with pytest.raises(ValueError):
        bewijs.schrijf(tmp_path / "b.json", json.loads(tekst), geheimen=server.run_wachtwoorden())
    assert not (tmp_path / "b.json").exists()


def test_bewijs_zonder_geheim_wordt_geschreven(tmp_path):
    bewijs.schrijf(tmp_path / "b.json", {"stap": "geen 'Use a password'", "versie": "12.4.0"}, geheimen=["geheim!"])
    assert (tmp_path / "b.json").read_text(encoding="utf-8").endswith("\n")


def test_slot_gebruikt_flock_in_de_gedeelde_map(monkeypatch, tmp_path):
    monkeypatch.setattr(bewijs, "LOCKS", tmp_path)
    with bewijs.slot("test.lock") as wacht:
        assert wacht == 0 and (tmp_path / "test.lock").exists()


def test_comprimeer_houdt_alleen_jelly_leon_schermafdrukken(monkeypatch, tmp_path):
    tmp_path = tmp_path / "schermen"
    tmp_path.mkdir()
    for naam in ("jelly-leon-tv-a.png", "stock-tv-a.png"):
        (tmp_path / naam).write_bytes(b"\x89PNG")
    monkeypatch.setattr(bewijs.subprocess, "run", lambda args, **k: (Path(args[-1]).write_bytes(b"jpg"),
                                                                    SimpleNamespace(returncode=0))[1])
    assert bewijs.comprimeer_schermafdrukken(tmp_path) == ["jelly-leon-tv-a.jpg"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["jelly-leon-tv-a.jpg"]


# --- opdrachtregel --------------------------------------------------------------------------------------------------

def test_android_bewijs_met_een_wachtwoord_van_de_run_wordt_niet_geschreven(monkeypatch, tmp_path):
    """De opdrachtregel geeft de wachtwoorden van déze run aan de echte bewijscontrole mee (geen vaste lijst)."""
    s = server.TestServer("img", werk=tmp_path)

    def lekkende_run(label, image, soort, apks, uitmap, gib, migratie_van=None, bediend="fork"):
        return {"oordeel": {"validatie": "Sim-geslaagd"}, "geheugen": {"oom_kill": 0},
                "stappen": {"inloggen": {"uitkomst": "geslaagd", "reden": f"getypt: {s.kijker_ww}"}}}

    monkeypatch.setattr(cli.apk, "bereid_voor", lambda *a, **k: {})
    monkeypatch.setattr(cli, "een_android_run", lekkende_run)
    monkeypatch.setattr(cli, "image_herkomst", lambda img: {"image": img})
    monkeypatch.setattr(cli, "corpus_herkomst", lambda: [])
    monkeypatch.setattr(cli.bewijs, "comprimeer_schermafdrukken", lambda m: [])
    a = SimpleNamespace(soorten="telefoon", vergelijk_soorten="", uit=tmp_path / "b.json", image="jl",
                        stock_image="stock", migratie_van=None, bediend="fork", aanvullen=False)
    with pytest.raises(ValueError, match="wachtwoord"):
        cli.android_cmd(a)
    assert not (tmp_path / "b.json").exists()


@contextlib.contextmanager
def _geen_slot(naam, log=None):
    yield 0.0


class _StilleServer(server.TestServer):
    """Echte TestServer (met echte, per server willekeurige wachtwoorden) zonder Docker."""

    def start(self):
        self.info = {"Version": "12.4.0"}
        return self

    def inrichten(self, voorkeuren=False):
        return {}

    def image_id(self):
        return "sha256:x"

    def verwijder(self):
        pass


def _desktop_args(tmp_path):
    build = tmp_path / "build"
    (build / "build/src").mkdir(parents=True, exist_ok=True)
    (build / "build/src/jellyfin-desktop").write_bytes(b"")
    return SimpleNamespace(uit=tmp_path / "uit.json", build=build, image="jl", stock_image="stock", met_stock=True)


WACHTWOORD = ["kijker_ww", "beheer_ww"]


@pytest.mark.parametrize("veld", WACHTWOORD)
def test_desktop_bewijs_met_een_wachtwoord_van_de_run_wordt_niet_geschreven(monkeypatch, tmp_path, veld):
    """Review R-VEILIG-4/R-TECH-2: desktop.main geeft de wachtwoorden van déze run aan de bewijscontrole mee."""
    monkeypatch.setattr(desktop, "TestServer", _StilleServer)
    monkeypatch.setattr(desktop.bewijs, "slot", _geen_slot)
    monkeypatch.setattr(cli, "image_herkomst", lambda img: {"image": img})

    def lekkende_run(srv, build, uitmap, label):
        return {"stappen": {"inloggen": {"uitkomst": "geslaagd"}}, "app_log_staart": f"login {getattr(srv, veld)}",
                "oordeel": {"validatie": "Sim-geslaagd", "mislukte_stappen": []}}

    monkeypatch.setattr(desktop, "run", lekkende_run)
    with pytest.raises(ValueError, match="wachtwoord"):
        desktop.main(_desktop_args(tmp_path))
    assert not (tmp_path / "uit.json").exists()


@pytest.mark.parametrize("veld", WACHTWOORD)
def test_hervatproef_bewijs_met_een_wachtwoord_van_de_run_wordt_niet_geschreven(monkeypatch, tmp_path, veld):
    from compat import hervatproef

    monkeypatch.setattr(cli, "TestServer", _StilleServer)
    monkeypatch.setattr(cli.bewijs, "slot", _geen_slot)
    monkeypatch.setattr(cli.apk, "bereid_voor", lambda *a, **k: {})
    monkeypatch.setattr(cli, "image_herkomst", lambda img: {"image": img})
    monkeypatch.setattr(hervatproef, "herhaal", lambda srv, soort, apks, bediend, n: {
        "geslaagd": n, "n": n, "pogingen": [{"uitkomst": "geslaagd", "reden": f"getypt: {getattr(srv, veld)}"}]})
    a = SimpleNamespace(image="jl", stock_image="stock", soort="tv", bediend="fork", n=1, uit=tmp_path / "h.json")
    with pytest.raises(ValueError, match="wachtwoord"):
        cli.hervatproef_cmd(a)
    assert not (tmp_path / "h.json").exists()


@pytest.mark.parametrize("veld", WACHTWOORD)
def test_swiftfin_bewijs_met_een_wachtwoord_van_de_run_wordt_niet_geschreven(monkeypatch, tmp_path, veld):
    from compat import swiftfin

    monkeypatch.setattr(cli, "TestServer", _StilleServer)
    monkeypatch.setattr(cli, "image_herkomst", lambda img: {"image": img})
    monkeypatch.setattr(swiftfin, "run", lambda srv: {
        "stappen": {"inloggen": {"uitkomst": "geslaagd", "verzoek": f"Pw={getattr(srv, veld)}"}},
        "oordeel": {"validatie": "Sim-geslaagd"}})
    a = SimpleNamespace(image="jl", stock_image="stock", uit=tmp_path / "s.json")
    with pytest.raises(ValueError, match="wachtwoord"):
        cli.swiftfin_cmd(a)
    assert not (tmp_path / "s.json").exists()


class _NepDesktop:
    """Neemt elke CDP-aanroep op; inloggen lukt, daarna geen bestuurbare sessie (de run stopt na 'inloggen')."""

    def __init__(self) -> None:
        self.aanroepen: list[tuple[str, dict]] = []

    def start(self) -> None:
        pass

    def cdp(self, actie, timeout=150, **velden):
        self.aanroepen.append((actie, velden))
        return {"ok": True, "thuis": True}

    def schermafdruk(self, pad) -> bool:
        return False


def test_desktop_app_krijgt_het_interne_adres_en_het_wachtwoord_van_de_run(monkeypatch, tmp_path):
    """Review R-TECH-2 (mutatie M9): de app in de container krijgt http://testserver:8096, nooit het hostadres van het
    harnas (server.url op 127.0.0.1)."""
    s = server.TestServer("img", werk=tmp_path)
    s.poort, s.jf = 41234, SimpleNamespace()
    monkeypatch.setattr(desktop, "Volger", lambda jf, client: SimpleNamespace(bestuurbaar=lambda t: None))
    d = _NepDesktop()
    res = {"stappen": {}}
    desktop._stappen(d, res, s, tmp_path, "jelly-leon")
    acties = dict(d.aanroepen)
    assert acties["verbind"]["server"] == s.intern_url == "http://testserver:8096"
    assert acties["inloggen"]["server"] == s.intern_url and acties["inloggen"]["wachtwoord"] == s.kijker_ww
    assert not any("127.0.0.1" in json.dumps(v) for _a, v in d.aanroepen)


def test_android_app_krijgt_het_interne_adres_en_het_wachtwoord_van_de_run(monkeypatch, tmp_path):
    """Review R-TECH-2 (mutatie M9) voor de telefoon-app: inloggen met http://testserver:8096 en het kijkerwachtwoord
    van de run."""
    s = server.TestServer("img", werk=tmp_path)
    s.poort, s.jf, s.items = 41234, SimpleNamespace(), SimpleNamespace()
    logins = []

    class NepEmu(_NepEmulator):
        soort = "telefoon"

        def pakketten(self, voorvoegsel):
            return [apk.FORK["android"]["pakket"], apk.OFFICIEEL["android"]["pakket"]]

        def pakketversie(self, pakket):
            return "2.7.3"

        def schermafdruk(self, pad):
            pass

    monkeypatch.setattr(android, "Emulator", lambda *a, **k: NepEmu(*a, **k))
    monkeypatch.setattr(android, "Volger", lambda jf, client: SimpleNamespace(bestuurbaar=lambda *a: None))
    monkeypatch.setattr(android, "inloggen_telefoon", lambda emu, pakket, url, ww: (logins.append((url, ww)),
                                                                                    {"uitkomst": sc.MISLUKT})[1])
    fork = {"bestand": "f.apk", "sha256": "1" * 64, "pakket": apk.FORK["android"]["pakket"],
            "versionName": "2.7.3-jl.1", "certificaat": "CN=test", "pad": str(tmp_path / "f.apk")}
    off = {"bestand": "o.apk", "sha256": "2" * 64, "pakket": apk.OFFICIEEL["android"]["pakket"],
           "versionName": "2.7.3", "pad": str(tmp_path / "o.apk")}
    android.run(s, "telefoon", {"android": {"fork": fork, "officieel": off}}, tmp_path, "jelly-leon")
    assert logins == [("http://testserver:8096", s.kijker_ww)]


def test_cli_zonder_kvm_is_omgevingsfout(monkeypatch, capsys):
    monkeypatch.setattr(cli.Path, "exists", lambda self: str(self) != "/dev/kvm")
    assert cli.main(["android", "--image", "x"]) == 2
    assert "kvm" in capsys.readouterr().err.lower()


def test_cli_desktop_zonder_build_is_omgevingsfout(tmp_path):
    assert cli.main(["desktop", "--image", "x", "--build", str(tmp_path), "--uit", str(tmp_path / "d.json")]) == 2


def test_aanvullen_vervangt_zichtbaar_en_houdt_de_rest():
    oud = {"begin": "t0", "eind": "t1", "resultaten": {"jelly-leon": {
        "tablet": {"oordeel": {"validatie": "Sim-mislukt", "mislukte_stappen": ["bladeren"]}, "fout": "x"},
        "tv": {"oordeel": {"validatie": "Sim-geslaagd"}}}}}
    nieuw = {"begin": "t2", "resultaten": {"jelly-leon": {"tablet": {"oordeel": {"validatie": "Sim-geslaagd"}}}}}
    uit = cli.aanvullen(oud, nieuw)
    assert uit["resultaten"]["jelly-leon"]["tablet"]["oordeel"]["validatie"] == "Sim-geslaagd"
    assert uit["resultaten"]["jelly-leon"]["tv"]["oordeel"]["validatie"] == "Sim-geslaagd"
    assert uit["vervangen"] == [{"server": "jelly-leon", "emulator": "tablet", "sessie": "t0",
                                 "oordeel": {"validatie": "Sim-mislukt", "mislukte_stappen": ["bladeren"]},
                                 "fout": "x", "mislukte_stappen": ["bladeren"], "stappen": None, "geheugen": None}]
    assert uit["sessies"][-1]["aangevuld"] == ["jelly-leon/tablet"]


def test_aanvullen_bewaart_de_metingen_en_de_juiste_sessie_van_een_vervangen_run():
    """Review P4-0: de gemelde posities van een vervangen (mislukte) hervatrun moeten in het bewijs blijven, en bij een
    tweede aanvulling hoort het vervangen resultaat bij de sessie die het schreef (niet bij de eerste sessie)."""
    hervat = {"uitkomst": "mislukt", "meldingen": [[0.0, 300.0, "s"], [1.0, 1.0, "s"], [2.0, 2.0, "s"]]}
    oud = {"begin": "t0", "eind": "t1", "resultaten": {"jelly-leon": {"tv": {
        "oordeel": {"validatie": "Sim-mislukt", "mislukte_stappen": ["hervatten"]}, "stappen": {"hervatten": hervat},
        "geheugen": {"oom_kill": 0}, "geheugen_afwijking": "5 GiB"}}}}
    eerste = cli.aanvullen(oud, {"begin": "t2", "resultaten": {"jelly-leon": {"tv": {
        "oordeel": {"validatie": "Sim-mislukt"}, "stappen": {"hervatten": {"uitkomst": "mislukt"}}}}}})
    v = eerste["vervangen"][0]
    assert v["sessie"] == "t0" and v["stappen"]["hervatten"]["meldingen"][1] == [1.0, 1.0, "s"]
    assert v["geheugen"] == {"oom_kill": 0} and v["geheugen_afwijking"] == "5 GiB"
    tweede = cli.aanvullen(eerste, {"begin": "t3", "resultaten": {"jelly-leon": {"tv": {
        "oordeel": {"validatie": "Sim-geslaagd"}}}}})
    assert [x["sessie"] for x in tweede["vervangen"]] == ["t0", "t2"]
    assert cli.sessie_van(tweede, "jelly-leon", "tv") == "t3"
    assert cli.sessie_van(tweede, "stock", "tv") == "t0"
    assert cli.vervangen_mislukt(tweede) == ["jelly-leon/tv"]  # beide vervangen runs waren Sim-mislukt
    assert cli.vervangen_mislukt({"vervangen": [{"server": "a", "emulator": "b",
                                                 "oordeel": {"validatie": "Sim-geslaagd"}}]}) == []
    assert cli.vervangen_mislukt({}) == []


# --- hervatproef (review P4-0) ------------------------------------------------------------------------------------

class _NepEmulator:
    afscherming: dict = {"uitkomst": "geslaagd"}

    def __init__(self, *a, **k) -> None:
        self.gestopt = False
        self.netwerk = k.get("netwerk")

    def start(self) -> float:
        return 1.0

    def installeer(self, pad) -> str:
        return "Success"

    def wacht_op(self, *a, **k):
        return emulator.Knoop("Resume from 5:00", "", "TextView", "", (0, 0, 10, 10), True, True)

    def geheugen(self) -> dict:
        return {"oom_kill": 0}

    def stop(self) -> None:
        self.gestopt = True


class _NepVolger:
    def __init__(self, reeksen) -> None:
        self.reeksen = list(reeksen)

    def id(self) -> str:
        return "sessie"

    def volg(self, item_id, *a, **k):
        reeks = self.reeksen.pop(0)
        if isinstance(reeks, Exception):
            raise reeks
        return [sc.Monster(t=t, sessie="s", item_id=item_id, positie_s=p, gepauzeerd=False, methode="DirectPlay",
                           ondertitel=None, audio=None, transcode=None, client="c", versie="v") for t, p in reeks]


def _nep_server():
    jf = SimpleNamespace(zet_userdata=lambda *a, **k: None, toon=lambda *a, **k: None)
    return SimpleNamespace(jf=jf, items=SimpleNamespace(hervat={"Id": "tos", "Name": "tos"}), kijker_id="k",
                           HERVAT_S=300.0, poort=1, netwerk=netwerk.Testnetwerk("jlc-net-h"),
                           intern_url="http://testserver:8096", kijker_ww="Abc123willekeurig")


def _apks():
    return {"androidtv": {"fork": {"pad": "/x/fork.apk", "pakket": "f"}, "officieel": {"pad": "/x/off.apk",
                                                                                     "pakket": "o"}}}


@pytest.mark.parametrize(("login", "reeksen", "geslaagd", "uitkomsten"), [
    # goed, begint bij 0, appfout halverwege (telt als mislukt, de proef gaat door), weer goed
    ("geslaagd", [[(0, 300.0), (1, 301.0), (3, 303.0)], [(1, 1.0), (2, 2.0), (4, 4.0)], RuntimeError("sessie weg"),
                  [(0, 300.0), (2, 302.0), (3, 303.0)]], 2, ["geslaagd", "mislukt", "mislukt", "geslaagd"]),
    ("mislukt", [], 0, []),  # niet ingelogd: geen poging, en 0 van de gevraagde 4 — nooit geslaagd
])
def test_hervatproef_telt_elke_gevraagde_poging(monkeypatch, login, reeksen, geslaagd, uitkomsten):
    from compat import hervatproef

    emulators, logins = [], []

    def nep_emulator(*a, **k):
        emulators.append(_NepEmulator(*a, **k))
        return emulators[-1]

    monkeypatch.setattr(hervatproef, "Emulator", nep_emulator)
    monkeypatch.setattr(hervatproef, "Volger", lambda jf, client: _NepVolger(reeksen))
    monkeypatch.setattr(hervatproef, "inloggen_tv", lambda *a, **k: (logins.append(a), {"uitkomst": login})[1])
    monkeypatch.setattr(hervatproef, "dpad_kies", lambda *a, **k: True)
    monkeypatch.setattr(hervatproef, "stop", lambda *a, **k: True)
    monkeypatch.setattr(hervatproef.time, "sleep", lambda s: None)
    srv = _nep_server()
    uit = hervatproef.herhaal(srv, "tv", _apks(), "officieel", 4)
    assert (uit["geslaagd"], uit["n"], uit["gevraagd"]) == (geslaagd, 4, 4)
    # S-P40-72: de emulator op het testnetwerk van de server, de app naar de testserver met het wachtwoord van de run.
    assert emulators[0].netwerk is srv.netwerk
    assert logins[0][2:] == ("http://testserver:8096", "Abc123willekeurig")
    assert uit["netwerkafscherming"] == {"uitkomst": "geslaagd"}
    assert [p["uitkomst"] for p in uit["pogingen"]] == uitkomsten
    assert uit["pakket"] == "o" and uit["inloggen"] == login
    if reeksen:
        assert "RuntimeError: sessie weg" in uit["pogingen"][2]["reden"]


# --- android.run en de geheugenregel (review P4-0) ----------------------------------------------------------------

class _KapotteEmulator(_NepEmulator):
    """Emulator die niet opstart; ``geheugen`` levert wat de test opgeeft."""

    meting: dict = {"oom_kill": 0}

    def __init__(self, soort="tv", *a, **k) -> None:
        super().__init__()
        self.soort = soort

    def start(self) -> float:
        raise RuntimeError("emulator startte niet")

    def geheugen(self) -> dict:
        return dict(self.meting)


def _android_apks():
    fork = {"bestand": "f.apk", "sha256": "1" * 64, "pakket": "org.jellyfin.androidtv.jellyleon",
            "versionName": "0.19.10-jl.1", "certificaat": "CN=test", "pad": "/x/f.apk"}
    off = {"bestand": "o.apk", "sha256": "2" * 64, "pakket": "org.jellyfin.androidtv", "versionName": "0.19.10",
           "pad": "/x/o.apk"}
    return {"androidtv": {"fork": fork, "officieel": off}}


@pytest.mark.parametrize(("meting", "geheugenstap"), [
    ({"oom_kill": 0}, None),
    ({"oom_kill": 1}, "OOM-kill"),
    ({"fout": "memory.events ontbreekt"}, "niet meetbaar"),  # fail-closed: geen meting = geen bewijs
])
def test_android_run_die_afbreekt_is_nooit_geslaagd(monkeypatch, tmp_path, meting, geheugenstap):
    monkeypatch.setattr(_KapotteEmulator, "meting", meting)
    monkeypatch.setattr(android, "Emulator", _KapotteEmulator)
    monkeypatch.setattr(_KapotteEmulator, "afscherming", {})
    srv = SimpleNamespace(jf=SimpleNamespace(), items=SimpleNamespace(), netwerk=netwerk.Testnetwerk("n"))
    res = android.run(srv, "tv", _android_apks(), tmp_path, "jelly-leon")
    assert res["fout"] == "RuntimeError: emulator startte niet"
    assert res["netwerkafscherming"]["uitkomst"] == sc.MISLUKT  # niet gemeten = niet aangetoond
    assert res["oordeel"]["validatie"] == "Sim-mislukt"
    assert set(android.VEREIST) <= set(res["oordeel"]["mislukte_stappen"])  # elke ontbrekende stap telt als mislukt
    if geheugenstap:
        assert geheugenstap in res["stappen"]["geheugen"]["reden"] and "geheugen" in res["oordeel"]["mislukte_stappen"]
    else:
        assert "geheugen" not in res["stappen"]


def test_android_cmd_herhaalt_alleen_na_een_oom_kill_met_5_gib_en_bewaart_beide(monkeypatch, tmp_path):
    """B03 §10.14: eerst binnen 4 GiB; alleen na een OOM-kill één herhaling met 5 GiB, als afwijking zichtbaar; de
    runs draaien via een_android_run (stack.lock + gradle.lock)."""
    aanroepen = []

    def nep_run(label, image, soort, apks, uitmap, gib, migratie_van=None, bediend="fork"):
        aanroepen.append((label, soort, gib))
        oom = 1 if (soort == "tablet" and gib == 4) else 0
        ok = soort != "tablet"
        return {"oordeel": {"validatie": "Sim-geslaagd" if ok else "Sim-mislukt", "mislukte_stappen": [] if ok
                            else ["bladeren"]}, "geheugen": {"oom_kill": oom},
                "stappen": {"hervatten": {"uitkomst": "geslaagd" if ok else "mislukt"}}}

    geschreven = {}
    monkeypatch.setattr(cli.apk, "bereid_voor", lambda *a, **k: {})
    monkeypatch.setattr(cli, "een_android_run", nep_run)
    monkeypatch.setattr(cli, "image_herkomst", lambda img: {"image": img})
    monkeypatch.setattr(cli, "corpus_herkomst", lambda: [])
    monkeypatch.setattr(cli.bewijs, "comprimeer_schermafdrukken", lambda m: [])
    monkeypatch.setattr(cli.bewijs, "schrijf", lambda pad, doc, geheimen=None: geschreven.update(doc))
    a = SimpleNamespace(soorten="telefoon,tablet", vergelijk_soorten="telefoon", uit=tmp_path / "b.json",
                        image="jl", stock_image="stock", migratie_van=None, bediend="fork", aanvullen=False)
    assert cli.android_cmd(a) == 0
    assert aanroepen == [("jelly-leon", "telefoon", 4), ("jelly-leon", "tablet", 4), ("jelly-leon", "tablet", 5),
                         ("stock", "telefoon", 4)]
    tablet = geschreven["resultaten"]["jelly-leon"]["tablet"]
    assert "afwijking" in tablet["geheugen_afwijking"] and tablet["eerdere_poging_4gib"]["geheugen"]["oom_kill"] == 1
    assert "geheugen_afwijking" not in geschreven["resultaten"]["jelly-leon"]["telefoon"]
    assert geschreven["validatie"] == "Sim-mislukt"  # één client mislukt = geheel mislukt
    assert geschreven["samenvatting"] == {"jelly-leon/telefoon": "Sim-geslaagd", "jelly-leon/tablet": "Sim-mislukt",
                                          "stock/telefoon": "Sim-geslaagd"}
    assert geschreven["regressies"] == [] and geschreven["vervangen_mislukt"] == []


def test_emulator_alleen_binnen_gradle_lock(monkeypatch, tmp_path):
    """ADR-0011 besluit 15 (herstel 2 van S-P40-72): de AVD-map (<werkmap>/avd) en de AVD-naam jlc-jc3-<soort> zijn
    gedeeld; dat is veilig omdat een emulator alleen binnen gradle.lock draait (machinebreed één tegelijk). Een Emulator
    wordt alleen gemaakt in android.run en hervatproef.herhaal, en die worden alleen vanuit cli.py binnen het slot
    aangeroepen (een_android_run: zie de test hieronder; hervatproef_cmd: hier)."""
    makers = {b.name for b in COMPAT.glob("*.py") if "Emulator(" in b.read_text(encoding="utf-8")}
    assert makers == {"android.py", "hervatproef.py"}
    for bron in COMPAT.glob("*.py"):
        tekst = bron.read_text(encoding="utf-8")
        for aanroep in ("android.run(", "hervatproef.herhaal("):
            assert aanroep not in tekst or bron.name == "cli.py", (bron.name, aanroep)
    actief: list[str] = []

    @contextlib.contextmanager
    def nep_slot(naam, log=None):
        actief.append(naam)
        try:
            yield 0.0
        finally:
            actief.remove(naam)

    class NepServer:
        def __init__(self, image):
            pass

        def start(self):
            return self

        def inrichten(self):
            return {}

        def verwijder(self):
            pass

    from compat import hervatproef
    gezien: list = []
    monkeypatch.setattr(cli.bewijs, "slot", nep_slot)
    monkeypatch.setattr(cli, "TestServer", NepServer)
    monkeypatch.setattr(cli.apk, "bereid_voor", lambda *a, **k: {})
    monkeypatch.setattr(cli, "image_herkomst", lambda img: {"image": img})
    monkeypatch.setattr(cli.bewijs, "schrijf", lambda *a, **k: None)
    monkeypatch.setattr(hervatproef, "herhaal", lambda *a, **k: gezien.append(list(actief)) or {"geslaagd": 1, "n": 1})
    a = SimpleNamespace(image="i", stock_image="s", soort="tv", bediend="fork", n=1, uit=tmp_path / "h.json")
    assert cli.hervatproef_cmd(a) == 0
    assert gezien == [["stack.lock", "gradle.lock"]] * 2


def test_een_android_run_neemt_stack_en_gradle_lock(monkeypatch, tmp_path):
    sloten = []

    class NepSlot:
        def __init__(self, naam, log=None):
            self.naam = naam

        def __enter__(self):
            sloten.append(self.naam)
            return 0.0

        def __exit__(self, *a):
            return False

    class NepServer:
        def __init__(self, image):
            self.info = {"Version": "12.4.0"}

        def start(self):
            assert sloten == ["stack.lock", "gradle.lock"], "server pas starten binnen beide sloten"
            return self

        def inrichten(self):
            return {}

        def image_id(self):
            return "sha256:x"

        def verwijder(self):
            pass

        def logs(self, n):
            return ""

    monkeypatch.setattr(cli.bewijs, "slot", NepSlot)
    monkeypatch.setattr(cli, "TestServer", NepServer)
    monkeypatch.setattr(cli.android, "run", lambda *a, **k: {"oordeel": {"validatie": "Sim-geslaagd"}})
    r = cli.een_android_run("jelly-leon", "img", "telefoon", {}, tmp_path, 4)
    assert sloten == ["stack.lock", "gradle.lock"] and r["server"]["versie"] == "12.4.0"
