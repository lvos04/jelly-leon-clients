"""Welke SDK's en welke serverversie horen bij de statische compatibiliteitscontrole (CI-workflow Clients / Compat).

De SDK-versies komen uit de clientbronnen zelf (nooit met de hand bijgehouden): jellyfin-sdk-kotlin uit
``android/gradle/libs.versions.toml`` en ``androidtv/gradle/libs.versions.toml``, jellyfin-sdk-swift uit Swiftfins
``Package.resolved``. De serverversie is de upstream-tag van de Jelly Leon-forkbasis (jelly-leon
``tools/jelly-leon/baseline.json``: ``upstream_version`` 12.4.0 sinds P4-0); de API-routes van de fork zijn gelijk aan
upstream (jelly-leon BOUWVERIFICATIE_P4-0 §3: OpenAPI structureel gelijk, alleen ``/media/v1`` erbij).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SERVER_TAG = "v12.4"  # upstream-tag van de forkbasis van jelly-leon (12.4.0-jl.0)
VORIGE_SERVER_TAG = "v10.11.11"  # de basis vóór P4-0, alleen om verdwenen routes te tonen
SWIFT_RESOLVED = "swiftfin/Swiftfin.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"
KOTLIN_RE = re.compile(r'^jellyfin-sdk\s*=\s*"([^"]+)"\s*$', re.MULTILINE)


def kotlin_sdk(repo: Path) -> dict[str, str]:
    uit = {}
    for app in ("android", "androidtv"):
        m = KOTLIN_RE.search((repo / app / "gradle/libs.versions.toml").read_text(encoding="utf-8"))
        if not m:
            raise ValueError(f"{app}: geen jellyfin-sdk-versie in gradle/libs.versions.toml")
        uit[app] = m.group(1)
    return uit


def swift_sdk(repo: Path) -> dict[str, str]:
    pins = json.loads((repo / SWIFT_RESOLVED).read_text(encoding="utf-8"))["pins"]
    pin = next(p for p in pins if p["identity"] == "jellyfin-sdk-swift")
    return {"versie": pin["state"].get("version", ""), "revisie": pin["state"]["revision"]}


def github_output(repo: Path) -> str:
    """Regels voor $GITHUB_OUTPUT; faalt als android en androidtv een andere Kotlin-SDK gebruiken."""
    k = kotlin_sdk(repo)
    if len(set(k.values())) != 1:
        raise ValueError(f"android en androidtv gebruiken een andere jellyfin-sdk-kotlin: {k}")
    s = swift_sdk(repo)
    regels = [
        f"server_tag={SERVER_TAG}",
        f"vorige_server_tag={VORIGE_SERVER_TAG}",
        f"kotlin_sdk=v{k['android']}",
        f"swift_sdk={s['revisie']}",
        f"swift_sdk_versie={s['versie']}",
    ]
    return "\n".join(regels) + "\n"
