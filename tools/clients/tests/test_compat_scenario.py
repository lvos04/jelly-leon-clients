"""Beoordelingsregels van het compatibiliteitsharnas (compat/scenario.py; P4-0, JC3).

Puur en zonder Docker of emulator. Bewaakt vooral de eerlijkheid: een client die niets meldt, bij 0 begint, op
pauze staat of de verkeerde afspeelmethode gebruikt, is nooit geslaagd; een ontbrekende functie (geen segmenten) is
``niet_aanwezig`` en nooit een verkapt "geslaagd"; een ontbrekende vereiste stap telt als mislukt.
"""

from __future__ import annotations

import pytest
from compat import scenario as sc


def m(t: float, positie: float, *, item: str = "i", gepauzeerd: bool = False, methode: str = "DirectPlay",
      ondertitel: int | None = None) -> sc.Monster:
    return sc.Monster(t=t, sessie="s", item_id=item, positie_s=positie, gepauzeerd=gepauzeerd, methode=methode,
                      ondertitel=ondertitel, audio=None, transcode=None, client="c", versie="v")


def test_monster_uit_sessie_leest_positie_methode_en_transcodeinfo():
    sessie = {"Id": "abc", "Client": "Jellyfin Android TV", "ApplicationVersion": "0.19.10-jl.1",
              "NowPlayingItem": {"Id": "it"},
              "PlayState": {"PositionTicks": 3_000_000_000, "IsPaused": False, "PlayMethod": "Transcode",
                            "SubtitleStreamIndex": 1, "AudioStreamIndex": 3},
              "TranscodingInfo": {"VideoCodec": "h264", "AudioCodec": "mp3", "IsVideoDirect": False, "Bitrate": 1,
                                  "TranscodeReasons": ["ContainerNotSupported"]}}
    x = sc.monster(sessie, 1.234)
    assert (x.item_id, x.positie_s, x.methode, x.ondertitel, x.t) == ("it", 300.0, "Transcode", 1, 1.23)
    assert x.transcode["TranscodeReasons"] == ["ContainerNotSupported"]
    assert "Bitrate" not in x.transcode  # alleen de vaste velden
    leeg = sc.monster({"Id": "x"}, 0)
    assert leeg.item_id is None and leeg.positie_s == 0 and leeg.transcode is None


def test_afspelen_geslaagd_alleen_als_de_positie_echt_oploopt():
    rij = [m(0, 0.0), m(1, 1.0), m(2, 2.0), m(3, 3.0)]
    assert sc.beoordeel_afspelen(rij, "i", verwachte_methode="DirectPlay")["uitkomst"] == sc.GESLAAGD
    assert sc.beoordeel_afspelen(rij[:2], "i")["uitkomst"] == sc.MISLUKT  # 1 s opgelopen < 2 s
    gepauzeerd = [m(t, 5.0, gepauzeerd=True) for t in range(5)]
    assert sc.beoordeel_afspelen(gepauzeerd, "i")["uitkomst"] == sc.MISLUKT
    stilstand = [m(0, 1.0), m(1, 3.5), m(2, 3.5)]  # laatste stap loopt niet meer op
    assert sc.beoordeel_afspelen(stilstand, "i")["uitkomst"] == sc.MISLUKT


def test_afspelen_zonder_melding_of_met_verkeerde_methode_is_mislukt():
    assert sc.beoordeel_afspelen([], "i")["reden"].startswith("de client meldde")
    anders = [m(t, float(t), item="ander") for t in range(5)]
    assert sc.beoordeel_afspelen(anders, "i")["uitkomst"] == sc.MISLUKT
    direct = [m(t, float(t)) for t in range(5)]
    uit = sc.beoordeel_afspelen(direct, "i", verwachte_methode="Transcode")
    assert uit["uitkomst"] == sc.MISLUKT and "afspeelmethode" in uit["reden"]
    stream = [m(t, float(t), methode="DirectStream") for t in range(5)]
    assert sc.beoordeel_afspelen(stream, "i", verwachte_methode="Transcode")["uitkomst"] == sc.MISLUKT


def test_hervatten_schat_de_startpositie_ook_bij_een_late_eerste_melding():
    # Gemeten op de desktop: eerste melding pas na 13,8 s op 313,79 s → geschatte start 299,99 s.
    uit = sc.beoordeel_hervatten([m(13.8, 313.79), m(14.8, 314.79), m(16.0, 316.0)], "i", 300.0)
    assert uit["uitkomst"] == sc.GESLAAGD
    assert uit["geschatte_startpositie_s"] == pytest.approx(299.99)
    assert sc.beoordeel_hervatten([m(1, 300.0), m(2, 301.0), m(4, 303.0)], "i", 300.0)["uitkomst"] == sc.GESLAAGD


