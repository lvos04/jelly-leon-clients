"""Beoordelingsregels van de clientscenario's (puur, zonder Docker of emulator; unit-getest).

Alle oordelen gaan over wat de **server** ziet: de sessie die de client zelf meldt (``GET /Sessions``) en de
kijkgegevens die de server bewaart. Een client die niets meldt, geldt als mislukt — nooit als geslaagd.

Uitkomsten per stap: ``geslaagd``, ``mislukt`` of ``niet_aanwezig`` (de server levert de functie niet, bv. geen
mediasegmenten zonder segmentprovider: capability_unavailable). Alleen ``geslaagd``/``mislukt`` tellen mee in het
eindoordeel; ``niet_aanwezig`` staat er met reden bij en is nooit een verkapt "geslaagd".
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

TICKS = 10_000_000
NL_TALEN = {"dut", "nld", "nl", "nl-nl"}
EN_TALEN = {"eng", "en", "en-us", "en-gb"}

GESLAAGD, MISLUKT, NIET_AANWEZIG = "geslaagd", "mislukt", "niet_aanwezig"


@dataclass(frozen=True)
class Monster:
    """Eén waarneming van een clientsessie aan de serverkant."""

    t: float
    sessie: str
    item_id: str | None
    positie_s: float
    gepauzeerd: bool
    methode: str | None
    ondertitel: int | None
    audio: int | None
    transcode: dict[str, Any] | None
    client: str
    versie: str


def monster(sessie: dict[str, Any], t: float) -> Monster:
    ps = sessie.get("PlayState") or {}
    np = sessie.get("NowPlayingItem") or {}
    ti = sessie.get("TranscodingInfo")
    return Monster(
        t=round(t, 2),
        sessie=str(sessie.get("Id", "")),
        item_id=np.get("Id"),
        positie_s=round((ps.get("PositionTicks") or 0) / TICKS, 2),
        gepauzeerd=bool(ps.get("IsPaused")),
        methode=ps.get("PlayMethod"),
        ondertitel=ps.get("SubtitleStreamIndex"),
        audio=ps.get("AudioStreamIndex"),
        transcode={
            k: ti.get(k)
            for k in (
                "VideoCodec",
                "AudioCodec",
                "Container",
                "IsVideoDirect",
                "IsAudioDirect",
                "TranscodeReasons",
                "HardwareAccelerationType",
            )
        }
        if ti
        else None,
        client=str(sessie.get("Client") or ""),
        versie=str(sessie.get("ApplicationVersion") or ""),
    )


def van_item(monsters: list[Monster], item_id: str) -> list[Monster]:
    return [m for m in monsters if m.item_id == item_id]


def _loopt(rij: list[Monster], minimaal_s: float) -> tuple[bool, float]:
    """Loopt de positie echt op? (niet gepauzeerd, monotoon, in totaal ≥ minimaal_s)."""
    spelend = [m for m in rij if not m.gepauzeerd]
    if len(spelend) < 2:
        return False, 0.0
    opgelopen = spelend[-1].positie_s - spelend[0].positie_s
    stijgend = all(b.positie_s >= a.positie_s for a, b in zip(spelend, spelend[1:], strict=False))
    return stijgend and opgelopen >= minimaal_s and spelend[-1].positie_s > spelend[-2].positie_s, round(opgelopen, 2)


def meest_voorkomend(waarden: list[Any]) -> Any:
    waarden = [w for w in waarden if w is not None]
    return Counter(waarden).most_common(1)[0][0] if waarden else None


def beoordeel_afspelen(
    monsters: list[Monster], item_id: str, *, verwachte_methode: str | None = None, minimaal_s: float = 2.0
) -> dict[str, Any]:
    """Afspelen geslaagd = de client meldt dit item, de positie loopt ≥ minimaal_s op en (optioneel) met de verwachte
    afspeelmethode (``DirectPlay`` of ``Transcode``; DirectStream telt niet als transcode)."""
    rij = van_item(monsters, item_id)
    loopt, opgelopen = _loopt(rij, minimaal_s)
    methode = meest_voorkomend([m.methode for m in rij])
    transcode = next((m.transcode for m in reversed(rij) if m.transcode), None)
    redenen = []
    if not rij:
        redenen.append("de client meldde dit item niet aan de server")
    elif not loopt:
        redenen.append(f"positie liep niet ≥ {minimaal_s:g} s op (opgelopen {opgelopen} s)")
    if verwachte_methode and rij and methode != verwachte_methode:
        redenen.append(f"afspeelmethode {methode!r}, verwacht {verwachte_methode!r}")
    return {
        "uitkomst": MISLUKT if redenen else GESLAAGD,
        "methode": methode,
        "opgelopen_s": opgelopen,
        "posities_s": [m.positie_s for m in rij][-8:],
        "transcode": transcode,
        "client": rij[-1].client if rij else None,
        "versie": rij[-1].versie if rij else None,
        **({"reden": "; ".join(redenen)} if redenen else {}),
    }


def beoordeel_hervatten(
    monsters: list[Monster], item_id: str, hervat_s: float, *, marge_s: float = 10.0
) -> dict[str, Any]:
    """Hervatten op het juiste punt: de geschatte startpositie ligt binnen ± marge_s van het hervatpunt en loopt op.

    De monsters beginnen (t = 0) op het moment van de startactie (knop of opdracht). Een client meldt zijn positie pas
    na enkele seconden; de startpositie wordt daarom geschat als ``eerste gemelde positie − t van die melding`` (een
    trage start maakt de schatting lager, nooit hoger). Begint de client bij 0, dan is dat altijd mislukt.
    """
    alle = van_item(monsters, item_id)
    rij = [m for m in alle if m.positie_s > 0] or alle
    if not rij:
        return {"uitkomst": MISLUKT, "reden": "de client meldde het item niet", "hervatpunt_s": hervat_s}
    eerste = rij[0]
    geschat = round(eerste.positie_s - eerste.t, 2)
    loopt, opgelopen = _loopt(rij, 2.0)
    redenen = []
    if not hervat_s - marge_s <= geschat <= hervat_s + marge_s:
        redenen.append(f"geschatte startpositie {geschat} s ligt buiten {hervat_s:g} ± {marge_s:g} s")
    if not loopt:
        redenen.append(f"positie liep niet op (opgelopen {opgelopen} s)")
    return {
        "uitkomst": MISLUKT if redenen else GESLAAGD,
        "hervatpunt_s": hervat_s,
        "eerste_positie_s": eerste.positie_s,
        "eerste_melding_na_s": eerste.t,
        "geschatte_startpositie_s": geschat,
        "afwijking_s": round(geschat - hervat_s, 2),
        "opgelopen_s": opgelopen,
        "posities_s": [m.positie_s for m in rij][-8:],
        **({"reden": "; ".join(redenen)} if redenen else {}),
    }


def beoordeel_bewaard(
    userdata: dict[str, Any], laatste_positie_s: float, *, tolerantie_s: float = 15.0
) -> dict[str, Any]:
    """Na stoppen bewaart de server het hervatpunt dat de client meldde (± tolerantie)."""
    bewaard = (userdata.get("PlaybackPositionTicks") or 0) / TICKS
    ok = abs(bewaard - laatste_positie_s) <= tolerantie_s and bewaard > 0
    uit = {
        "uitkomst": GESLAAGD if ok else MISLUKT,
        "bewaard_s": round(bewaard, 2),
        "laatste_gemelde_positie_s": laatste_positie_s,
        "tolerantie_s": tolerantie_s,
    }
    if not ok:
        uit["reden"] = "bewaard hervatpunt wijkt af van de laatst gemelde positie"
    return uit


def beoordeel_ondertitel(
    monsters: list[Monster], item_id: str, verwacht: int | None, *, vanaf_t: float = 0.0
) -> dict[str, Any]:
    """De client meldt (vanaf ``vanaf_t``) het verwachte ondertitelspoor voor dit item."""
    rij = [m for m in van_item(monsters, item_id) if m.t >= vanaf_t]
    gemeld = [m.ondertitel for m in rij]
    if verwacht is None:
        return {"uitkomst": MISLUKT, "reden": "geen verwacht ondertitelspoor bepaald", "gemeld": gemeld[-6:]}
    ok = bool(rij) and verwacht in gemeld
    uit = {"uitkomst": GESLAAGD if ok else MISLUKT, "verwacht_index": verwacht, "gemeld": gemeld[-6:]}
    if not ok:
        uit["reden"] = "client meldde het verwachte ondertitelspoor niet" if rij else "de client meldde het item niet"
    return uit


def beoordeel_segmenten(per_item: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Skipknoppen kunnen alleen beproefd worden als de server segmenten levert (12.x: alleen via een provider)."""
    aantallen = {naam: len(lijst) for naam, lijst in per_item.items()}
    if not any(aantallen.values()):
        return {
            "uitkomst": NIET_AANWEZIG,
            "aantallen": aantallen,
            "reden": "capability_unavailable: de server levert geen mediasegmenten (Jellyfin 12.4 heeft geen "
            "ingebouwde segmentprovider en de Jelly Leon-plugin 12.4.0-jl.0 implementeert er geen; F6 volgt "
            "in P4) — skipknoppen niet beproefd",
        }
    return {"uitkomst": GESLAAGD, "aantallen": aantallen}


