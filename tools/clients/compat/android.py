"""Scenario's voor de Android-apps in de emulator: inloggen, bladeren, hervatten, afspelen, ondertitels, segmenten.

Per app de fork-build (eigen applicationId) naast de officiële release; alleen de fork-app wordt bediend.
Bediening zoals
een gebruiker (aanraken op de telefoon, D-pad op de tv) en waar dat officieel bestaat via de afstandsbedieningsroutes
van de server (``/Sessions/{id}/Playing``, ``/Viewing``, ``/Command``) — dezelfde routes als "Afspelen op" in de
web-client. Beoordeeld wordt wat de **server** ziet (``scenario``).

Gemeten bij het verkennen (2026-11-10, fork-apps tegen de jelly-leon-image 12.4.0-jl.0):
- android 2.7.3 speelt video in de native speler (ExoPlayer); die meldt zich als een tweede sessie zonder
  ``SupportsMediaControl``. Afstandsopdrachten gaan naar de sessie van de webweergave; stoppen gebeurt met de
  terugknop (de native speler reageert niet op een Stop- of SetSubtitleStreamIndex-opdracht aan de webweergave).
- androidtv 0.19.10 negeert de spoorindex in ``PlayNow`` (``SocketHandler.onPlayMessage``) maar volgt
  ``SetSubtitleStreamIndex`` tijdens het afspelen; aanraken activeert op de tv niet altijd, de D-pad wel.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from . import scenario as sc
from .apk import FORK, OFFICIEEL
from .emulator import AVDS, Emulator, Knoop, zoek
from .jfapi import TICKS, Jellyfin
from .server import KIJKER, KIJKER_WW, TestServer

CLIENTNAAM = {"android": "Jellyfin for Android", "androidtv": "Jellyfin Android TV"}
VEREIST = [
    "naast_officieel",
    "inloggen",
    "bladeren",
    "hervatten",
    "hervatpunt_bewaard",
    "direct_play",
    "transcode",
    "ondertitel_voorkeur",
    "ondertitel_extern",
]
THUIS = r"^(My Media|My media|Mijn media)$"


def log(tekst: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {tekst}", flush=True)


class Volger:
    """Peilt ``GET /Sessions`` voor de sessies van de kijker met de clientnaam van deze app."""

    def __init__(self, jf: Jellyfin, client: str) -> None:
        self.jf = jf
        self.client = client.lower()
        self.gezien_ids: set[str] = set()

    def sessies(self) -> list[dict[str, Any]]:
        return [
            s
            for s in self.jf.sessies()
            if s.get("UserName") == KIJKER and (s.get("Client") or "").lower() == self.client
        ]

    def id(self) -> str:
        """De actuele bestuurbare sessie, vlak voor elke afstandsopdracht opnieuw opgezocht: gemeten op de tablet-AVD
        maakte de webweergave tijdens het bladeren een nieuwe sessie aan (de oude gaf daarna 404 op /Viewing)."""
        s = self.bestuurbaar(30)
        if s is None:
            raise RuntimeError("geen bestuurbare sessie van de app meer op de server")
        self.gezien_ids.add(s["Id"])
        return s["Id"]

    def bestuurbaar(self, timeout: float = 60) -> dict[str, Any] | None:
        einde = time.monotonic() + timeout
        while time.monotonic() < einde:
            kandidaten = [s for s in self.sessies() if s.get("SupportsMediaControl")]
            if kandidaten:
                return max(kandidaten, key=lambda s: s.get("LastActivityDate") or "")
            time.sleep(2)
        return None

    def volg(self, item_id: str, seconden: float, minimaal_s: float = 6.0) -> list[sc.Monster]:
        """Verzamelt monsters tot ``seconden`` voorbij zijn, of eerder zodra het item ≥ minimaal_s is opgelopen."""
        t0 = time.monotonic()
        uit: list[sc.Monster] = []
        while time.monotonic() - t0 < seconden:
            for s in self.sessies():
                if (s.get("NowPlayingItem") or {}).get("Id"):
                    uit.append(sc.monster(s, time.monotonic() - t0))
            rij = [m for m in sc.van_item(uit, item_id) if not m.gepauzeerd]
            if len(rij) >= 3 and rij[-1].positie_s - rij[0].positie_s >= minimaal_s:
                break
            time.sleep(1)
        return uit

    def wacht_tot_gestopt(self, timeout: float = 20) -> bool:
        einde = time.monotonic() + timeout
        while time.monotonic() < einde:
            if not any((s.get("NowPlayingItem") or {}).get("Id") for s in self.sessies()):
                return True
            time.sleep(1)
        return False


# --- UI-hulpen ----------------------------------------------------------------------------------------------------


def bevat(buiten: Knoop, binnen: Knoop) -> bool:
    x, y = binnen.midden
    return buiten.bounds[0] <= x <= buiten.bounds[2] and buiten.bounds[1] <= y <= buiten.bounds[3]


def dpad_kies(emu: Emulator, patroon: str, max_stappen: int = 14) -> bool:
    """Tv: zet de focus met de D-pad op het element en activeer het (aanraken activeert op de tv niet altijd)."""
    for _ in range(max_stappen):
        knopen = emu.dump()
        doel = zoek(knopen, patroon)
        focus = next((k for k in knopen if k.focus), None)
        if doel is None:
            time.sleep(1)
            continue
        if focus and (focus is doel or bevat(focus, doel)):
            emu.toets("KEYCODE_DPAD_CENTER")
            return True
        if focus is None:
            emu.toets("KEYCODE_DPAD_DOWN")
            continue
        (fx, fy), (dx, dy) = focus.midden, doel.midden
        if abs(dy - fy) > max(20, (focus.bounds[3] - focus.bounds[1]) // 2):
            emu.toets("KEYCODE_DPAD_DOWN" if dy > fy else "KEYCODE_DPAD_UP")
        else:
            emu.toets("KEYCODE_DPAD_RIGHT" if dx > fx else "KEYCODE_DPAD_LEFT")
    return False


def stap_uit(ok: bool, **gegevens: Any) -> dict[str, Any]:
    return {"uitkomst": sc.GESLAAGD if ok else sc.MISLUKT, **gegevens}


# --- inloggen -----------------------------------------------------------------------------------------------------


def inloggen_telefoon(emu: Emulator, pakket: str, url: str) -> dict[str, Any]:
    emu.sh(f"monkey -p {pakket} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1")
    stappen = []
    for _ in range(2):  # meldingentoestemming (API 33+) wegklikken als die verschijnt
        k = emu.wacht_op(r"^(Allow|Toestaan)$", timeout=6)
        if k:
            emu.tik(k)
            stappen.append("toestemming meldingen: Allow")
    veld = emu.wacht_op(r".*", timeout=60, klasse="EditText")
    if not veld:
        return stap_uit(False, reden=f"geen serveradresveld; scherm: {emu.teksten()}")
    emu.tik(veld)
    emu.typ(url)
    emu.toets("KEYCODE_ENTER")
    stappen.append("serveradres ingevuld (Connect to Server)")
    velden: list[Knoop] = []
    for _ in range(45):  # de webweergave laadt de web-client van de server (jelly-leon-web)
        velden = [k for k in emu.dump() if "EditText" in k.klasse]
        if len(velden) >= 2:
            break
        time.sleep(2)
    if len(velden) < 2:
        return stap_uit(False, reden=f"geen inlogvelden in de webweergave; scherm: {emu.teksten()}", stappen=stappen)
    emu.tik(velden[0])
    emu.typ(KIJKER)
    # Met Tab naar het wachtwoordveld: na het typen schuift het toetsenbord de pagina op
    # (oude coördinaten kloppen dan niet meer).
    emu.toets("KEYCODE_TAB")
    time.sleep(1)
    emu.typ(KIJKER_WW)
    emu.toets("KEYCODE_ENTER")  # niet op 'Sign In' tikken: de batterijmelding kan erover liggen
    thuis = emu.wacht_op(THUIS, timeout=60)
    stappen.append(
        "ingelogd met gebruikersnaam en wachtwoord in de web-client van de server" if thuis else "niet ingelogd"
    )
    return stap_uit(
        bool(thuis), stappen=stappen, **({} if thuis else {"reden": f"startscherm niet bereikt: {emu.teksten()}"})
    )


def inloggen_tv(emu: Emulator, pakket: str, url: str) -> dict[str, Any]:
    """androidtv 0.19.10: 'Enter server address' → adres → 'Add account' → 'Use a password' → naam + wachtwoord."""
    emu.sh(f"monkey -p {pakket} -c android.intent.category.LEANBACK_LAUNCHER 1 >/dev/null 2>&1")
    stappen = []
    if not emu.wacht_op(r"^Enter server address$", timeout=90) or not dpad_kies(emu, r"^Enter server address$"):
        return stap_uit(False, reden=f"geen startscherm van de tv-app; scherm: {emu.teksten()}")
    veld = emu.wacht_op(r"id/address$", timeout=20, klasse="EditText")
    if not veld:
        return stap_uit(False, reden=f"geen adresveld; scherm: {emu.teksten()}")
    emu.typ(url)
    emu.toets("KEYCODE_ENTER")
    stappen.append("serveradres ingevuld")
    if not emu.wacht_op(r"^Add account$", timeout=60) or not dpad_kies(emu, r"^Add account$"):
        return stap_uit(False, reden=f"geen 'Add account'; scherm: {emu.teksten()}", stappen=stappen)
    if not emu.wacht_op(r"^Use a password$", timeout=30) or not dpad_kies(emu, r"^Use a password$"):
        return stap_uit(False, reden=f"geen 'Use a password'; scherm: {emu.teksten()}", stappen=stappen)
    naam = emu.wacht_op(r"id/username$", timeout=20, klasse="EditText")
    ww = emu.wacht_op(r"id/password$", timeout=5, klasse="EditText")
    if not naam or not ww:
        return stap_uit(False, reden=f"geen inlogvelden; scherm: {emu.teksten()}", stappen=stappen)
    emu.tik(naam)
    emu.typ(KIJKER)
    emu.tik(ww)
    emu.typ(KIJKER_WW)
    emu.toets("KEYCODE_ENTER")
    thuis = emu.wacht_op(THUIS, timeout=60)
    stappen.append("ingelogd met gebruikersnaam en wachtwoord (native tv-app)" if thuis else "niet ingelogd")
    return stap_uit(
        bool(thuis), stappen=stappen, **({} if thuis else {"reden": f"startscherm niet bereikt: {emu.teksten()}"})
    )


# --- bladeren -----------------------------------------------------------------------------------------------------


def bladeren(emu: Emulator, app: str, jf: Jellyfin, volger: Volger, server: TestServer) -> dict[str, Any]:
    """Startscherm toont de bibliotheken en 'verder kijken'; de filmbibliotheek en een serie zijn te openen."""
    films = sorted(i["Name"] for i in jf.items(server.kijker_id) if i.get("Type") == "Movie")
    thuis = emu.teksten()
    gezien = {
        "films_tegel": "Films" in thuis,
        "series_tegel": "Series" in thuis,
        "verder_kijken_rij": any(t.lower().startswith("continue watching") for t in thuis),
        "hervatitem_op_startscherm": server.items.hervat["Name"] in thuis,
    }
    views = {v["Name"]: v for v in jf.a.doe("GET", "/UserViews", {"userId": server.kijker_id})["Items"]}
    jf.toon(volger.id(), views["Films"])
    time.sleep(4)
    knopen = emu.dump()
    teksten = [k.label for k in knopen]
    if app == "android":
        gezien["films_in_bibliotheek"] = [f for f in films if f in teksten]
        bib_ok = gezien["films_in_bibliotheek"] == films
    else:  # tv: rasterweergave met statusregel en teller "1 | n"
        status = next((t for t in teksten if "from 'Films'" in t), "")
        teller = next((t for t in teksten if "|" in t and t.replace("|", "").replace(" ", "").isdigit()), "")
        gezien["statusregel"], gezien["teller"] = status, teller
        bib_ok = bool(status) and teller.endswith(f"| {len(films)}")
    serie_id = server.items.afleveringen[0].get("SeriesId") if server.items.afleveringen else None
    if serie_id:
        jf.toon(volger.id(), {"Type": "Series", "Id": serie_id, "Name": "B03 Testserie"})
        emu.wacht_op(r"^B03 Testserie$", timeout=20)
        time.sleep(2)
        gezien["serie_pagina"] = sc.serie_seizoenen(emu.teksten(), "B03 Testserie", 2)
    # Het startscherm toont de bibliotheken en de gezaaide kijkgeschiedenis ('verder kijken' met het hervatitem).
    ok = (
        bib_ok
        and gezien["films_tegel"]
        and gezien["verder_kijken_rij"]
        and gezien["hervatitem_op_startscherm"]
        and bool(gezien.get("serie_pagina", {}).get("ok"))
    )
    return stap_uit(ok, gezien=gezien, verwacht_films=films)


# --- afspelen -----------------------------------------------------------------------------------------------------


def stop(emu: Emulator, app: str, jf: Jellyfin, sessie: dict[str, Any], volger: Volger) -> bool:
    if app == "android":
        emu.toets("KEYCODE_BACK")  # de native speler stoppen zoals een gebruiker
    else:
        jf.afspeelcommando(volger.id(), "Stop")
    gestopt = volger.wacht_tot_gestopt()
    time.sleep(2)
    return gestopt


def run(
    server: TestServer,
    soort: str,
    apks: dict[str, Any],
    uitmap: Path,
    label: str,
    geheugen_gib: int = 4,
    extra_stappen: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Volledige scenarioreeks voor één emulator tegen één (verse) server."""
    a = AVDS[soort]
    app = a["app"]
    fork, officieel = apks[app]["fork"], apks[app]["officieel"]
    res: dict[str, Any] = {
        "client": f"{app} {FORK[app]['versie']} (fork, {FORK[app]['pakket']})",
        "emulator": soort,
        "systeemimage": a["image"],
        "apparaat": a["apparaat"],
        "scherm": a["config"] or "standaard",
        "apk": {k: fork[k] for k in ("bestand", "sha256", "pakket", "versionName", "certificaat")},
        "officiele_apk": {k: officieel[k] for k in ("bestand", "sha256", "pakket", "versionName")},
        "stappen": {},
    }
    emu = Emulator(soort, Path(fork["pad"]).parent, geheugen_gib=geheugen_gib)
    try:
        _stappen(emu, res, server, app, apks, uitmap, label)
    except Exception as fout:  # noqa: BLE001 - elke harnas- of emulatorfout eerlijk in het bewijs, nooit stil
        res["fout"] = f"{type(fout).__name__}: {str(fout)[:600]}"
    finally:
        res["geheugen"] = emu.geheugen()
        emu.stop()
    if res["geheugen"].get("oom_kill"):
        res["stappen"]["geheugen"] = {
            "uitkomst": sc.MISLUKT,
            "reden": f"OOM-kill van de emulator binnen {geheugen_gib} GiB",
        }
    res["stappen"].update(extra_stappen or {})
    vereist = VEREIST + list(extra_stappen or {}) + (["geheugen"] if "geheugen" in res["stappen"] else [])
    res["oordeel"] = sc.eindoordeel(res["stappen"], vereist)
    return res