def test_hervatten_vanaf_het_begin_of_zonder_voortgang_is_mislukt():
    begin = sc.beoordeel_hervatten([m(1, 0.0), m(2, 1.0), m(3, 2.0), m(5, 4.0)], "i", 300.0)
    assert begin["uitkomst"] == sc.MISLUKT and "buiten" in begin["reden"]
    stil = sc.beoordeel_hervatten([m(1, 300.0), m(2, 300.0), m(3, 300.0)], "i", 300.0)
    assert stil["uitkomst"] == sc.MISLUKT and "liep niet op" in stil["reden"]
    assert sc.beoordeel_hervatten([], "i", 300.0)["uitkomst"] == sc.MISLUKT
    te_ver = sc.beoordeel_hervatten([m(1, 340.0), m(2, 341.0), m(4, 343.0)], "i", 300.0)
    assert te_ver["uitkomst"] == sc.MISLUKT


def test_bewaard_hervatpunt_moet_bij_de_laatste_melding_passen():
    assert sc.beoordeel_bewaard({"PlaybackPositionTicks": 3_069_500_000}, 306.0)["uitkomst"] == sc.GESLAAGD
    assert sc.beoordeel_bewaard({"PlaybackPositionTicks": 0}, 306.0)["uitkomst"] == sc.MISLUKT
    assert sc.beoordeel_bewaard({"PlaybackPositionTicks": 3_000_000_000}, 360.0)["uitkomst"] == sc.MISLUKT
    assert sc.beoordeel_bewaard({}, 1.0)["uitkomst"] == sc.MISLUKT


def test_ondertitel_moet_door_de_client_gemeld_worden():
    rij = [m(t, float(t), ondertitel=1) for t in range(5)]
    assert sc.beoordeel_ondertitel(rij, "i", 1)["uitkomst"] == sc.GESLAAGD
    assert sc.beoordeel_ondertitel(rij, "i", 2)["uitkomst"] == sc.MISLUKT
    assert sc.beoordeel_ondertitel(rij, "i", None)["uitkomst"] == sc.MISLUKT  # geen verwachting = nooit geslaagd
    wissel = [m(0, 0, ondertitel=0), m(1, 1, ondertitel=0), m(4, 4, ondertitel=1)]
    assert sc.beoordeel_ondertitel(wissel, "i", 0, vanaf_t=3)["uitkomst"] == sc.MISLUKT
    assert sc.beoordeel_ondertitel(wissel, "i", 1, vanaf_t=3)["uitkomst"] == sc.GESLAAGD


def test_segmenten_zonder_provider_zijn_niet_aanwezig_en_nooit_geslaagd():
    leeg = sc.beoordeel_segmenten({"S01E01": [], "S01E02": []})
    assert leeg["uitkomst"] == sc.NIET_AANWEZIG and "capability_unavailable" in leeg["reden"]
    assert sc.beoordeel_segmenten({"S01E01": [{"Type": "Intro"}]})["uitkomst"] == sc.GESLAAGD


def test_spoorindex_op_taal_en_soort():
    streams = [{"Index": 0, "Type": "Subtitle", "Language": "eng"}, {"Index": 1, "Type": "Subtitle", "Language": "nld"},
               {"Index": 2, "Type": "Video", "Language": "eng"}, {"Index": 3, "Type": "Audio", "Language": "dut"}]
    assert sc.spoor_index(streams, sc.NL_TALEN) == 1
    assert sc.spoor_index(streams, sc.EN_TALEN) == 0
    assert sc.spoor_index(streams, sc.NL_TALEN, "Audio") == 3
    assert sc.spoor_index(streams, {"fra"}) is None


def test_eindoordeel_ontbrekende_stap_is_mislukt_en_niet_aanwezig_telt_niet_mee():
    stappen = {"a": {"uitkomst": sc.GESLAAGD}, "seg": {"uitkomst": sc.NIET_AANWEZIG}}
    assert sc.eindoordeel(stappen, ["a"]) == {"validatie": "Sim-geslaagd", "mislukte_stappen": [],
                                              "niet_aanwezig": ["seg"]}
    assert sc.eindoordeel(stappen, ["a", "b"])["mislukte_stappen"] == ["b"]
    assert sc.eindoordeel({"a": {"uitkomst": sc.MISLUKT}}, ["a"])["validatie"] == "Sim-mislukt"
    assert sc.eindoordeel({}, [])["validatie"] == "Sim-geslaagd"


@pytest.mark.parametrize(("teksten", "ok"), [
    (["B03 Testserie", "SEASONS", "2"], True),                  # androidtv 0.19.10
    (["B03 Testserie", "Seasons", "Season 1", "Season 2"], True),  # web-client (telefoon, desktop)
    (["B03 Testserie", "Seasons"], False),
    (["Andere serie", "Season 1", "Season 2"], False),
])
def test_seriepagina(teksten, ok):
    assert sc.serie_seizoenen(teksten, "B03 Testserie", 2)["ok"] is ok
