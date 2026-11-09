"""Tests voor upstream_sync.py: subtree-squash-sync per client in sync/<client>-<tag> (ADR-0002, EX48).

Alles draait tegen lokale nep-upstreams (Sim-getest); er wordt nooit gepusht.
"""

from __future__ import annotations

import json
from pathlib import Path

import check_clients
import pytest
import upstream_sync
from clients_common import ToolError
from conftest import Fork, git, patch_block, write_files


def baseline(fork: Fork) -> dict:
    return json.loads((fork.path / "tools/clients/baseline.json").read_text(encoding="utf-8"))


def assert_unchanged(fork: Fork, head_before: str) -> None:
    assert fork.branch() == "main"
    assert fork.head() == head_before
    assert fork.status() == ""
    assert not [b for b in fork.branches() if b.startswith("sync/")]
    assert git(fork.path, "for-each-ref", "refs/jlc-sync") == ""


# ---------------------------------------------------------------------------------------------- status


def test_status_actueel_en_update_beschikbaar(simple_setup):
    up, fork = simple_setup
    rows = upstream_sync.status(fork.path)
    assert rows[0]["oordeel"] == "actueel"
    up.commit({"README.md": "app 1.1\n"}, "v1.1", tag="v1.1.0")
    up.commit({"README.md": "rc\n"}, "rc", tag="v1.2.0-rc1")  # pre-release telt niet
    rows = upstream_sync.status(fork.path)
    assert rows[0]["oordeel"] == "update_beschikbaar"
    assert rows[0]["nieuwste_tag"] == "v1.1.0"


def test_status_onbereikbare_upstream_is_unknown_nooit_actueel(simple_setup, tmp_path):
    _up, fork = simple_setup
    rows = upstream_sync.status(fork.path, {"app": str(tmp_path / "bestaat-niet")})
    assert rows[0]["oordeel"] == "unknown"
    assert rows[0]["nieuwste_tag"] is None


# ---------------------------------------------------------------------------------------------- sync


def test_sync_schone_update_behoudt_patch(simple_setup):
    up, fork = simple_setup
    write_files(fork.path, {"app/src/main.txt": "regel 1\nregel 2 (Jelly Leon)\nregel 3\n"})
    fork.write_register(patch_block("JLC-0001", "app", ["app/src/main.txt"]))
    fork.commit_all("patch")
    new = up.commit({"README.md": "app 1.1\n", "src/nieuw.txt": "nieuw\n"}, "v1.1", tag="v1.1.0")

    summary = upstream_sync.sync(fork.path, "app")

    assert summary["resultaat"] == "gesynchroniseerd"
    assert summary["branch"] == "sync/app-v1.1.0"
    assert fork.branch() == "sync/app-v1.1.0"
    assert "main" in fork.branches()
    assert (fork.path / "app/src/nieuw.txt").read_text() == "nieuw\n"
    assert "Jelly Leon" in (fork.path / "app/src/main.txt").read_text()
    data = baseline(fork)["clients"]["app"]
    assert (data["upstream_tag"], data["upstream_commit"], data["forkversie"]) == ("v1.1.0", new, "1.1.0-jl.0")
    assert check_clients.check(fork.path).violations == []
    assert fork.status() == ""
    assert git(fork.path, "for-each-ref", "refs/jlc-sync") == ""


def test_sync_incompatibele_upstream_faalt_schoon_ex48(simple_setup):
    """EX48: upstream wijzigt dezelfde regel als onze patch → sync faalt, niets gewijzigd, geen deploy."""
    up, fork = simple_setup
    write_files(fork.path, {"app/src/main.txt": "regel 1\nregel 2 (Jelly Leon)\nregel 3\n"})
    fork.write_register(patch_block("JLC-0001", "app", ["app/src/main.txt"]))
    head_before = fork.commit_all("patch")
    up.commit({"src/main.txt": "regel 1\nregel 2 (upstream herschreven)\nregel 3\n"}, "v1.1", tag="v1.1.0")

    with pytest.raises(upstream_sync.SyncFailure, match="mergeconflict"):
        upstream_sync.sync(fork.path, "app")
    assert_unchanged(fork, head_before)
    assert baseline(fork)["clients"]["app"]["upstream_tag"] == "v1.0.0"