def _stappen(
    emu: Emulator, res: dict[str, Any], server: TestServer, app: str, apks: dict[str, Any], uitmap: Path, label: str
) -> None:
    assert server.jf
    jf, it, soort = server.jf, server.items, emu.soort
    fork, officieel = apks[app]["fork"], apks[app]["officieel"]
    st = res["stappen"]
    volger = Volger(jf, CLIENTNAAM[app])
    schot = lambda naam: emu.schermafdruk(uitmap / f"{label}-{soort}-{naam}.png")  # noqa: E731
    res["boot_s"] = round(emu.start(), 1)
    log(f"{soort}: opgestart in {res['boot_s']} s")
    installatie = {"officieel": emu.installeer(Path(officieel["pad"])), "fork": emu.installeer(Path(fork["pad"]))}
    pakketten = emu.pakketten("org.jellyfin")
    versies = {p: emu.pakketversie(p) for p in pakketten}
    st["naast_officieel"] = stap_uit(
        FORK[app]["pakket"] in pakketten and OFFICIEEL[app]["pakket"] in pakketten,
        pakketten=pakketten,
        versies=versies,
        installatie=installatie,
    )
    url = f"http://10.0.2.2:{server.poort}"
    st["inloggen"] = (inloggen_telefoon if app == "android" else inloggen_tv)(emu, FORK[app]["pakket"], url)
    schot("startscherm")
    sessie = volger.bestuurbaar() if st["inloggen"]["uitkomst"] == sc.GESLAAGD else None
    if sessie is None:
        st["inloggen"] = {
            **st["inloggen"],
            "uitkomst": sc.MISLUKT,
            "reden": st["inloggen"].get("reden", "geen bestuurbare sessie van de app op de server"),
        }
        return
    st["inloggen"]["sessie"] = {
        "client": sessie.get("Client"),
        "versie": sessie.get("ApplicationVersion"),
        "apparaat": sessie.get("DeviceName"),
    }
    if sessie.get("ApplicationVersion") != FORK[app]["versie"]:
        st["inloggen"].update(uitkomst=sc.MISLUKT, reden="de sessie is niet van de fork-app")
    log(f"{soort}: ingelogd ({sessie.get('Client')} {sessie.get('ApplicationVersion')})")

    st["bladeren"] = bladeren(emu, app, jf, volger, server)
    schot("bladeren")
    log(f"{soort}: bladeren {st['bladeren']['uitkomst']}")

    # Hervatten op het gezaaide punt (300 s) via de eigen knop van de app op de detailpagina.
    jf.toon(volger.id(), it.hervat)
    knop_patroon = r"^Resume$" if app == "android" else r"^Resume from"
    knop = emu.wacht_op(knop_patroon, timeout=30)
    if knop is None:
        st["hervatten"] = stap_uit(False, reden=f"geen hervatknop op de detailpagina: {emu.teksten()}")
    else:
        if app == "android":
            emu.tik(knop)
        else:
            dpad_kies(emu, knop_patroon)
        monsters = volger.volg(it.hervat["Id"], 25, minimaal_s=6)
        st["hervatten"] = {**sc.beoordeel_hervatten(monsters, it.hervat["Id"], server.HERVAT_S), "knop": knop.label}
        schot("hervatten")
        laatste = max((m.positie_s for m in sc.van_item(monsters, it.hervat["Id"])), default=0.0)
        stop(emu, app, jf, sessie, volger)
        st["hervatpunt_bewaard"] = sc.beoordeel_bewaard(jf.userdata(server.kijker_id, it.hervat["Id"]), laatste)
    log(f"{soort}: hervatten {st['hervatten']['uitkomst']}, bewaard {st.get('hervatpunt_bewaard', {}).get('uitkomst')}")

    jf.speel(volger.id(), it.direct_play["Id"])
    monsters = volger.volg(it.direct_play["Id"], 45, minimaal_s=6)
    st["direct_play"] = {
        **sc.beoordeel_afspelen(monsters, it.direct_play["Id"], verwachte_methode="DirectPlay"),
        "item": it.direct_play["Name"],
    }
    schot("direct_play")
    stop(emu, app, jf, sessie, volger)
    log(f"{soort}: direct_play {st['direct_play']['uitkomst']} ({st['direct_play'].get('methode')})")

    # Transcode: het eerste kandidaat-item dat de app niet direct kan spelen (afhankelijk van het apparaatprofiel).
    pogingen = []
    for item in it.transcode:
        jf.speel(volger.id(), item["Id"])
        monsters = volger.volg(item["Id"], 45, minimaal_s=6)
        poging = {**sc.beoordeel_afspelen(monsters, item["Id"], verwachte_methode="Transcode"), "item": item["Name"]}
        pogingen.append(poging)
        if poging.get("methode") == "Transcode":
            schot("transcode")
        stop(emu, app, jf, sessie, volger)
        if poging.get("methode") == "Transcode":
            break
    beste = next((p for p in pogingen if p.get("methode") == "Transcode"), pogingen[-1])
    st["transcode"] = {
        **beste,
        "pogingen": [{k: p.get(k) for k in ("item", "methode", "uitkomst", "reden")} for p in pogingen],
    }
    log(
        f"{soort}: transcode {st['transcode']['uitkomst']} "
        f"({st['transcode'].get('item')}, {st['transcode'].get('methode')})"
    )

    # Ondertitels volgens de taalvoorkeur van de gebruiker (net als een overgenomen voorkeur): NL, altijd tonen.
    jf.gebruikersconfig(server.kijker_id, {"SubtitleMode": "Always", "SubtitleLanguagePreference": "nld"})
    pi = jf.playbackinfo(server.kijker_id, it.ondertitel_ingebed["Id"])["MediaSources"][0]
    verwacht = pi.get("DefaultSubtitleStreamIndex")
    nl = sc.spoor_index(it.ondertitel_ingebed.get("MediaStreams", []), sc.NL_TALEN)
    jf.speel(volger.id(), it.ondertitel_ingebed["Id"], start_ticks=5 * TICKS)
    monsters = volger.volg(it.ondertitel_ingebed["Id"], 30, minimaal_s=6)
    st["ondertitel_voorkeur"] = {
        **sc.beoordeel_ondertitel(monsters, it.ondertitel_ingebed["Id"], verwacht),
        "nl_spoor": nl,
        "server_standaard": verwacht,
        "item": it.ondertitel_ingebed["Name"],
        "afspeelmethode": sc.meest_voorkomend([m.methode for m in monsters]),
    }
    if verwacht != nl:
        st["ondertitel_voorkeur"].update(uitkomst=sc.MISLUKT, reden="de server kiest niet het NL-spoor als standaard")
    schot("ondertitel-voorkeur")
    stop(emu, app, jf, sessie, volger)
    log(f"{soort}: ondertitel_voorkeur {st['ondertitel_voorkeur']['uitkomst']}")

    # Externe NL-ondertitel (.nl.srt naast de film), vanaf 24 s zodat er cues in beeld komen (25–45 s).
    streams = it.hervat.get("MediaStreams", [])
    nl_ext, en_ext = sc.spoor_index(streams, sc.NL_TALEN), sc.spoor_index(streams, sc.EN_TALEN)
    if app == "android":  # de web-client geeft de spoorindex van PlayNow door aan de native speler
        jf.speel(volger.id(), it.hervat["Id"], start_ticks=24 * TICKS, ondertitel=nl_ext)
        monsters = volger.volg(it.hervat["Id"], 30, minimaal_s=5)
        schot("ondertitel-extern")
        st["ondertitel_extern"] = {
            **sc.beoordeel_ondertitel(monsters, it.hervat["Id"], nl_ext),
            "route": "PlayNow met subtitleStreamIndex",
        }
        # Wisselen op afstand (informatief, niet vereist): volgt de native speler SetSubtitleStreamIndex?
        jf.algemeen_commando(volger.id(), "SetSubtitleStreamIndex", {"Index": str(en_ext)})
        meer = volger.volg(it.hervat["Id"], 9, minimaal_s=99)
        st["ondertitel_wisselen_op_afstand"] = {
            **sc.beoordeel_ondertitel(meer, it.hervat["Id"], en_ext, vanaf_t=3),
            "informatief": True,
        }
    else:  # tv: PlayNow negeert de spoorindex; wisselen met SetSubtitleStreamIndex tijdens het afspelen
        jf.speel(volger.id(), it.hervat["Id"], start_ticks=24 * TICKS)
        begin = volger.volg(it.hervat["Id"], 20, minimaal_s=2)
        jf.algemeen_commando(volger.id(), "SetSubtitleStreamIndex", {"Index": str(en_ext)})
        naar_en = volger.volg(it.hervat["Id"], 8, minimaal_s=99)
        jf.algemeen_commando(volger.id(), "SetSubtitleStreamIndex", {"Index": str(nl_ext)})
        naar_nl = volger.volg(it.hervat["Id"], 10, minimaal_s=99)
        schot("ondertitel-extern")
        en_ok = sc.beoordeel_ondertitel(naar_en, it.hervat["Id"], en_ext, vanaf_t=3)
        nl_ok = sc.beoordeel_ondertitel(naar_nl, it.hervat["Id"], nl_ext, vanaf_t=3)
        st["ondertitel_extern"] = {
            "uitkomst": sc.GESLAAGD if en_ok["uitkomst"] == nl_ok["uitkomst"] == sc.GESLAAGD else sc.MISLUKT,
            "route": "SetSubtitleStreamIndex tijdens het afspelen (EN, daarna NL)",
            "naar_en": en_ok,
            "naar_nl": nl_ok,
            "bij_start": sc.meest_voorkomend([m.ondertitel for m in begin]),
        }
    stop(emu, app, jf, sessie, volger)
    log(f"{soort}: ondertitel_extern {st['ondertitel_extern']['uitkomst']}")

    st["skip_segmenten"] = sc.beoordeel_segmenten({a["Name"]: jf.segmenten(a["Id"]) for a in it.afleveringen})
    res["bestuurbare_sessies_gezien"] = len(volger.gezien_ids)  # >1 = de app maakte onderweg een nieuwe sessie aan
