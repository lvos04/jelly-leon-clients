#!/usr/bin/env python3
"""Forkregels voor jelly-leon-clients: basislijn, subtree-integriteit en patchregister (ADR-0001/0003/0005).

Controleert de opgegeven commit (standaard HEAD), met de basislijn en het patchregister uit diezelfde commit
(ontbreken die in de commit, dan die uit de werkboom — dat staat dan in het rapport):
  1. geen `.gitmodules` in de root en geen gitlinks (mode 160000) in de boom — git subtree neemt
     submodule-inhoud niet mee, een gitlink betekent dus ontbrekende broncode;
  2. per client: de jongste squashcommit voor de prefix (`git-subtree-dir`) verwijst naar exact de
     upstream-commit uit tools/clients/baseline.json, de inhoud (tree-hash) van die squashcommit is exact
     `upstream_tree` uit de basislijn, en de forkversie past bij de upstream-tag;
  3. per geneste subtree (vervangen submodule): upstream pint op die plek een gitlink met exact de commit
     uit de basislijn, en de geneste squashcommit verwijst naar diezelfde commit en inhoud;
  4. elke afwijking van upstream binnen een clientmap (gewijzigd, toegevoegd of verwijderd bestand, ook een
     vervangen gitlink) staat bij een actieve patch in docs/platform-v2/PATCHES.md;
  5. elk bestand bij een actieve patch wijkt ook echt af (anders is het register verouderd);
  6. beschermde bestanden (licenties, credits) bestaan en wijken nooit af, ook niet met registratie.

Exitcodes: 0 = in orde, 1 = overtreding, 3 = gebruiks-/omgevingsfout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from clients_common import (  # noqa: E402
    BASELINE_REL,
    DEFAULT_REPO_ROOT,
    GITLINK_MODE,
    PATCHES_REL,
    Client,
    ToolError,
    find_squash_commit,
    parse_baseline_text,
    parse_clients,
    read_text_at,
    run_git,
)

ACTIVE_STATUSES = {"actief", "upstream-aangeboden"}
KNOWN_STATUSES = ACTIVE_STATUSES | {"vervallen"}
REQUIRED_FIELDS = ("Status", "Client", "Doel", "Bestanden", "Waarom nodig", "Upstream-PR-kans", "Test")
PATCH_HEADING_RE = re.compile(r"^##\s+(JLC-\d{4})\b\s*[—-]?\s*(.*)$")
ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$")
BACKTICK_RE = re.compile(r"`([^`]+)`")


@dataclass
class Patch:
    patch_id: str
    title: str
    fields: dict[str, str] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.fields.get("Status", "").strip().lower()

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES


def parse_register(text: str) -> list[Patch]:
    patches: list[Patch] = []
    current: Patch | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        heading = PATCH_HEADING_RE.match(line)
        if heading:
            current = Patch(heading.group(1), heading.group(2).strip())
            patches.append(current)
            continue
        if line.startswith("## "):
            current = None
            continue
        if current is None:
            continue
        row = ROW_RE.match(line)
        if not row:
            continue
        key, value = row.group(1).strip(), row.group(2).strip()
        if key in {"Veld", "---"} or set(key) <= {"-", " "}:
            continue
        current.fields[key] = value
        if key == "Bestanden":
            current.files = [f.strip() for f in BACKTICK_RE.findall(value)]
    return patches


def covers(entry: str, path: str) -> bool:
    """Een registerregel dekt een pad exact, of als map wanneer de regel op '/' eindigt."""
    if entry.endswith("/"):
        return path.startswith(entry)
    return path == entry


def tree_exists(repo: Path, spec: str) -> bool:
    proc = run_git(repo, "cat-file", "-t", spec, check=False)
    return proc.returncode == 0 and proc.stdout.strip() == "tree"


def diff_paths(repo: Path, base_tree: str, head_tree: str) -> dict[str, str]:
    out = run_git(repo, "diff", "--no-renames", "--name-status", "-z", base_tree, head_tree).stdout
    parts = [p for p in out.split("\0") if p]
    result: dict[str, str] = {}
    for i in range(0, len(parts) - 1, 2):
        result[parts[i + 1]] = parts[i]
    return result


def ls_tree_entry(repo: Path, treeish: str, path: str) -> tuple[str, str, str] | None:
    out = run_git(repo, "ls-tree", treeish, "--", path).stdout.strip()
    if not out:
        return None
    meta, _, _name = out.partition("\t")
    mode, typ, sha = meta.split()
    return mode, typ, sha


@dataclass
class Result:
    violations: list[str] = field(default_factory=list)
    changed: dict[str, str] = field(default_factory=dict)  # volledig pad -> status (M/A/D/T of 'gitlink→subtree')
    report: list[dict] = field(default_factory=list)
    bronnen: dict[str, str] = field(default_factory=dict)  # basislijn/register -> "<ref>" of "werkboom"


def check_tree(result: Result, label: str, squash_sha: str, expected_tree: str | None, actual_tree: str) -> None:
    """De squashcommit moet exact de upstream-inhoud bevatten; de trailer alleen is geen bewijs."""
    if not expected_tree:
        result.violations.append(f"{label}: basislijn mist 'upstream_tree' (tree-hash van de upstream-commit)")
    elif actual_tree != expected_tree:
        result.violations.append(
            f"{label}: squashcommit {squash_sha[:10]} heeft inhoud {actual_tree[:10]}, upstream-tree volgens "
            f"basislijn is {expected_tree[:10]} — squashcommit bevat niet exact de upstream-boom")


def protected_exists(repo: Path, ref: str, full: str) -> bool:
    entry = ls_tree_entry(repo, ref, full)
    return entry is not None and entry[1] == "blob"


def check_client(repo: Path, ref: str, client: Client, result: Result) -> None:
    info = {"client": client.key, "prefix": client.prefix, "upstream_tag": client.upstream_tag,
            "upstream_commit": client.upstream_commit, "afwijkingen": 0, "geneste_subtrees": []}
    result.report.append(info)

    if not tree_exists(repo, f"{ref}:{client.prefix}"):
        result.violations.append(f"{client.key}: map '{client.prefix}/' ontbreekt in {ref}")
        return

    expected_prefix = client.upstream_tag.lstrip("v") + "-jl."
    if not client.fork_version.startswith(expected_prefix):
        result.violations.append(
            f"{client.key}: forkversie '{client.fork_version}' past niet bij upstream-tag '{client.upstream_tag}'"
            f" (verwacht '{expected_prefix}<N>')")

    squash = find_squash_commit(repo, client.prefix, ref)
    if squash is None:
        result.violations.append(f"{client.key}: geen subtree-squashcommit gevonden voor prefix '{client.prefix}'")
        return
    squash_sha, split = squash
    info["squash_commit"] = squash_sha
    if split != client.upstream_commit:
        result.violations.append(
            f"{client.key}: jongste squashcommit {squash_sha[:10]} verwijst naar upstream {split[:10]}, "
            f"basislijn zegt {client.upstream_commit[:10]} ({client.upstream_tag})")
    check_tree(result, client.key, squash_sha, client.upstream_tree,
               run_git(repo, "rev-parse", f"{squash_sha}^{{tree}}").stdout.strip())

    changed = diff_paths(repo, f"{squash_sha}^{{tree}}", f"{ref}:{client.prefix}")

    for nested in client.nested:
        n_info = {"pad": nested.full_prefix, "upstream_commit": nested.upstream_commit}
        info["geneste_subtrees"].append(n_info)
        entry = ls_tree_entry(repo, squash_sha, nested.rel_path)
        if entry is None or entry[0] != GITLINK_MODE:
            result.violations.append(
                f"{client.key}: upstream heeft op '{nested.rel_path}' geen submodule (meer); "
                f"geneste subtree '{nested.full_prefix}' heroverwegen")
        elif entry[2] != nested.upstream_commit:
            result.violations.append(
                f"{client.key}: upstream pint '{nested.rel_path}' op {entry[2][:10]}, geneste subtree in basislijn "
                f"staat op {nested.upstream_commit[:10]}")
        # De gitlink zelf is vervangen door een map: dat is een (te registreren) afwijking.
        for path in list(changed):
            if path == nested.rel_path or path.startswith(nested.rel_path + "/"):
                del changed[path]
        result.changed[nested.full_prefix] = "gitlink→subtree"

        n_squash = find_squash_commit(repo, nested.full_prefix, ref)
        if n_squash is None:
            result.violations.append(f"{client.key}: geen squashcommit voor geneste subtree '{nested.full_prefix}'")
            continue
        n_sha, n_split = n_squash
        n_info["squash_commit"] = n_sha
        if n_split != nested.upstream_commit:
            result.violations.append(
                f"{client.key}: geneste squashcommit {n_sha[:10]} verwijst naar {n_split[:10]}, basislijn zegt "
                f"{nested.upstream_commit[:10]}")
        check_tree(result, f"{client.key} ({nested.full_prefix})", n_sha, nested.upstream_tree,
                   run_git(repo, "rev-parse", f"{n_sha}^{{tree}}").stdout.strip())
        if not tree_exists(repo, f"{ref}:{nested.full_prefix}"):
            result.violations.append(f"{client.key}: geneste subtree '{nested.full_prefix}/' ontbreekt")
            continue
        for path, status in diff_paths(repo, f"{n_sha}^{{tree}}", f"{ref}:{nested.full_prefix}").items():
            result.changed[f"{nested.full_prefix}/{path}"] = status
        for protected in nested.protected_files:
            full = f"{nested.full_prefix}/{protected}"
            if full in result.changed:
                result.violations.append(
                    f"{client.key}: beschermd bestand '{full}' wijkt af van upstream")
            elif not protected_exists(repo, ref, full):
                result.violations.append(
                    f"{client.key}: beschermd bestand '{full}' ontbreekt (ook upstream?) — handmatig beoordelen "
                    "en basislijn bijwerken")

    for path, status in changed.items():
        result.changed[f"{client.prefix}/{path}"] = status
    for protected in client.protected_files:
        full = f"{client.prefix}/{protected}"
        if full in result.changed:
            result.violations.append(
                f"{client.key}: beschermd bestand '{full}' wijkt af van upstream (nooit toegestaan)")
        elif not protected_exists(repo, ref, full):
            # Upstream hernoemde of verwijderde een licentie-/creditbestand: de bescherming zou stil vervallen.
            result.violations.append(
                f"{client.key}: beschermd bestand '{full}' ontbreekt (ook upstream?) — handmatig beoordelen en "
                "basislijn bijwerken")

    info["afwijkingen"] = sum(1 for p in result.changed if p == client.prefix or p.startswith(client.prefix + "/"))


def _text_at_ref_or_worktree(repo: Path, ref: str, rel: str, result: Result, key: str) -> str | None:
    text = read_text_at(repo, ref, rel)
    if text is not None:
        result.bronnen[key] = ref
        return text
    text = read_text_at(repo, None, rel)
    if text is not None:
        result.bronnen[key] = "werkboom"
    return text


def check(repo: Path, ref: str = "HEAD") -> Result:
    result = Result()
    if run_git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False).returncode != 0:
        raise ToolError(f"ref '{ref}' is geen commit")
    baseline_text = _text_at_ref_or_worktree(repo, ref, BASELINE_REL, result, "basislijn")
    if baseline_text is None:
        raise ToolError(f"basislijn ontbreekt: {BASELINE_REL} (in {ref} en in de werkboom)")
    clients = parse_clients(parse_baseline_text(baseline_text, result.bronnen["basislijn"]))

    if ls_tree_entry(repo, ref, ".gitmodules") is not None:
        result.violations.append(".gitmodules in de root: submodules zijn niet toegestaan (ADR-0005)")
    tree = run_git(repo, "ls-tree", "-r", "-z", ref).stdout
    for record in tree.split("\0"):
        if record.startswith(GITLINK_MODE + " "):
            result.violations.append(
                f"gitlink (submodule zonder inhoud) gevonden: '{record.partition(chr(9))[2]}' — "
                "als geneste subtree toevoegen (ADR-0005)")

    known_keys = {c.key for c in clients}
    for client in clients:
        check_client(repo, ref, client, result)

    register_text = _text_at_ref_or_worktree(repo, ref, PATCHES_REL, result, "patchregister")
    if register_text is None:
        result.violations.append(f"patchregister ontbreekt: {PATCHES_REL}")
        return result
    patches = parse_register(register_text)
    seen: set[str] = set()
    for patch in patches:
        if patch.patch_id in seen:
            result.violations.append(f"{patch.patch_id}: dubbel in het register")
        seen.add(patch.patch_id)
        missing = [f for f in REQUIRED_FIELDS if not patch.fields.get(f)]
        if missing:
            result.violations.append(f"{patch.patch_id}: verplichte velden ontbreken: {', '.join(missing)}")
        if patch.status not in KNOWN_STATUSES:
            result.violations.append(f"{patch.patch_id}: onbekende status '{patch.status}'")
        client_key = patch.fields.get("Client", "").strip().strip("`")
        if client_key and client_key not in known_keys:
            result.violations.append(f"{patch.patch_id}: onbekende client '{client_key}'")
        if patch.active and not patch.files:
            result.violations.append(f"{patch.patch_id}: geen bestanden (tussen backticks) bij 'Bestanden'")

    active = [p for p in patches if p.active]
    for path, status in sorted(result.changed.items()):
        if not any(covers(entry, path) for p in active for entry in p.files):
            result.violations.append(f"niet-geregistreerde afwijking van upstream ({status}): {path}")
    for patch in active:
        for entry in patch.files:
            if not any(covers(entry, path) for path in result.changed):
                result.violations.append(
                    f"{patch.patch_id}: '{entry}' wijkt niet (meer) af van upstream — register bijwerken")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--json", action="store_true", help="rapport als JSON")
    args = parser.parse_args(argv)
    try:
        result = check(args.repo_root.resolve(), args.ref)
    except ToolError as exc:
        print(f"FOUT: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps({"in_orde": not result.violations, "ref": args.ref, "bronnen": result.bronnen,
                          "overtredingen": result.violations, "afwijkingen": result.changed,
                          "clients": result.report}, indent=2, ensure_ascii=False))
    else:
        for key, bron in sorted(result.bronnen.items()):
            if bron == "werkboom":
                print(f"LET OP: {key} ontbreekt in {args.ref}; die uit de werkboom is gebruikt.")
        for info in result.report:
            print(f"{info['client']:<10} {info['upstream_tag']:<9} {info['upstream_commit'][:10]}  "
                  f"afwijkingen van upstream: {info['afwijkingen']}")
        if result.violations:
            print(f"\n{len(result.violations)} overtreding(en):")
            for v in result.violations:
                print(f"  - {v}")
        else:
            print("\nForkregels in orde: basislijn, subtrees en patchregister kloppen.")
    return 1 if result.violations else 0


if __name__ == "__main__":
    sys.exit(main())
