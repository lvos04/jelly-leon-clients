"""Android-telefoon- en Android TV-emulator in een container (B03 §10.14; ADR-0011 van deze repo).

Regels: alleen in een container met ``--device /dev/kvm`` (groep via ``--group-add``), één emulator tegelijk en onder
``gradle.lock`` (machinebreed), 4 GiB (geheugenlimiet = swaplimiet), geen ``--privileged``, geen Docker-socket, de
Android SDK alleen-lezen gekoppeld, headless (``-no-window``). De AVD's staan in de werkmap buiten de repo en gaan na
de run weg. De runner-image (``emulator.Dockerfile``) bevat alleen de gedeelde bibliotheken van de emulator.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET  # noqa: S405 - uiautomator-dump uit de eigen wegwerpemulator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .server import WERK, docker

SDK = Path(os.environ.get("ANDROID_HOME", str(Path.home() / "android-sdk")))
RUNNER_IMAGE = os.environ.get("JLC_EMULATOR_IMAGE", "jelly-leon-clients/emulator-runner:dev")
NAAM = "jlc-jc3-emulator"

# Kleinere schermen dan het standaardapparaat: met pixel_6 (1080x2400) haalde de emulator binnen 4 GiB een OOM-kill
# zodra de app afspeelde (gemeten in jelly-leon B03-016). De vormfactor blijft gelijk.
AVDS: dict[str, dict[str, Any]] = {
    "telefoon": {
        "image": "system-images;android-35;google_apis;x86_64",
        "apparaat": "pixel_6",
        "app": "android",
        "config": {"hw.lcd.width": "720", "hw.lcd.height": "1600", "hw.lcd.density": "280"},
    },
    "tablet": {
        "image": "system-images;android-35;google_apis;x86_64",
        "apparaat": "pixel_tablet",
        "app": "android",
        "config": {"hw.lcd.width": "1280", "hw.lcd.height": "800", "hw.lcd.density": "213"},
    },
    "tv": {"image": "system-images;android-34;android-tv;x86", "apparaat": "tv_720p", "app": "androidtv", "config": {}},
    "tv36": {
        "image": "system-images;android-36;android-tv;x86_64",
        "apparaat": "tv_720p",
        "app": "androidtv",
        "config": {},
    },
}
BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass(frozen=True)
class Knoop:
    tekst: str
    id: str
    klasse: str
    omschrijving: str
    bounds: tuple[int, int, int, int]
    focus: bool
    klikbaar: bool

    @property
    def midden(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    @property
    def label(self) -> str:
        return self.tekst or self.omschrijving


def parse_ui(xml: str) -> list[Knoop]:
    """Knopen uit een ``uiautomator dump``; lege lijst als de dump onbruikbaar is (scherm wisselt)."""
    if "<hierarchy" not in xml:
        return []
    try:
        wortel = ET.fromstring(xml[xml.index("<hierarchy") :])  # noqa: S314 - eigen emulator
    except ET.ParseError:
        return []
    uit = []
    for n in wortel.iter("node"):
        m = BOUNDS_RE.match(n.get("bounds", ""))
        if m:
            x1, y1, x2, y2 = (int(g) for g in m.groups())
            uit.append(
                Knoop(
                    n.get("text", ""),
                    n.get("resource-id", ""),
                    n.get("class", ""),
                    n.get("content-desc", ""),
                    (x1, y1, x2, y2),
                    n.get("focused") == "true",
                    n.get("clickable") == "true",
                )
            )
    return uit


def zoek(knopen: list[Knoop], patroon: str, klasse: str | None = None) -> Knoop | None:
    rx = re.compile(patroon, re.IGNORECASE)
    for k in knopen:
        if (rx.search(k.tekst) or rx.search(k.omschrijving) or rx.search(k.id)) and (
            klasse is None or klasse in k.klasse
        ):
            return k
    return None


def kvm_groep() -> int:
    """Groep van /dev/kvm (de container krijgt die groep, geen extra rechten)."""
    return os.stat("/dev/kvm").st_gid


def maak_avd(soort: str, avd_map: Path) -> str:
    """Maakt het AVD op de host (avdmanager heeft Java nodig, de container niet) in een eigen map buiten de repo."""
    a = AVDS[soort]
    naam = f"jlc-jc3-{soort}"
    avd_map.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "ANDROID_HOME": str(SDK), "ANDROID_SDK_ROOT": str(SDK), "ANDROID_AVD_HOME": str(avd_map)}
    subprocess.run(
        [
            str(SDK / "cmdline-tools/latest/bin/avdmanager"),
            "create",
            "avd",
            "-n",
            naam,
            "-k",
            a["image"],
            "-d",
            a["apparaat"],
            "--force",
        ],
        input="no\n",
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    ini = avd_map / f"{naam}.avd" / "config.ini"
    regels = [r for r in ini.read_text(encoding="utf-8").splitlines() if r.split("=", 1)[0].strip() not in a["config"]]
    regels += [f"{k}={v}" for k, v in a["config"].items()]
    ini.write_text("\n".join(regels) + "\n", encoding="utf-8")
    return naam


class Emulator:
    def __init__(self, soort: str, apk_map: Path, avd_map: Path = WERK / "avd", geheugen_gib: int = 4) -> None:
        self.soort = soort
        self.apk_map = apk_map
        self.avd_map = avd_map
        self.geheugen_gib = geheugen_gib
        self.avd = ""
        self.cid = ""

    def adb(self, *args: str, timeout: float = 120) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "exec", "-e", "HOME=/tmp", NAAM, str(SDK / "platform-tools/adb"), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def sh(self, opdracht: str, timeout: float = 120) -> str:
        return self.adb("shell", opdracht, timeout=timeout).stdout

    def start(self) -> float:
        self.avd = maak_avd(self.soort, self.avd_map)
        docker("rm", "-f", NAAM, check=False)
        kvm_gid = kvm_groep()
        self.cid = docker(
            "run",
            "-d",
            "--name",
            NAAM,
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--device",
            "/dev/kvm",
            "--group-add",
            str(kvm_gid),
            "--memory",
            f"{self.geheugen_gib}g",
            "--memory-swap",
            f"{self.geheugen_gib}g",
            "--network",
            "host",
            "--security-opt",
            "no-new-privileges",
            "--cap-drop",
            "ALL",
            "-e",
            f"ANDROID_AVD_HOME={self.avd_map}",
            "-e",
            f"ANDROID_SDK_ROOT={SDK}",
            "-e",
            "HOME=/tmp",
            "-v",
            f"{SDK}:{SDK}:ro",
            "-v",
            f"{self.avd_map}:{self.avd_map}",
            "-v",
            f"{self.apk_map}:/apk:ro",
            RUNNER_IMAGE,
            "sleep",
            "infinity",
        ).stdout.strip()
        # Eerst de adb-server (maakt /tmp/.android/adbkey): de emulator zet die sleutel bij het starten in het image;
        # zonder dit blijft het Android TV-image (ro.adb.secure) op 'unauthorized' (gemeten in jelly-leon B03-016).
        self.adb("start-server")
        t0 = time.monotonic()
        subprocess.run(
            [
                "docker",
                "exec",
                "-d",
                "-e",
                "HOME=/tmp",
                NAAM,
                "sh",
                "-c",
                f"{SDK}/emulator/emulator -avd {self.avd} -no-window -no-audio -no-boot-anim -no-snapshot "
                "-wipe-data -gpu swiftshader_indirect -feature -Vulkan -memory 2048 -cores 4 -accel on "
                "-no-metrics > /tmp/emu.log 2>&1",
            ],
            check=True,
        )  # noqa: S108 - pad in de wegwerpcontainer
        for _ in range(600):
            if self.sh("getprop sys.boot_completed", timeout=20).strip() == "1":
                return time.monotonic() - t0
            time.sleep(1)
        raise RuntimeError(
            "emulator niet opgestart binnen 600 s: "
            + docker("exec", NAAM, "tail", "-20", "/tmp/emu.log", check=False).stdout[-800:]
        )  # noqa: S108

    def installeer(self, apk: Path) -> str:
        r = self.adb("install", "-r", f"/apk/{apk.name}", timeout=300)
        return (r.stdout + r.stderr).strip()[-200:]

    def pakketten(self, voorvoegsel: str) -> list[str]:
        return sorted(
            r.removeprefix("package:").strip()
            for r in self.sh(f"pm list packages {voorvoegsel}").splitlines()
            if r.startswith("package:")
        )

    def pakketversie(self, pakket: str) -> str:
        m = re.search(r"versionName=(\S+)", self.sh(f"dumpsys package {pakket}"))
        return m.group(1) if m else ""

    def geheugen(self) -> dict[str, Any]:
        basis = Path(f"/sys/fs/cgroup/system.slice/docker-{self.cid}.scope")
        uit: dict[str, Any] = {"limiet_bytes": self.geheugen_gib * 1024**3}
        try:
            uit["piek_bytes"] = int((basis / "memory.peak").read_text().strip())
            events = dict(r.split() for r in (basis / "memory.events").read_text().splitlines())
            uit["oom"] = int(events.get("oom", 0))
            uit["oom_kill"] = int(events.get("oom_kill", 0))
        except OSError as fout:
            uit["fout"] = str(fout)
        return uit

    def stop(self) -> None:
        docker("rm", "-f", NAAM, check=False)

    # --- UI ---------------------------------------------------------------------------------------------------

    def dump(self) -> list[Knoop]:
        self.sh("uiautomator dump /sdcard/ui.xml >/dev/null 2>&1")
        return parse_ui(self.adb("exec-out", "cat", "/sdcard/ui.xml").stdout)

    def wacht_op(self, patroon: str, timeout: float = 60, klasse: str | None = None) -> Knoop | None:
        einde = time.monotonic() + timeout
        while time.monotonic() < einde:
            k = zoek(self.dump(), patroon, klasse)
            if k:
                return k
            time.sleep(2)
        return None

    def tik(self, k: Knoop, wacht: float = 1.0) -> None:
        x, y = k.midden
        self.sh(f"input tap {x} {y}")
        time.sleep(wacht)  # focus en toetsenbord moeten er zijn vóór 'input text'

    def typ(self, tekst: str) -> None:
        self.sh("input text " + shlex.quote(tekst.replace(" ", "%s")))

    def toets(self, *codes: str, wacht: float = 0.4) -> None:
        for c in codes:
            self.sh(f"input keyevent {c}")
            time.sleep(wacht)

    def teksten(self, knopen: list[Knoop] | None = None) -> list[str]:
        return [k.label for k in (knopen if knopen is not None else self.dump()) if k.label][:60]

    def schermafdruk(self, pad: Path) -> None:
        pad.parent.mkdir(parents=True, exist_ok=True)
        uit = subprocess.run(
            ["docker", "exec", "-e", "HOME=/tmp", NAAM, str(SDK / "platform-tools/adb"), "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if uit.stdout.startswith(b"\x89PNG"):
            pad.write_bytes(uit.stdout)
