"""Testhulpmiddelen: nep-upstreams en een nep-fork met git subtree (squash), volledig lokaal (Sim-getest)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

GIT_TEST_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
    "LC_ALL": "C",
}


@pytest.fixture(autouse=True)
def _git_env(monkeypatch, tmp_path):
    for key, value in GIT_TEST_ENV.items():
        monkeypatch.setenv(key, value)
    # Eigen, lege globale config: geen invloed van de ontwikkelmachine (signing, hooks, aliassen).
    cfg = tmp_path / "gitconfig"
    cfg.write_text("[init]\n\tdefaultBranch = main\n[advice]\n\tdetachedHead = false\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], check=False, capture_output=True, text=True,
                          env=os.environ.copy())
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} faalde: {proc.stderr}{proc.stdout}")
    return proc.stdout.strip()


def write_files(root: Path, files: dict[str, str | None]) -> None:
    for rel, content in files.items():
        path = root / rel
        if content is None:
            if path.exists():
                path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class Upstream:
    """Een nep-upstream-repo met tags; gitlinks (submodules) zijn zonder echte submodule-clone te zetten."""

    def __init__(self, path: Path):
        self.path = path
        path.mkdir(parents=True)
        git(path, "init", "-q", "-b", "main")

    def commit(self, files: dict[str, str | None], message: str, tag: str | None = None,
               gitlinks: dict[str, str] | None = None) -> str:
        write_files(self.path, files)
        git(self.path, "add", "-A")
        for rel, sha in (gitlinks or {}).items():
            git(self.path, "update-index", "--add", "--cacheinfo", f"160000,{sha},{rel}")
        git(self.path, "commit", "-q", "--allow-empty", "-m", message)
        if tag:
            git(self.path, "tag", "-a", tag, "-m", f"release {tag}")
        return git(self.path, "rev-parse", "HEAD")

    @property
    def url(self) -> str:
        return str(self.path)


@dataclass
class ClientSpec:
    key: str
    upstream: Upstream
    tag: str
    protected: list[str] = field(default_factory=lambda: ["LICENSE"])
    tag_pattern: str = r"^v(\d+)\.(\d+)\.(\d+)$"
    nested: dict[str, tuple[Upstream, str]] = field(default_factory=dict)  # rel_path -> (upstream, commit)


REGISTER_HEADER = """# Patchregister (test)

| ID | Titel | Client | Soort | Status |
|---|---|---|---|---|
"""


def patch_block(patch_id: str, client: str, files: list[str], status: str = "actief",
                drop_field: str | None = None) -> str:
    fields = {
        "Status": status,
        "Client": client,
        "Doel": "test",
        "Bestanden": ", ".join(f"`{f}`" for f in files),
        "Waarom nodig": "test",
        "Upstream-PR-kans": "laag",
        "Test": "pytest",
    }
    if drop_field:
        fields.pop(drop_field)
    rows = "\n".join(f"| {k} | {v} |" for k, v in fields.items())
    return f"\n## {patch_id} — testpatch\n\n| Veld | Waarde |\n|---|---|\n{rows}\n"


class Fork:
    def __init__(self, path: Path, specs: list[ClientSpec]):
        self.path = path
        self.specs = {s.key: s for s in specs}
        path.mkdir(parents=True)
        git(path, "init", "-q", "-b", "main")
        write_files(path, {"README.md": "fork\n"})
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", "init")
        for spec in specs:
            git(path, "subtree", "add", "--prefix", spec.key, "--squash", spec.upstream.url, spec.tag)
            for rel, (n_up, n_commit) in spec.nested.items():
                git(path, "rm", "-q", "--cached", f"{spec.key}/{rel}")
                leftover = path / spec.key / rel
                if leftover.is_dir():
                    leftover.rmdir()
                git(path, "commit", "-q", "-m", f"gitlink {rel} weg")
                git(path, "fetch", "-q", n_up.url, n_commit)
                git(path, "subtree", "add", "--prefix", f"{spec.key}/{rel}", "--squash", n_commit)
        self.write_baseline()
        self.write_register("")
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", "basislijn en register")

    def baseline_data(self) -> dict:
        clients = {}
        for spec in self.specs.values():
            commit = git(spec.upstream.path, "rev-parse", f"{spec.tag}^{{commit}}")
            clients[spec.key] = {
                "naam": spec.key,
                "prefix": spec.key,
                "upstream_repo": spec.upstream.url,
                "upstream_tag": spec.tag,
                "upstream_commit": commit,
                "upstream_tree": git(spec.upstream.path, "rev-parse", f"{spec.tag}^{{tree}}"),
                "tag_patroon": spec.tag_pattern,
                "forkversie": f"{spec.tag.lstrip('v')}-jl.0",
                "licentie": "GPL-2.0",
                "beschermde_bestanden": spec.protected,
                "geneste_subtrees": {
                    rel: {"upstream_repo": n_up.url, "upstream_commit": n_commit,
                          "upstream_tree": git(n_up.path, "rev-parse", f"{n_commit}^{{tree}}"),
                          "beschermde_bestanden": []}
                    for rel, (n_up, n_commit) in spec.nested.items()
                },
            }
        return {"schema_versie": 1, "clients": clients}

    def write_baseline(self, data: dict | None = None) -> None:
        path = self.path / "tools/clients/baseline.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data or self.baseline_data(), indent=2) + "\n", encoding="utf-8")

    def write_register(self, blocks: str) -> None:
        path = self.path / "docs/platform-v2/PATCHES.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(REGISTER_HEADER + blocks, encoding="utf-8")

    def commit_all(self, message: str) -> str:
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", message)
        return git(self.path, "rev-parse", "HEAD")

    def head(self) -> str:
        return git(self.path, "rev-parse", "HEAD")

    def branch(self) -> str:
        return git(self.path, "rev-parse", "--abbrev-ref", "HEAD")

    def branches(self) -> list[str]:
        return git(self.path, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()

    def status(self) -> str:
        return git(self.path, "status", "--porcelain")


@pytest.fixture
def make_upstream(tmp_path):
    def _make(name: str) -> Upstream:
        return Upstream(tmp_path / "upstreams" / name)
    return _make


@pytest.fixture
def simple_setup(tmp_path, make_upstream):
    """Eén client 'app' op v1.0.0 met LICENSE en twee bestanden."""
    up = make_upstream("app")
    up.commit({"LICENSE": "GPL\n", "src/main.txt": "regel 1\nregel 2\nregel 3\n", "README.md": "app\n"},
              "v1", tag="v1.0.0")
    fork = Fork(tmp_path / "fork", [ClientSpec("app", up, "v1.0.0")])
    return up, fork


@pytest.fixture
def nested_setup(tmp_path, make_upstream):
    """Client 'desk' met submodule external/dep (zoals desktop/external/mpvqt), vervangen door geneste subtree."""
    dep = make_upstream("dep")
    n1 = dep.commit({"dep.txt": "dep 1\n", "LICENSES/LGPL.txt": "lgpl\n"}, "dep 1")
    n2 = dep.commit({"dep.txt": "dep 2\n"}, "dep 2")
    up = make_upstream("desk")
    up.commit({"LICENSE": "GPL\n", "main.cpp": "int main(){}\n"}, "v1", tag="v1.0.0", gitlinks={"external/dep": n1})
    fork = Fork(tmp_path / "fork", [ClientSpec("desk", up, "v1.0.0", nested={"external/dep": (dep, n1)})])
    return up, dep, fork, n1, n2
