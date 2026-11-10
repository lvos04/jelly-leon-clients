"""Regels van het compatibiliteitsharnas (compat/; P4-0, JC3) zonder echte Docker, emulator of server.

Bewaakt de veiligheidsregels van de containers (03_RISICO_AUTONOMIE en B03 §10.14): emulator alleen met
``--device /dev/kvm``, 4 GiB (geheugen = swap), ``--cap-drop ALL``, ``no-new-privileges``, SDK en APK's alleen-lezen,
nooit ``--privileged`` of de Docker-socket; de testserver op 127.0.0.1 met het corpus alleen-lezen en zonder beperkt
gelicentieerde testdata (BG-37); de desktop met ``--shm-size 1g`` (gemeten oorzaak van de eerdere blokkade). Verder:
uiautomator-dumps lezen, de regressievergelijking met stock en de geheimencontrole van het bewijs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from compat import android, apk, bewijs, cli, desktop, emulator, server
from compat import scenario as sc

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

def test_emulator_container_volgt_de_regels(monkeypatch, tmp_path):
    opname = DockerOpname()
    monkeypatch.setattr(emulator, "docker", opname)
    monkeypatch.setattr(emulator, "maak_avd", lambda soort, avd_map: f"jlc-jc3-{soort}")
    monkeypatch.setattr(emulator, "kvm_groep", lambda: 992)
    monkeypatch.setattr(emulator.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="1\n", stderr=""))
    e = emulator.Emulator("tv", tmp_path / "apk", avd_map=tmp_path / "avd")
    assert e.start() >= 0
    args = opname.run()
    assert "/dev/kvm" in waarde_na(args, "--device") and waarde_na(args, "--group-add") == ["992"]
    assert waarde_na(args, "--memory") == ["4g"] and waarde_na(args, "--memory-swap") == ["4g"]
    assert waarde_na(args, "--cap-drop") == ["ALL"] and "no-new-privileges" in waarde_na(args, "--security-opt")
    koppelingen = waarde_na(args, "-v")
    assert f"{emulator.SDK}:{emulator.SDK}:ro" in koppelingen and f"{tmp_path / 'apk'}:/apk:ro" in koppelingen
    assert not any("docker.sock" in k for k in koppelingen)
    assert "--privileged" not in args and emulator.RUNNER_IMAGE in args


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
    monkeypatch.setattr(server, "wacht_klaar", lambda url, **k: {"Version": "12.4.0"})
    s = server.TestServer("img@sha256:" + "0" * 64, werk=tmp_path / "werk", corpus=tmp_path)
    s.start()
    args = opname.run()
    poorten = waarde_na(args, "-p")
    assert len(poorten) == 1 and poorten[0].startswith("127.0.0.1:") and poorten[0].endswith(":8096")
    media = [k for k in waarde_na(args, "-v") if ":/media/" in k]
    assert len(media) == len(server.FILMS) + len(server.SERIES) and all(k.endswith(":ro") for k in media)
    assert waarde_na(args, "--cap-drop") == ["ALL"] and "--privileged" not in args
    assert not any("docker.sock" in k for k in waarde_na(args, "-v"))


def test_twee_testservers_krijgen_elk_een_eigen_naam_en_map(tmp_path):
    a, b = server.TestServer("img", werk=tmp_path), server.TestServer("img", werk=tmp_path)
    assert a.naam != b.naam and a.map != b.map and a.naam.startswith("jlc-jc3-server-")


def test_testserver_weigert_een_ontbrekend_corpusbestand(tmp_path):
    with pytest.raises(FileNotFoundError):
        server.TestServer("img", werk=tmp_path / "w", corpus=tmp_path / "leeg").koppelingen()


def test_desktop_container_met_grote_shm_en_zonder_rechten(monkeypatch, tmp_path):
    opname = DockerOpname()
    monkeypatch.setattr(desktop, "docker", opname)
    d = desktop.Desktop(tmp_path)
    monkeypatch.setattr(d, "cdp", lambda actie, **k: {"doelen": [{"type": "page"}]})
    d.start()
    args = opname.run()
    assert waarde_na(args, "--shm-size") == ["1g"]
    assert waarde_na(args, "--cap-drop") == ["ALL"] and "no-new-privileges" in waarde_na(args, "--security-opt")
    assert waarde_na(args, "-v") == [f"{tmp_path}:/out:ro"] and "--privileged" not in args


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


@pytest.mark.parametrize("document", [
    {"k": "MediaBrowser Client=\"x\", Token=\"abc123\""},
    {"AccessToken": "x"},
    {"url": "/Videos/1/master.m3u8?ApiKey=0123456789abcdef0123"},
    {"lijst": ["Jc3Kijker2026"]},
])
def test_bewijs_met_geheim_wordt_geweigerd(document, tmp_path):
    with pytest.raises(ValueError):
        bewijs.schrijf(tmp_path / "b.json", document, geheimen=[server.KIJKER_WW])
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
