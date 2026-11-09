"""Gedeelde helpers voor de fork-tooling van jelly-leon-clients (ADR-0001, ADR-0002, ADR-0003).

Alleen standaardbibliotheek; geen netwerk behalve via `git` zelf (fetch/ls-remote in upstream_sync.py).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_REL = "tools/clients/baseline.json"
PATCHES_REL = "docs/platform-v2/PATCHES.md"

SUBTREE_DIR_RE = re.compile(r"^git-subtree-dir:\s*(\S+?)/*\s*$", re.MULTILINE)
SUBTREE_SPLIT_RE = re.compile(r"^git-subtree-split:\s*([0-9a-f]{40})\s*$", re.MULTILINE)
GITLINK_MODE = "160000"


class ToolError(Exception):
    """Gebruiks- of omgevingsfout (exitcode 3)."""


@dataclass
class NestedSubtree:
    rel_path: str  # relatief t.o.v. de client-prefix, bv. "external/mpvqt"
    full_prefix: str  # bv. "desktop/external/mpvqt"
    upstream_repo: str
    upstream_commit: str
    protected_files: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class Client:
    key: str
    prefix: str
    upstream_repo: str
    upstream_tag: str
    upstream_commit: str
    tag_pattern: str
    fork_version: str
    protected_files: list[str]
    nested: list[NestedSubtree]
    raw: dict = field(default_factory=dict)


def run_git(repo: Path, *args: str, check: bool = True, input_text: str | None = None,
            env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    full_env.setdefault("LC_ALL", "C")
    if env:
        full_env.update(env)
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        input=input_text,
        env=full_env,
        check=False,
    )
    if check and proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise ToolError(f"git {' '.join(args)} faalde ({proc.returncode}): {detail}")
    return proc


def git_out(repo: Path, *args: str) -> str:
    return run_git(repo, *args).stdout.strip()


def load_baseline_data(repo: Path) -> dict:
    path = repo / BASELINE_REL
    if not path.is_file():
        raise ToolError(f"basislijn ontbreekt: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolError(f"basislijn is geen geldige JSON: {exc}") from exc


def parse_clients(data: dict) -> list[Client]:
    clients: list[Client] = []
    for key, raw in sorted(data.get("clients", {}).items()):
        try:
            prefix = raw["prefix"].strip("/")
            nested = [
                NestedSubtree(
                    rel_path=rel.strip("/"),
                    full_prefix=f"{prefix}/{rel.strip('/')}",
                    upstream_repo=n["upstream_repo"],
                    upstream_commit=n["upstream_commit"],
                    protected_files=list(n.get("beschermde_bestanden", [])),
                    raw=n,
                )
                for rel, n in sorted(raw.get("geneste_subtrees", {}).items())
            ]
            clients.append(
                Client(
                    key=key,
                    prefix=prefix,
                    upstream_repo=raw["upstream_repo"],
                    upstream_tag=raw["upstream_tag"],
                    upstream_commit=raw["upstream_commit"],
                    tag_pattern=raw["tag_patroon"],
                    fork_version=raw["forkversie"],
                    protected_files=list(raw.get("beschermde_bestanden", [])),
                    nested=nested,
                    raw=raw,
                )
            )
        except KeyError as exc:
            raise ToolError(f"basislijn: client '{key}' mist veld {exc}") from exc
    if not clients:
        raise ToolError("basislijn bevat geen clients")
    return clients


def load_clients(repo: Path) -> list[Client]:
    return parse_clients(load_baseline_data(repo))


def find_squash_commit(repo: Path, prefix: str, ref: str = "HEAD") -> tuple[str, str] | None:
    """Zoekt de jongste subtree-squashcommit voor exact deze prefix.

    Geeft (squash_commit, upstream_split_commit) of None. Werkt zoals `git subtree` zelf: via de trailers
    `git-subtree-dir` en `git-subtree-split` in de commitboodschap.
    """
    out = run_git(
        repo, "log", ref, "--format=%H%x1f%B%x1e", "--grep", f"^git-subtree-dir: {re.escape(prefix)}/*$",
        "--extended-regexp",
    ).stdout
    for raw_record in out.split("\x1e"):
        record = raw_record.strip()
        if not record:
            continue
        sha, _, body = record.partition("\x1f")
        dirs = SUBTREE_DIR_RE.findall(body)
        splits = SUBTREE_SPLIT_RE.findall(body)
        if dirs and dirs[0] == prefix and splits:
            return sha.strip(), splits[0]
    return None


def version_key(tag: str, pattern: str) -> tuple[int, ...] | None:
    match = re.match(pattern, tag)
    if not match:
        return None
    return tuple(int(g) if g is not None else 0 for g in match.groups())


def newest_tag(tags: list[str], pattern: str) -> str | None:
    candidates = [(version_key(t, pattern), t) for t in tags]
    candidates = [(k, t) for k, t in candidates if k is not None]
    if not candidates:
        return None
    return max(candidates)[1]


def fork_version_for(tag: str) -> str:
    return f"{tag.lstrip('v')}-jl.0"
