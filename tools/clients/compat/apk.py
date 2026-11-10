"""APK's voor de emulatortests: de fork-builds met de eigen applicationId en de officiële upstream-releases.

- Fork: ``assembleLibreRelease`` (android) en ``assembleRelease`` (androidtv) zonder handtekening (de buildscripts
  ondertekenen alleen met een sleutel uit de omgeving), daarna ondertekend met een **wegwerp-testsleutel** die per
  run in de werkmap ontstaat en daarna verdwijnt. Dat is géén releasesleutel: verspreiden wacht op het besluit over
  ondertekening en kanaal (ADR-0008). Zo test de emulator de echte release-ID (``org.jellyfin.*.jellyleon``, zonder
  de debug-suffix) en de R8-build van android.
- Officieel: de upstream-release-APK, alleen na een sha256-controle (download via een tijdelijk bestand en atomaire
  hernoeming), om te tonen dat de fork-app er **naast** geïnstalleerd kan worden.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

SDK = Path(os.environ.get("ANDROID_HOME", str(Path.home() / "android-sdk")))
BUILD_TOOLS = os.environ.get("JLC_BUILD_TOOLS", "36.0.0")

FORK = {
    "android": {
        "pakket": "org.jellyfin.mobile.jellyleon",
        "versie": "2.7.3-jl.1",
        "uitvoer": "android/app/build/outputs/apk/libre/release/"
        "jellyfin-android-v2.7.3-jl.1-libre-release-unsigned.apk",
    },
    "androidtv": {
        "pakket": "org.jellyfin.androidtv.jellyleon",
        "versie": "0.19.10-jl.1",
        "uitvoer": "androidtv/app/build/outputs/apk/release/jellyfin-androidtv-v0.19.10-jl.1-release-unsigned.apk",
    },
}
OFFICIEEL = {
    "android": {
        "pakket": "org.jellyfin.mobile",
        "naam": "jellyfin-android-v2.7.3-libre-release.apk",
        "url": "https://github.com/jellyfin/jellyfin-android/releases/download/v2.7.3/jellyfin-android-v2.7.3-libre-release.apk",
        "sha256": "f9f4b3ab46cc9434df811194c2d4351417f4db83a4c1a0facd0a662d69533f7f",
    },
    "androidtv": {
        "pakket": "org.jellyfin.androidtv",
        "naam": "jellyfin-androidtv-v0.19.10-release.apk",
        "url": "https://github.com/jellyfin/jellyfin-androidtv/releases/download/v0.19.10/jellyfin-androidtv-v0.19.10-release.apk",
        "sha256": "8510a517c99927076082917f41bf306dd7a2546c59d492dd11bde18d6e2e4628",
    },
}
BADGING_RE = re.compile(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'")


def sha256(pad: Path) -> str:
    h = hashlib.sha256()
    with pad.open("rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def tool(naam: str) -> str:
    pad = SDK / "build-tools" / BUILD_TOOLS / naam
    if not pad.exists():
        raise FileNotFoundError(f"{pad} ontbreekt (ANDROID_HOME/build-tools {BUILD_TOOLS})")
    return str(pad)


def haal_officieel(app: str, map_: Path, cache: Path | None = None) -> Path:
    """Officiële APK: uit een lokale cache of via download, altijd met sha256-controle en atomaire hernoeming."""
    a = OFFICIEEL[app]
    doel = map_ / a["naam"]
    map_.mkdir(parents=True, exist_ok=True)
    if doel.exists() and sha256(doel) == a["sha256"]:
        return doel
    tijdelijk = doel.with_suffix(".apk.deel")
    if cache and (cache / a["naam"]).exists():
        shutil.copyfile(cache / a["naam"], tijdelijk)
    else:
        with urllib.request.urlopen(a["url"], timeout=300) as r, tijdelijk.open("wb") as f:  # noqa: S310 - vaste URL
            shutil.copyfileobj(r, f)
    if sha256(tijdelijk) != a["sha256"]:
        tijdelijk.unlink(missing_ok=True)
        raise RuntimeError(f"sha256 van {a['naam']} klopt niet; niet gebruikt")
    tijdelijk.replace(doel)
    return doel


def teken_met_testsleutel(ongetekend: Path, doel: Path, werk: Path) -> dict[str, Any]:
    """Ondertekent met een per run nieuw gemaakte wegwerpsleutel (nooit bewaard, nooit in een repo of log)."""
    werk.mkdir(parents=True, exist_ok=True)
    sleutel = werk / "wegwerp-testsleutel.p12"
    wachtwoord = secrets.token_urlsafe(24)
    sleutel.unlink(missing_ok=True)
    try:
        subprocess.run(
            [
                "keytool",
                "-genkeypair",
                "-keystore",
                str(sleutel),
                "-storetype",
                "PKCS12",
                "-alias",
                "test",
                "-keyalg",
                "RSA",
                "-keysize",
                "2048",
                "-validity",
                "2",
                "-dname",
                "CN=Jelly Leon emulatortest",
                "-storepass:env",
                "JLC_SLEUTEL_WW",
                "-keypass:env",
                "JLC_SLEUTEL_WW",
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "JLC_SLEUTEL_WW": wachtwoord},
        )
        doel.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                tool("apksigner"),
                "sign",
                "--ks",
                str(sleutel),
                "--ks-pass",
                "env:JLC_SLEUTEL_WW",
                "--out",
                str(doel),
                str(ongetekend),
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "JLC_SLEUTEL_WW": wachtwoord},
        )
    finally:
        sleutel.unlink(missing_ok=True)
    controle = subprocess.run(
        [tool("apksigner"), "verify", "--print-certs", str(doel)], capture_output=True, text=True, check=False
    )
    doel.with_suffix(".apk.idsig").unlink(missing_ok=True)
    return {
        "handtekening_geldig": controle.returncode == 0,
        "certificaat": next(
            (r.split(":", 1)[1].strip() for r in controle.stdout.splitlines() if "certificate DN" in r), ""
        ),
        "sleutel": "wegwerp-testsleutel (per run gemaakt en verwijderd; geen releasesleutel, ADR-0008)",
    }


def badging(apk: Path) -> dict[str, Any]:
    uit = subprocess.run(
        [tool("aapt2"), "dump", "badging", str(apk)], capture_output=True, text=True, check=True
    ).stdout
    m = BADGING_RE.search(uit)
    label = re.search(r"application-label:'([^']*)'", uit)
    if not m:
        raise RuntimeError(f"geen pakketregel in aapt2-uitvoer van {apk.name}")
    return {
        "pakket": m.group(1),
        "versionCode": int(m.group(2)),
        "versionName": m.group(3),
        "label": label.group(1) if label else None,
        "sha256": sha256(apk),
        "bestand": apk.name,
    }


def bereid_voor(repo: Path, map_: Path, cache: Path | None = None) -> dict[str, dict[str, Any]]:
    """Fork-APK's (ondertekend met de wegwerpsleutel) en officiële APK's klaarzetten, met aapt2-controle van de ID."""
    uit: dict[str, dict[str, Any]] = {}
    for app, f in FORK.items():
        ongetekend = repo / f["uitvoer"]
        if not ongetekend.exists():
            raise FileNotFoundError(f"{ongetekend} ontbreekt: eerst de release bouwen (zie BOUWVERIFICATIE_P4-0.md)")
        doel = map_ / ongetekend.name.replace("-unsigned", "-testsleutel")
        teken = teken_met_testsleutel(ongetekend, doel, map_ / "sleutel")
        info = badging(doel)
        if info["pakket"] != f["pakket"] or info["versionName"] != f["versie"]:
            raise RuntimeError(
                f"{app}: aapt2 meldt {info['pakket']} {info['versionName']}, verwacht {f['pakket']} {f['versie']}"
            )
        off = haal_officieel(app, map_, cache)
        uit[app] = {"fork": {**info, **teken, "pad": str(doel)}, "officieel": {**badging(off), "pad": str(off)}}
    return uit