def serie_seizoenen(teksten: list[str], serie: str, aantal: int) -> dict[str, Any]:
    """Seriepagina: de naam staat er en de seizoenen zijn zichtbaar ('Season 1'… in de web-client, 'SEASONS' + het
    aantal in de tv-app)."""
    seizoenen = [t for t in teksten if re.fullmatch(r"(?i)season \d+", t.strip())]
    tv_vorm = any(t.strip().upper() == "SEASONS" for t in teksten) and str(aantal) in [t.strip() for t in teksten]
    ok = serie in teksten and (len(seizoenen) >= aantal or tv_vorm)
    return {"ok": ok, "seizoenen": seizoenen, "tv_telling": tv_vorm}


def spoor_index(media_streams: list[dict[str, Any]], talen: set[str], soort: str = "Subtitle") -> int | None:
    for s in media_streams:
        if s.get("Type") == soort and str(s.get("Language") or "").lower() in talen:
            return s.get("Index")
    return None


def eindoordeel(stappen: dict[str, dict[str, Any]], vereist: list[str]) -> dict[str, Any]:
    """Sim-geslaagd alleen als elke vereiste stap geslaagd is; een ontbrekende stap telt als mislukt."""
    mislukt = [s for s in vereist if stappen.get(s, {}).get("uitkomst") != GESLAAGD]
    niet_aanwezig = [s for s, v in stappen.items() if v.get("uitkomst") == NIET_AANWEZIG]
    return {
        "validatie": "Sim-mislukt" if mislukt else "Sim-geslaagd",
        "mislukte_stappen": mislukt,
        "niet_aanwezig": niet_aanwezig,
    }


def als_dict(monsters: list[Monster]) -> list[dict[str, Any]]:
    return [asdict(m) for m in monsters]