def test_sync_faalt_als_upstream_onze_patch_overnam_register_verouderd(simple_setup):
    """Upstream nam exact onze wijziging over: merge is schoon, maar het register is dan verouderd → falen."""
    up, fork = simple_setup
    patched = "regel 1\nregel 2 (Jelly Leon)\nregel 3\n"
    write_files(fork.path, {"app/src/main.txt": patched})
    fork.write_register(patch_block("JLC-0001", "app", ["app/src/main.txt"]))
    head_before = fork.commit_all("patch")
    up.commit({"src/main.txt": patched}, "v1.1 neemt patch over", tag="v1.1.0")

    with pytest.raises(upstream_sync.SyncFailure, match="forkregels geschonden"):
        upstream_sync.sync(fork.path, "app")
    assert_unchanged(fork, head_before)


def test_sync_al_actueel_doet_niets(simple_setup):
    _up, fork = simple_setup
    head_before = fork.head()
    summary = upstream_sync.sync(fork.path, "app")
    assert summary["resultaat"] == "actueel"
    assert_unchanged(fork, head_before)


def test_sync_weigert_vuile_werkboom(simple_setup):
    up, fork = simple_setup
    up.commit({"README.md": "1.1\n"}, "v1.1", tag="v1.1.0")
    write_files(fork.path, {"README.md": "lokaal gewijzigd\n"})
    with pytest.raises(ToolError, match="werkboom is niet schoon"):
        upstream_sync.sync(fork.path, "app")


def test_sync_weigert_oudere_tag_en_onbekende_tag(simple_setup):
    up, fork = simple_setup
    git(up.path, "tag", "-a", "v0.9.0", "-m", "oud", "HEAD")
    with pytest.raises(ToolError, match="ouder dan de basislijn"):
        upstream_sync.sync(fork.path, "app", tag="v0.9.0")
    with pytest.raises(ToolError, match="bestaat niet"):
        upstream_sync.sync(fork.path, "app", tag="v7.7.7")


def test_sync_weigert_bestaande_syncbranch(simple_setup):
    up, fork = simple_setup
    up.commit({"README.md": "1.1\n"}, "v1.1", tag="v1.1.0")
    git(fork.path, "branch", "sync/app-v1.1.0")
    with pytest.raises(ToolError, match="bestaat al"):
        upstream_sync.sync(fork.path, "app")


def test_sync_in_verse_clone_zonder_upstream_historie(simple_setup, tmp_path):
    """Zoals in CI: een verse clone bevat de vorige upstream-commit niet; de tool haalt die zelf op."""
    up, fork = simple_setup
    up.commit({"README.md": "1.1\n"}, "v1.1", tag="v1.1.0")
    clone = tmp_path / "ci-clone"
    git(tmp_path, "clone", "-q", "--no-local", f"file://{fork.path}", str(clone))
    old = baseline(fork)["clients"]["app"]["upstream_commit"]
    probe = upstream_sync.run_git(clone, "cat-file", "-e", f"{old}^{{commit}}", check=False)
    assert probe.returncode != 0, "verse clone hoort de upstream-commit niet te bevatten"

    summary = upstream_sync.sync(clone, "app")
    assert summary["resultaat"] == "gesynchroniseerd"
    assert check_clients.check(clone).violations == []


# ------------------------------------------------------------------------------- geneste subtrees


def _register_vendoring(fork: Fork) -> str:
    fork.write_register(patch_block("JLC-0001", "desk", ["desk/external/dep"]))
    return fork.commit_all("vendoring geregistreerd")


def test_sync_geneste_pin_ongewijzigd(nested_setup):
    up, _dep, fork, n1, _n2 = nested_setup
    _register_vendoring(fork)
    up.commit({"main.cpp": "int main(){return 0;}\n"}, "v1.1", tag="v1.1.0", gitlinks={"external/dep": n1})

    summary = upstream_sync.sync(fork.path, "desk")
    assert summary["geneste_updates"] == []
    assert summary["opgeloste_gitlinkconflicten"] == []
    assert (fork.path / "desk/external/dep/dep.txt").read_text() == "dep 1\n"
    assert check_clients.check(fork.path).violations == []


