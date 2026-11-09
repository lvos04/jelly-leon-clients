#!/usr/bin/env python3
"""Upstream-sync per client met git subtree (squash) in een eigen branch `sync/<client>-<tag>` (ADR-0002).

Subcommando's
  status  Per client: basislijn-tag, nieuwste stabiele upstream-tag (git ls-remote) en oordeel
          `actueel` | `update_beschikbaar` | `unknown`. Een netwerkfout geeft `unknown`, nooit `actueel`.
  sync    Voor één client: upstream-tag ophalen, branch `sync/<client>-<tag>` maken,
          `git subtree merge --prefix <map> --squash <tag-commit>` (gelijk aan
          `git subtree pull --prefix <map> --squash <upstream-url> <tag>`), geneste subtrees (vervangen
          submodules, ADR-0005) meenemen naar de nieuwe upstream-pin, de basislijn bijwerken en de forkregels
          (check_clients.py) controleren.

Veiligheid
  * Weigert te starten met een vuile werkboom of als de syncbranch al bestaat (exitcode 3).
  * Elk conflict, een nieuwe/verdwenen submodule of een overtreding van de forkregels → alles terugdraaien
    (oorspronkelijke branch terug, syncbranch weg, werkboom schoon) en exitcode 2 (EX48: incompatibele
    upstream-update faalt, geen deploy).
  * Pusht nooit en voegt nooit samen met de hoofdbranch: pushen doet de workflow, samenvoegen een mens na
    review en groene CI (R2).

Exitcodes: 0 = gelukt of al actueel, 2 = sync faalt, 3 = gebruiks-/omgevingsfout.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_clients  # noqa: E402
from clients_common import (  # noqa: E402
    BASELINE_REL,
    DEFAULT_REPO_ROOT,
    GITLINK_MODE,
    Client,
    ToolError,
    fork_version_for,
    git_out,
    load_baseline_data,
    newest_tag,
    parse_clients,
    run_git,
    version_key,
)

LS_REMOTE_TIMEOUT_S = 120
TEMP_REF_PREFIX = "refs/jlc-sync"


class SyncFailure(Exception):
    """De sync kan niet veilig worden voltooid (exitcode 2)."""


def ls_remote_tags(url: str) -> list[str] | None:
    try:
        proc = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", url],
            capture_output=True, text=True, timeout=LS_REMOTE_TIMEOUT_S, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    tags = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].startswith("refs/tags/"):
            tags.append(parts[1][len("refs/tags/"):])
    return tags


def status(repo: Path, url_overrides: dict[str, str] | None = None) -> list[dict]:
    url_overrides = url_overrides or {}
    rows = []
    for client in parse_clients(load_baseline_data(repo)):
        url = url_overrides.get(client.key, client.upstream_repo)
        tags = ls_remote_tags(url)
        row = {"client": client.key, "basislijn_tag": client.upstream_tag, "upstream_repo": url}
        if tags is None:
            row.update(nieuwste_tag=None, oordeel="unknown", reden="upstream niet bereikbaar (git ls-remote faalde)")
        else:
            latest = newest_tag(tags, client.tag_pattern)
            if latest is None:
                row.update(nieuwste_tag=None, oordeel="unknown", reden="geen stabiele tag volgens tag_patroon")
            elif version_key(latest, client.tag_pattern) > version_key(client.upstream_tag, client.tag_pattern):
                row.update(nieuwste_tag=latest, oordeel="update_beschikbaar", reden="")
            else:
                row.update(nieuwste_tag=latest, oordeel="actueel", reden="")
        rows.append(row)
    return rows


def _is_clean(repo: Path) -> bool:
    return git_out(repo, "status", "--porcelain", "--untracked-files=normal") == ""


def _gitlinks(repo: Path, commit: str) -> dict[str, str]:
    out = run_git(repo, "ls-tree", "-r", "-z", commit).stdout
    links = {}
    for record in out.split("\0"):
        if record.startswith(GITLINK_MODE + " "):
            meta, _, path = record.partition("\t")
            links[path] = meta.split()[2]
    return links


def _gitmodules_url(repo: Path, commit: str, path: str) -> str:
    proc = run_git(repo, "config", "--blob", f"{commit}:.gitmodules", "--get-regexp", r"submodule\..*\.(path|url)",
                   check=False)
    entries: dict[str, dict[str, str]] = {}
    for line in proc.stdout.splitlines():
        key, _, value = line.partition(" ")
        name, _, attr = key[len("submodule."):].rpartition(".")
        entries.setdefault(name, {})[attr] = value
    for entry in entries.values():
        if entry.get("path") == path:
            return entry.get("url", "onbekend")
    return "onbekend"


def _fetch(repo: Path, url: str, *refs: str) -> None:
    proc = run_git(repo, "fetch", "--quiet", "--no-tags", url, *refs, check=False)
    if proc.returncode != 0:
        raise SyncFailure(f"ophalen van {', '.join(refs)} uit {url} faalde: {proc.stderr.strip()}")


def _resolve_nested_gitlink_conflicts(repo: Path, client: Client) -> list[str]:
    """Lost alleen conflicten op die uitsluitend een vervangen submodule-gitlink betreffen.

    Upstream wijzigt de pin van een submodule die wij als geneste subtree (map) hebben: git meldt dan een
    file/directory-conflict op `<map>` of `<map>~<rev>`. Wij houden onze map; de nieuwe pin volgt daarna via
    een geneste subtree-merge. Elk ander conflict wordt niet aangeraakt.
    """
    out = run_git(repo, "ls-files", "-u", "-z").stdout
    entries = []
    for record in out.split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        mode, _sha, _stage = meta.split()
        entries.append((mode, path))
    if not entries:
        return []
    nested_paths = [f"{client.prefix}/{n.rel_path}" for n in client.nested]

    def is_nested_gitlink(mode: str, path: str) -> bool:
        return mode == GITLINK_MODE and any(path == p or path.startswith(p + "~") for p in nested_paths)

    unexpected = sorted({p for m, p in entries if not is_nested_gitlink(m, p)})
    if unexpected:
        raise SyncFailure("mergeconflict(en) met upstream: " + ", ".join(unexpected))
    paths = sorted({p for _m, p in entries})
    run_git(repo, "rm", "--quiet", "--cached", "--", *paths)
    for path in paths:
        leftover = repo / path
        if leftover.is_dir() and path not in nested_paths:
            shutil.rmtree(leftover)
        elif leftover.exists() and not leftover.is_dir():
            leftover.unlink()
    if run_git(repo, "ls-files", "-u").stdout.strip():
        raise SyncFailure("onopgeloste conflicten na het afhandelen van submodule-gitlinks")
    run_git(repo, "commit", "--quiet", "--no-edit")
    return paths


def _subtree_merge(repo: Path, prefix: str, commit: str, message: str) -> subprocess.CompletedProcess:
    return run_git(repo, "subtree", "merge", "--prefix", prefix, "--squash", "-m", message, commit, check=False)


def sync(repo: Path, client_key: str, tag: str | None = None, url_override: str | None = None,
         nested_url_overrides: dict[str, str] | None = None, branch_prefix: str = "sync") -> dict:
    nested_url_overrides = nested_url_overrides or {}
    data = load_baseline_data(repo)
    clients = {c.key: c for c in parse_clients(data)}
    if client_key not in clients:
        raise ToolError(f"onbekende client '{client_key}' (bekend: {', '.join(sorted(clients))})")
    client = clients[client_key]
    url = url_override or client.upstream_repo

    if not _is_clean(repo):
        raise ToolError("werkboom is niet schoon; commit of stash eerst je wijzigingen")

    tags = ls_remote_tags(url)
    if tags is None:
        raise ToolError(f"upstream {url} niet bereikbaar (git ls-remote faalde) — status unknown, niets gewijzigd")
    if tag is None:
        tag = newest_tag(tags, client.tag_pattern)
        if tag is None:
            raise ToolError(f"geen stabiele upstream-tag gevonden volgens patroon {client.tag_pattern}")
    elif tag not in tags:
        raise ToolError(f"tag '{tag}' bestaat niet in {url}")
    new_key = version_key(tag, client.tag_pattern)
    if new_key is None:
        raise ToolError(f"tag '{tag}' past niet bij tag_patroon {client.tag_pattern}")
    old_key = version_key(client.upstream_tag, client.tag_pattern)
    summary = {"client": client.key, "van_tag": client.upstream_tag, "naar_tag": tag, "branch": None,
               "geneste_updates": [], "opgeloste_gitlinkconflicten": [], "resultaat": None}
    if new_key == old_key:
        summary["resultaat"] = "actueel"
        return summary
    if new_key < old_key:
        raise ToolError(f"tag '{tag}' is ouder dan de basislijn '{client.upstream_tag}'; terugzetten is geen sync")

    branch = f"{branch_prefix}/{client.key}-{tag}"
    if run_git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0:
        raise ToolError(f"branch '{branch}' bestaat al")

    # Nieuwe tag (naar een tijdelijke ref) én de vorige upstream-commit ophalen: git subtree heeft die laatste
    # nodig om de squash te vergelijken, en in een verse CI-clone ontbreekt hij (squashcommits verwijzen er
    # niet naar). De tijdelijke ref verdwijnt altijd weer.
    temp_ref = f"{TEMP_REF_PREFIX}/{client.key}"
    try:
        _fetch(repo, url, f"+refs/tags/{tag}:{temp_ref}", client.upstream_commit)
        new_commit = git_out(repo, "rev-parse", f"{temp_ref}^{{commit}}")
        summary["upstream_commit"] = new_commit
        upstream_links = _check_submodules(repo, client, tag, new_commit)
        _merge_on_branch(repo, data, client, tag, url, new_commit, upstream_links, nested_url_overrides,
                         branch, summary)
    finally:
        run_git(repo, "update-ref", "-d", temp_ref, check=False)

    summary["branch"] = branch
    summary["resultaat"] = "gesynchroniseerd"
    return summary


def _check_submodules(repo: Path, client: Client, tag: str, new_commit: str) -> dict[str, str]:
    """Upstream-gitlinks moeten precies de bekende geneste subtrees zijn (ADR-0005); anders niets doen."""
    upstream_links = _gitlinks(repo, new_commit)
    nested_rel = {n.rel_path for n in client.nested}
    unknown = sorted(p for p in upstream_links if p not in nested_rel)
    if unknown:
        details = ", ".join(f"{p} ({_gitmodules_url(repo, new_commit, p)})" for p in unknown)
        raise SyncFailure(f"upstream {tag} bevat nieuwe submodule(s): {details}. Handmatig beoordelen en als "
                          f"geneste subtree toevoegen (ADR-0005)")
    vanished = sorted(p for p in nested_rel if p not in upstream_links)
    if vanished:
        raise SyncFailure(f"upstream {tag} heeft submodule(s) {', '.join(vanished)} niet meer; geneste subtree "
                          f"handmatig heroverwegen (ADR-0005)")
    return upstream_links


def _merge_on_branch(repo: Path, data: dict, client: Client, tag: str, url: str, new_commit: str,
                     upstream_links: dict[str, str], nested_url_overrides: dict[str, str], branch: str,
                     summary: dict) -> None:
    original = git_out(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if original == "HEAD":
        original = git_out(repo, "rev-parse", "HEAD")
    run_git(repo, "checkout", "--quiet", "-b", branch)
    try:
        message = (
            f"Upstream-sync: {client.key} {client.upstream_tag} → {tag} (git subtree, squash)\n\n"
            f"Upstream: {url} {tag} ({new_commit[:12]}).\n"
            f"Voorgesteld door tools/clients/upstream_sync.py in branch {branch}; samenvoegen in de\n"
            f"hoofdbranch alleen na review en groene CI (R2, ADR-0002). Geen release of publicatie."
        )
        proc = _subtree_merge(repo, client.prefix, new_commit, message)
        if proc.returncode != 0:
            summary["opgeloste_gitlinkconflicten"] = _resolve_nested_gitlink_conflicts(repo, client)

        for nested in client.nested:
            new_pin = upstream_links[nested.rel_path]
            if new_pin == nested.upstream_commit:
                continue
            n_url = nested_url_overrides.get(nested.rel_path, nested.upstream_repo)
            _fetch(repo, n_url, new_pin, nested.upstream_commit)
            n_msg = (f"Upstream-sync: geneste subtree {nested.full_prefix} → {new_pin[:12]}\n\n"
                     f"{client.key} {tag} pint submodule {nested.rel_path} op {new_pin}; bron {n_url} (ADR-0005).")
            n_proc = _subtree_merge(repo, nested.full_prefix, new_pin, n_msg)
            if n_proc.returncode != 0:
                raise SyncFailure(f"geneste subtree {nested.full_prefix} → {new_pin[:12]}: "
                                  f"{n_proc.stderr.strip() or n_proc.stdout.strip()}")
            data["clients"][client.key]["geneste_subtrees"][nested.rel_path]["upstream_commit"] = new_pin
            summary["geneste_updates"].append({"pad": nested.full_prefix, "van": nested.upstream_commit,
                                               "naar": new_pin})

        entry = data["clients"][client.key]
        entry["upstream_tag"] = tag
        entry["upstream_commit"] = new_commit
        entry["forkversie"] = fork_version_for(tag)
        (repo / BASELINE_REL).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        run_git(repo, "add", BASELINE_REL)
        run_git(repo, "commit", "--quiet", "-m",
                f"Upstream-sync: basislijn {client.key} → {tag}\n\nforkversie {entry['forkversie']}; "
                f"upstream-commit {new_commit}.")

        result = check_clients.check(repo, "HEAD")
        if result.violations:
            raise SyncFailure("forkregels geschonden na sync: " + "; ".join(result.violations))
    except (SyncFailure, ToolError) as exc:
        _rollback(repo, original, branch)
        raise SyncFailure(str(exc)) from exc


def _rollback(repo: Path, original: str, branch: str) -> None:
    git_dir = Path(git_out(repo, "rev-parse", "--absolute-git-dir"))
    if (git_dir / "MERGE_HEAD").exists():
        run_git(repo, "merge", "--abort", check=False)
    run_git(repo, "reset", "--quiet", "--hard", check=False)
    run_git(repo, "clean", "-fdq", check=False)
    run_git(repo, "checkout", "--quiet", original, check=False)
    run_git(repo, "branch", "-D", branch, check=False)


def _parse_overrides(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        key, sep, url = value.partition("=")
        if not sep:
            raise ToolError(f"ongeldige override '{value}', verwacht <sleutel>=<url>")
        result[key] = url
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_status = sub.add_parser("status", help="upstream-tags vergelijken met de basislijn")
    p_status.add_argument("--json", action="store_true")
    p_status.add_argument("--upstream-url", action="append", default=[], metavar="CLIENT=URL")
    p_sync = sub.add_parser("sync", help="één client synchroniseren in een syncbranch")
    p_sync.add_argument("client")
    p_sync.add_argument("--tag", help="upstream-tag (standaard: nieuwste stabiele)")
    p_sync.add_argument("--upstream-url", help="andere upstream-URL (tests/spiegel)")
    p_sync.add_argument("--geneste-url", action="append", default=[], metavar="PAD=URL",
                        help="andere URL voor een geneste subtree, bv. external/mpvqt=<url>")
    p_sync.add_argument("--branch-prefix", default="sync")
    p_sync.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    repo = args.repo_root.resolve()
    try:
        if args.cmd == "status":
            rows = status(repo, _parse_overrides(args.upstream_url))
            if args.json:
                print(json.dumps(rows, indent=2, ensure_ascii=False))
            else:
                for r in rows:
                    print(f"{r['client']:<10} basislijn {r['basislijn_tag']:<9} upstream {str(r['nieuwste_tag']):<9} "
                          f"→ {r['oordeel']}{(' (' + r['reden'] + ')') if r['reden'] else ''}")
            return 0
        summary = sync(repo, args.client, args.tag, args.upstream_url, _parse_overrides(args.geneste_url),
                       args.branch_prefix)
    except SyncFailure as exc:
        print(f"SYNC MISLUKT (niets gewijzigd): {exc}", file=sys.stderr)
        if getattr(args, "json", False):
            print(json.dumps({"resultaat": "mislukt", "reden": str(exc)}, ensure_ascii=False))
        return 2
    except ToolError as exc:
        print(f"FOUT: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    elif summary["resultaat"] == "actueel":
        print(f"{summary['client']}: al op {summary['naar_tag']} — niets te doen.")
    else:
        print(f"{summary['client']}: {summary['van_tag']} → {summary['naar_tag']} in branch {summary['branch']}")
        for upd in summary["geneste_updates"]:
            print(f"  geneste subtree {upd['pad']}: {upd['van'][:12]} → {upd['naar'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
