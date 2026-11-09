"""Regels voor de lokale bouwcontainer van de desktop-client (tools/clients/bouwverificatie, ADR-0008).

Statisch op de echte bestanden: elke image (ook de Dockerfile-frontend) op exacte versie + `@sha256:`-digest, nooit
`latest`; de compile draait zonder netwerk, zonder capabilities, niet-root, met de bron alleen-lezen en zonder
Docker-socket; geen proxy-instellingen meer in de bouwcommando's. Zegt niets over een echte build (die staat in
BOUWVERIFICATIE_P0.md en EVIDENCE.json).
"""

from __future__ import annotations

import re
from pathlib import Path

from clients_common import DEFAULT_REPO_ROOT

ROOT = Path(DEFAULT_REPO_ROOT)
DOCKERFILE = ROOT / "tools/clients/bouwverificatie/desktop.Dockerfile"
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


def test_base_images_op_digest_en_nooit_latest():
    regels = code_regels(DOCKERFILE)
    args = {m.group(1): m.group(2) for r in regels if (m := re.match(r"^ARG\s+(\w+)=(\S+)$", r))}
    froms = [r.split()[1] for r in regels if r.upper().startswith("FROM ")]
    assert froms, "geen FROM gevonden"
    for ref in froms:
        image = args.get(ref.strip("${}"), ref) if ref.startswith("$") else ref
        assert DIGEST_RE.search(image), f"base-image {image!r} niet op digest gepind"
        assert ":latest" not in image, image
        assert re.search(r":\d[\w.-]*@", image), f"base-image {image!r} zonder exacte versie-tag"


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
