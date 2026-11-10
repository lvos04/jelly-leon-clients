"""Regels voor de lokale bouwcontainer van de desktop-client (tools/clients/bouwverificatie, ADR-0008).

Statisch op de echte bestanden: elke image (ook de Dockerfile-frontend) op exacte versie + `@sha256:`-digest, nooit
`latest`; de compile draait zonder netwerk, zonder capabilities, niet-root, met de bron alleen-lezen en zonder
Docker-socket; geen proxy-instellingen meer in de bouwcommando's. Zegt niets over een echte build (die staat in
BOUWVERIFICATIE_P0.md en EVIDENCE.json).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from clients_common import DEFAULT_REPO_ROOT

ROOT = Path(DEFAULT_REPO_ROOT)
DOCKERFILE = ROOT / "tools/clients/bouwverificatie/desktop.Dockerfile"
EMULATOR_DOCKERFILE = ROOT / "tools/clients/compat/emulator.Dockerfile"
BOUWSCRIPT = ROOT / "tools/clients/bouwverificatie/desktop_bouw.sh"
MAKEFILE = ROOT / "Makefile"
DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")


def code_regels(path: Path) -> list[str]:
    return [r for r in path.read_text(encoding="utf-8").splitlines() if r.strip() and not r.lstrip().startswith("#")]


def test_dockerfile_frontend_op_exacte_versie_en_digest():
    eerste = DOCKERFILE.read_text(encoding="utf-8").splitlines()[0]
    assert eerste.startswith("# syntax="), "syntax-regel hoort de eerste regel te zijn"
    image = eerste.removeprefix("# syntax=").strip()
    assert DIGEST_RE.search(image), f"frontend {image!r} niet op digest gepind"
    assert re.match(r"^docker/dockerfile:\d+\.\d+\.\d+@", image), f"frontend {image!r} niet op exacte versie"


@pytest.mark.parametrize("dockerfile", [DOCKERFILE, EMULATOR_DOCKERFILE], ids=lambda p: p.name)
def test_base_images_op_digest_en_nooit_latest(dockerfile):
    regels = code_regels(dockerfile)
    args = {m.group(1): m.group(2) for r in regels if (m := re.match(r"^ARG\s+(\w+)=(\S+)$", r))}
    froms = [r.split() for r in regels if r.upper().startswith("FROM ")]
    assert froms, "geen FROM gevonden"
    eerdere_stadia: set[str] = set()
    for delen in froms:
        ref = delen[1]
        if ref not in eerdere_stadia:  # `FROM bouw AS test` bouwt op een eerder stadium, geen externe image
            image = args.get(ref.strip("${}"), ref) if ref.startswith("$") else ref
            assert DIGEST_RE.search(image), f"base-image {image!r} niet op digest gepind"
            assert ":latest" not in image, image
            # Exacte versie: een versienummer (`24.04`) of een gedateerde snapshot-tag (`trixie-20261104-slim`).
            exact = re.search(r":(\d[\w.-]*|[a-z]+-\d{8}[\w.-]*)@", image)
            assert exact, f"base-image {image!r} zonder exacte versie-tag"
        if len(delen) >= 4 and delen[2].upper() == "AS":
            eerdere_stadia.add(delen[3])


def test_emulator_dockerfile_frontend_niet_root_en_optionele_ca():
    eerste = EMULATOR_DOCKERFILE.read_text(encoding="utf-8").splitlines()[0]
    assert DIGEST_RE.search(eerste.removeprefix("# syntax=").strip())
    regels = code_regels(EMULATOR_DOCKERFILE)
    assert [r for r in regels if r.startswith("USER ")][-1] == "USER 568:568"
    tekst = "\n".join(regels)
    assert "--mount=type=secret,id=ca_bundle,required=false" in tekst and "rm -rf /var/lib/apt/lists/*" in tekst
    assert not re.search(r"^(COPY|ADD|ENV|ARG)\b.*(PROXY|CA_BUNDLE|TOKEN)", tekst, re.MULTILINE | re.IGNORECASE)


def test_desktop_teststadium_raakt_de_standaardbouw_niet():
    regels = code_regels(DOCKERFILE)
    froms = [r for r in regels if r.upper().startswith("FROM ")]
    # Zonder --target blijft de bouwomgeving het resultaat: het laatste stadium bouwt direct op `bouw`.
    assert froms[-1] == "FROM bouw AS bouwomgeving" and "FROM bouw AS test" in froms
    tekst = "\n".join(regels)
    test_deel = tekst[tekst.index("FROM bouw AS test"):tekst.index("FROM bouw AS bouwomgeving")]
    assert "xvfb" in test_deel and "qml6-module-qtwebengine" in test_deel
    assert test_deel.rstrip().endswith("USER 568:568")


def test_dockerfile_eindigt_als_niet_root_en_zonder_geheimen_in_lagen():
    regels = code_regels(DOCKERFILE)
    users = [r for r in regels if r.startswith("USER ")]
    assert users and users[-1] == "USER 568:568"
    tekst = "\n".join(regels)
    # De optionele CA-secret mag alleen als BuildKit-secret binnenkomen (nooit COPY/ADD/ENV/ARG) en wordt opgeruimd.
    assert "--mount=type=secret,id=ca_bundle,required=false" in tekst
    assert not re.search(r"^(COPY|ADD)\b.*ca", tekst, re.MULTILINE | re.IGNORECASE)
    assert not re.search(r"^(ENV|ARG)\s+\w*(PROXY|CA_BUNDLE|TOKEN|PASSWORD)", tekst, re.MULTILINE | re.IGNORECASE)
    assert "rm -rf /tmp/deps /tmp/ca_bundle.crt" in tekst


def test_compile_draait_geisoleerd_zonder_docker_socket():
    tekst = "\n".join(code_regels(BOUWSCRIPT))
    for vereist in ("--network none", "--cap-drop ALL", "--security-opt no-new-privileges", "--user ",
                    '-v "$REPO_ROOT/desktop:/src:ro"', "--memory "):
        assert vereist in tekst, f"desktop_bouw.sh mist {vereist!r}"
    for verboden in ("docker.sock", "--privileged", "--network host", "--cap-add", "sudo "):
        assert verboden not in tekst, f"desktop_bouw.sh bevat {verboden!r}"


def test_geen_proxy_of_hostnetwerk_meer_in_de_bouwcommandos():
    for path in (MAKEFILE, BOUWSCRIPT):
        tekst = "\n".join(code_regels(path))
        assert not re.search(r"https?_proxy", tekst, re.IGNORECASE), f"{path.name}: proxy-instelling"
        assert "--network host" not in tekst, f"{path.name}: hostnetwerk"
        assert "docker.sock" not in tekst and "sudo " not in tekst, path.name
