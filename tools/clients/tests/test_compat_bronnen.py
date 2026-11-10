"""SDK-versies en server-tag voor de statische compatibiliteitscontrole komen uit de clientbronnen
(compat/bronnen.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from clients_common import DEFAULT_REPO_ROOT
from compat import bronnen

ROOT = Path(DEFAULT_REPO_ROOT)


def test_echte_repo_kotlin_en_swift():
    assert bronnen.kotlin_sdk(ROOT) == {"android": "1.7.1", "androidtv": "1.7.1"}
    s = bronnen.swift_sdk(ROOT)
    assert s["versie"] == "3.0.0" and len(s["revisie"]) == 40
    uit = bronnen.github_output(ROOT)
    assert "server_tag=v12.4\n" in uit and "kotlin_sdk=v1.7.1\n" in uit and uit.endswith("\n")


def test_verschillende_kotlin_sdk_faalt(tmp_path):
    for app, versie in (("android", "1.7.1"), ("androidtv", "1.8.12")):
        (tmp_path / app / "gradle").mkdir(parents=True)
        (tmp_path / app / "gradle/libs.versions.toml").write_text(f'[versions]\njellyfin-sdk = "{versie}"\n')
    resolved = tmp_path / bronnen.SWIFT_RESOLVED
    resolved.parent.mkdir(parents=True)
    resolved.write_text(json.dumps({"pins": [{"identity": "jellyfin-sdk-swift", "state": {"revision": "a" * 40}}]}))
    with pytest.raises(ValueError, match="andere jellyfin-sdk-kotlin"):
        bronnen.github_output(tmp_path)


def test_ontbrekende_kotlin_sdk_faalt(tmp_path):
    (tmp_path / "android/gradle").mkdir(parents=True)
    (tmp_path / "android/gradle/libs.versions.toml").write_text("[versions]\n")
    with pytest.raises(ValueError, match="geen jellyfin-sdk"):
        bronnen.kotlin_sdk(tmp_path)
