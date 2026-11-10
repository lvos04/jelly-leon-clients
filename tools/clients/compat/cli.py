"""Opdrachtregel van het compatibiliteitsharnas (P4-0, JC3). Alleen ontwikkeling; zie BOUWVERIFICATIE_P4-0.md.

    python3 tools/clients/client_compat.py android --image <jelly-leon-image> [--stock-image <digest>]
        [--soorten telefoon,tv] [--vergelijk-soorten telefoon,tv] [--uit <bewijs.json>]
    python3 tools/clients/client_compat.py desktop --image <jelly-leon-image> --binary <jellyfin-desktop> [--uit …]

Per server (de jelly-leon-image en, als controlegroep, stock 12.x op dezelfde upstream-digest) en per emulator een
verse wegwerpserver met dezelfde testbibliotheek en dezelfde gezaaide kijkgeschiedenis. Emulators onder ``stack.lock``
en ``gradle.lock`` (machinebreed, één tegelijk). Exitcode 0 = bewijs geschreven (ook bij Sim-mislukt: de uitkomst
staat in het bewijs), 2 = ongeldige invoer of omgeving.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import android, apk, bewijs
from .server import BEHEER_WW, CORPUS, FILMS, KIJKER_WW, SERIES, STOCK_12_4, WERK, TestServer, docker

REPO = Path(__file__).resolve().parents[3]
APK_CACHE = Path(
    "/home/transcode/truenas-v2/.lokaal/jelly-leon-b03-016/apk"
)  # alleen lezen; sha256 wordt gecontroleerd


def log(tekst: str) -> None:
    android.log(tekst)


def corpus_herkomst() -> list[dict[str, Any]]:
    sommen: dict[str, str] = {}
    for naam, basis in (
        ("SHA256SUMS.bron.txt", "bron"),
        ("SHA256SUMS.ondertitels.txt", "bron"),
        ("SHA256SUMS.afgeleid.txt", "afgeleid"),
    ):
        pad = CORPUS / naam
        if pad.exists():
            for regel in pad.read_text(encoding="utf-8").splitlines():
                if "  " in regel:
                    som, rel = regel.split("  ", 1)
                    sommen[f"{basis}/{rel.lstrip('./')}"] = som
    uit = []
    for doel, bron in {**FILMS, **SERIES}.items():
        pad = CORPUS / bron
        # Een gekoppelde map (de testserie): elk mediabestand apart, de grondwaarheid-JSON's niet.
        bestanden = sorted(x for x in pad.rglob("*.mkv")) if pad.is_dir() else [pad]
        for b in bestanden:
            rel = str(b.relative_to(CORPUS))
            doel_b = doel + str(b)[len(str(pad)) :]
            uit.append({"in_container": doel_b, "corpus": rel, "sha256": sommen.get(rel, "onbekend")})
    return uit


def image_herkomst(image: str) -> dict[str, Any]:
    """Image-ID en herkomstlabels (versie, revisie van jelly-leon en jelly-leon-web) van de server-image."""
    r = docker("image", "inspect", "--format", "{{.Id}}|{{json .Config.Labels}}", image, check=False).stdout.strip()
    image_id, _, labels_json = r.partition("|")
    try:
        labels = json.loads(labels_json) or {}
    except ValueError:
        labels = {}
    sleutels = (
        "org.opencontainers.image.version",
        "org.opencontainers.image.revision",
        "io.github.lvos04.jelly-leon.web.revision",
        "org.opencontainers.image.base.name",
    )
    return {
        "image": image,
        "image_id": image_id,
        **{k.rsplit(".", 1)[-1] if "web" not in k else "web_revisie": labels[k] for k in sleutels if k in labels},
    }


def een_android_run(
    label: str, image: str, soort: str, apks: dict[str, Any], uitmap: Path, gib: int, migratie_van: str | None = None
) -> dict[str, Any]:
    with bewijs.slot("stack.lock", log) as w1, bewijs.slot("gradle.lock", log) as w2:
        log(f"== {label} / {soort} ({gib} GiB; wachttijd sloten {w1 + w2} s)")
        server = TestServer(image)
        try:
            extra: dict[str, dict[str, Any]] = {}
            if migratie_van:
                # JLT-60, clientdeel: kijkgeschiedenis op de oude server zaaien; de nieuwe image migreert de map.
                inrichting = server.migreer_van(migratie_van)
                extra["kijkgeschiedenis_na_upgrade"] = {
                    "uitkomst": inrichting["uitkomst"],
                    "verschillen": inrichting["verschillen"],
                    "oude_server": inrichting["oude_server"]["versie"],
                    "nieuwe_server": inrichting["nieuwe_server"]["versie"],
                }
            else:
                server.start()
                inrichting = server.inrichten()
            r = android.run(server, soort, apks, uitmap, label, geheugen_gib=gib, extra_stappen=extra)
            r["server"] = {
                "versie": server.info.get("Version"),
                "product": server.info.get("ProductName"),
                "image_id": server.image_id(),
                "inrichting": inrichting,
            }
        except Exception as fout:  # noqa: BLE001 - eerlijk in het bewijs
            r = {
                "fout": f"{type(fout).__name__}: {str(fout)[:600]}",
                "oordeel": {"validatie": "Sim-mislukt"},
                "server_log": server.logs(40)[-1500:],
            }
        finally:
            server.verwijder()
    return r


def aanvullen(oud: dict[str, Any], nieuw: dict[str, Any]) -> dict[str, Any]:
    """Nieuwe resultaten in een bestaand bewijs zetten; een vervangen resultaat blijft met zijn oordeel en fout
    zichtbaar onder ``vervangen`` (nooit stil overschreven)."""
    uit = {**oud, "resultaten": {k: dict(v) for k, v in oud.get("resultaten", {}).items()}}
    vervangen = list(oud.get("vervangen", []))
    for label, rr in nieuw["resultaten"].items():
        for soort, r in rr.items():
            vorig = uit["resultaten"].setdefault(label, {}).get(soort)
            if vorig is not None:
                vervangen.append(
                    {
                        "server": label,
                        "emulator": soort,
                        "sessie": oud.get("begin"),
                        "oordeel": vorig.get("oordeel"),
                        "fout": vorig.get("fout"),
                        "mislukte_stappen": vorig.get("oordeel", {}).get("mislukte_stappen"),
                    }
                )
            uit["resultaten"][label][soort] = r
    uit["vervangen"] = vervangen
    uit["sessies"] = [
        *oud.get("sessies", [{"begin": oud.get("begin"), "eind": oud.get("eind")}]),
        {
            "begin": nieuw.get("begin"),
            "aangevuld": sorted(f"{lbl}/{s}" for lbl, rr in nieuw["resultaten"].items() for s in rr),
        },
    ]
    return uit


def android_cmd(a: argparse.Namespace) -> int:
    soorten = [s for s in a.soorten.split(",") if s]
    vergelijk = [s for s in a.vergelijk_soorten.split(",") if s]
    uitmap = a.uit.with_suffix("")
    uitmap.mkdir(parents=True, exist_ok=True)
    apks = apk.bereid_voor(REPO, WERK / "apk", APK_CACHE)
    servers = [("jelly-leon", a.image, soorten), ("stock", a.stock_image, vergelijk)]
    document: dict[str, Any] = {
        "schema": "jelly-leon-clients/p4-0-jc3-android/1",
        "begin": bewijs.nu(),
        "doel": "JC3 / P4-0: fork-apps android 2.7.3 en androidtv 0.19.10 (eigen applicationId) tegen de Jelly Leon "
        "12.x-server, met stock 12.x op dezelfde upstream-digest als controlegroep",
        "servers": {"jelly-leon": image_herkomst(a.image), "stock": image_herkomst(a.stock_image)},
        **(
            {
                "migratie_van": image_herkomst(a.migratie_van),
                "migratie": "kijkgeschiedenis eerst op de oude server gezaaid; dezelfde datamap gemigreerd (JLT-60)",
            }
            if a.migratie_van
            else {}
        ),
        "corpus": corpus_herkomst(),
        "apks": {
            k: {s: {x: v[s][x] for x in ("bestand", "sha256", "pakket", "versionName")} for s in ("fork", "officieel")}
            for k, v in apks.items()
        },
        "regels": "emulator in een container met --device /dev/kvm, 4 GiB (geheugen = swap), --cap-drop ALL, headless, "
        "onder stack.lock en gradle.lock, één tegelijk; per client een verse wegwerpserver op 127.0.0.1",
        "resultaten": {},
        "niet_hier": bewijs.NIET_HIER,
    }
    for label, image, lijst in servers:
        for soort in lijst:
            # Eerst binnen de plan-limiet van 4 GiB; bij een OOM-kill één keer opnieuw met 5 GiB (afwijking van het
            # plan, beide pogingen in het bewijs — zelfde beleid als jelly-leon B03-016).
            pogingen = []
            for gib in (4, 5):
                r = een_android_run(label, image, soort, apks, uitmap, gib, a.migratie_van)
                pogingen.append(r)
                if not r.get("geheugen", {}).get("oom_kill"):
                    break
            r = dict(pogingen[-1])
            if len(pogingen) > 1:
                r["geheugen_afwijking"] = (
                    "binnen 4 GiB een OOM-kill van de emulator; herhaald met 5 GiB (afwijking van B03 §10.14)"
                )
                r["eerdere_poging_4gib"] = {k: pogingen[0].get(k) for k in ("oordeel", "geheugen", "fout")}
            document["resultaten"].setdefault(label, {})[soort] = r
            log(
                f"== {label} / {soort}: {r.get('oordeel', {}).get('validatie')} "
                f"{r.get('oordeel', {}).get('mislukte_stappen', '')}"
            )
    if a.aanvullen and a.uit.exists():
        document = aanvullen(json.loads(a.uit.read_text(encoding="utf-8")), document)
    jl, st = document["resultaten"].get("jelly-leon", {}), document["resultaten"].get("stock", {})
    document["vergelijking_met_stock"] = {
        s: bewijs.vergelijk(jl[s].get("stappen", {}), st[s].get("stappen", {})) for s in jl if s in st
    }
    document["regressies"] = [
        {"emulator": s, **v} for s, rij in document["vergelijking_met_stock"].items() for v in rij if v["regressie"]
    ]
    document["schermafdrukken"] = sorted(
        set(document.get("schermafdrukken", [])) | set(bewijs.comprimeer_schermafdrukken(uitmap))
    )
    document["eind"] = bewijs.nu()
    document["samenvatting"] = {
        f"{lbl}/{s}": r.get("oordeel", {}).get("validatie")
        for lbl, rr in document["resultaten"].items()
        for s, r in rr.items()
    }
    document["validatie"] = (
        "Sim-geslaagd"
        if all(r.get("oordeel", {}).get("validatie") == "Sim-geslaagd" for r in jl.values())
        and jl
        and not document["regressies"]
        else "Sim-mislukt"
    )
    bewijs.schrijf(a.uit, document, geheimen=[KIJKER_WW, BEHEER_WW])
    log(f"bewijs geschreven: {a.uit} — {document['validatie']}")
    return 0


def swiftfin_cmd(a: argparse.Namespace) -> int:
    from . import swiftfin

    document: dict[str, Any] = {
        "schema": "jelly-leon-clients/p4-0-jc3-swiftfin-protocol/1",
        "begin": bewijs.nu(),
        "doel": "ADR-0009 herbeoordeeld: serverkant van Swiftfin 1.6.1 tegen de Jelly Leon 12.x-server en stock 12.x",
        "servers": {"jelly-leon": image_herkomst(a.image), "stock": image_herkomst(a.stock_image)},
        "resultaten": {},
        "niet_hier": bewijs.NIET_HIER,
    }
    for label, image in (("jelly-leon", a.image), ("stock", a.stock_image)):
        server = TestServer(image).start()
        try:
            server.inrichten()
            document["resultaten"][label] = {**swiftfin.run(server), "server_versie": server.info.get("Version")}
        finally:
            server.verwijder()
        log(f"swiftfin-protocol {label}: {document['resultaten'][label]['oordeel']['validatie']}")
    jl, st = document["resultaten"]["jelly-leon"], document["resultaten"]["stock"]
    document["vergelijking_met_stock"] = bewijs.vergelijk(jl["stappen"], st["stappen"])
    document["regressies"] = [v for v in document["vergelijking_met_stock"] if v["regressie"]]
    document["validatie"] = (
        "Sim-geslaagd" if jl["oordeel"]["validatie"] == "Sim-geslaagd" and not document["regressies"] else "Sim-mislukt"
    )
    document["eind"] = bewijs.nu()
    bewijs.schrijf(a.uit, document, geheimen=[KIJKER_WW, BEHEER_WW])
    log(f"bewijs geschreven: {a.uit} — {document['validatie']} (app zelf: NIET GEVALIDEERD (Mac/Xcode))")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="client_compat", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="opdracht", required=True)
    pa = sub.add_parser("android", help="fork-apps in de emulator tegen de jelly-leon-image (en stock als controle)")
    pa.add_argument("--image", required=True, help="jelly-leon-image (lokaal gebouwd of uit CI)")
    pa.add_argument("--stock-image", default=STOCK_12_4)
    pa.add_argument("--soorten", default="telefoon,tv", help="emulators tegen de jelly-leon-image")
    pa.add_argument(
        "--vergelijk-soorten", default="telefoon,tv", help="emulators tegen stock (controlegroep); leeg = geen"
    )
    pa.add_argument("--uit", type=Path, default=REPO / "docs/platform-v2/test-evidence/p4-0-jc3-android-emulator.json")
    pa.add_argument(
        "--aanvullen",
        action="store_true",
        help="resultaten toevoegen aan een bestaand bewijs (een vervangen resultaat blijft zichtbaar)",
    )
    pa.add_argument(
        "--migratie-van",
        default=None,
        metavar="OUDE_IMAGE",
        help="eerst de kijkgeschiedenis op deze oude server (bv. stock 10.11.11 op digest) zaaien en dezelfde "
        "datamap met de nieuwe image migreren (JLT-60, clientdeel)",
    )
    pd = sub.add_parser("desktop", help="jellyfin-desktop 2.0.0 onder Xvfb tegen de jelly-leon-image")
    pd.add_argument("--image", required=True)
    pd.add_argument("--stock-image", default=STOCK_12_4)
    pd.add_argument("--build", type=Path, required=True, help="map met de gebouwde app (build/src/jellyfin-desktop)")
    pd.add_argument("--met-stock", action="store_true", help="ook tegen stock als controlegroep")
    pd.add_argument("--uit", type=Path, default=REPO / "docs/platform-v2/test-evidence/p4-0-jc3-desktop.json")
    ps = sub.add_parser("swiftfin", help="serverkant van het Swiftfin 1.6.1-protocol (de app zelf: Mac/Xcode nodig)")
    ps.add_argument("--image", required=True)
    ps.add_argument("--stock-image", default=STOCK_12_4)
    ps.add_argument("--uit", type=Path, default=REPO / "docs/platform-v2/test-evidence/p4-0-jc3-swiftfin-protocol.json")
    sub.add_parser("bronnen", help="server-tag en SDK-versies voor de statische controle ($GITHUB_OUTPUT-regels)")
    a = p.parse_args(argv)
    if a.opdracht == "bronnen":
        from . import bronnen

        print(bronnen.github_output(REPO), end="")
        return 0
    a.uit = a.uit.resolve()
    if a.opdracht == "android":
        if not Path("/dev/kvm").exists():
            print("geen /dev/kvm: de emulator heeft KVM nodig", file=sys.stderr)
            return 2
        return android_cmd(a)
    if a.opdracht == "swiftfin":
        return swiftfin_cmd(a)
    from . import desktop  # alleen nodig voor de desktopproef

    return desktop.main(a)


if __name__ == "__main__":
    raise SystemExit(main())