def test_sync_geneste_pin_gewijzigd_volgt_upstream(nested_setup):
    up, _dep, fork, n1, n2 = nested_setup
    _register_vendoring(fork)
    up.commit({"main.cpp": "int main(){return 1;}\n"}, "v2", tag="v2.0.0", gitlinks={"external/dep": n2})

    summary = upstream_sync.sync(fork.path, "desk")
    assert summary["resultaat"] == "gesynchroniseerd"
    assert summary["opgeloste_gitlinkconflicten"], "het gitlink-conflict hoort opgelost te zijn"
    assert summary["geneste_updates"] == [{"pad": "desk/external/dep", "van": n1, "naar": n2}]
    assert (fork.path / "desk/external/dep/dep.txt").read_text() == "dep 2\n"
    assert (fork.path / "desk/main.cpp").read_text() == "int main(){return 1;}\n"
    assert baseline(fork)["clients"]["desk"]["geneste_subtrees"]["external/dep"]["upstream_commit"] == n2
    assert git(fork.path, "ls-files", "-s", "desk/external").count("160000") == 0
    assert check_clients.check(fork.path).violations == []
    assert fork.status() == ""


def test_sync_nieuwe_submodule_faalt_bewust(nested_setup, make_upstream):
    up, _dep, fork, n1, _n2 = nested_setup
    head_before = _register_vendoring(fork)
    other = make_upstream("ander")
    o1 = other.commit({"x.txt": "x\n"}, "x")
    write_files(up.path, {".gitmodules": '[submodule "external/ander"]\n\tpath = external/ander\n'
                                         '\turl = https://example.invalid/ander.git\n'})
    up.commit({}, "nieuwe submodule", tag="v1.1.0", gitlinks={"external/dep": n1, "external/ander": o1})

    with pytest.raises(upstream_sync.SyncFailure, match="nieuwe submodule.*external/ander.*example.invalid"):
        upstream_sync.sync(fork.path, "desk")
    assert_unchanged(fork, head_before)


def test_sync_verdwenen_submodule_faalt_bewust(nested_setup):
    up, _dep, fork, _n1, _n2 = nested_setup
    head_before = _register_vendoring(fork)
    git(up.path, "rm", "-q", "--cached", "external/dep")
    up.commit({}, "submodule weg", tag="v1.1.0")

    with pytest.raises(upstream_sync.SyncFailure, match="niet meer"):
        upstream_sync.sync(fork.path, "desk")
    assert_unchanged(fork, head_before)


# ---------------------------------------------------------------------------------------------- CLI


def test_cli_exitcodes(simple_setup, capsys):
    up, fork = simple_setup
    root = ["--repo-root", str(fork.path)]
    assert upstream_sync.main([*root, "status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["oordeel"] == "actueel"
    assert upstream_sync.main([*root, "sync", "app"]) == 0  # actueel
    assert upstream_sync.main([*root, "sync", "bestaatniet"]) == 3

    write_files(fork.path, {"app/src/main.txt": "regel 1\nJL\nregel 3\n"})
    fork.write_register(patch_block("JLC-0001", "app", ["app/src/main.txt"]))
    fork.commit_all("patch")
    up.commit({"src/main.txt": "regel 1\nUPSTREAM\nregel 3\n"}, "v1.1", tag="v1.1.0")
    assert upstream_sync.main([*root, "sync", "app", "--json"]) == 2
    assert "SYNC MISLUKT" in capsys.readouterr().err


def test_echte_basislijn_tagpatronen_kiezen_huidige_tag():
    """De tagpatronen in de echte basislijn herkennen de vastgelegde tags zelf als stabiel."""
    from clients_common import DEFAULT_REPO_ROOT, load_clients, version_key  # noqa: PLC0415

    for client in load_clients(Path(DEFAULT_REPO_ROOT)):
        assert version_key(client.upstream_tag, client.tag_pattern) is not None, client.key
