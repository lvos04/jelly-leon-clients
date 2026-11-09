"""Tests voor check_clients.py (forkregels, patchregister, geneste subtrees)."""

from __future__ import annotations

import json

import check_clients
import pytest
from clients_common import DEFAULT_REPO_ROOT, find_squash_commit, newest_tag, version_key
from conftest import Fork, git, patch_block, write_files


def test_echte_repo_voldoet_aan_forkregels():
    """De echte repo (deze checkout, met volledige historie) voldoet aan de forkregels."""
    result = check_clients.check(DEFAULT_REPO_ROOT)
    assert result.violations == []
    keys = {r["client"] for r in result.report}
    assert keys == {"android", "androidtv", "desktop", "swiftfin"}
    assert result.changed == {"desktop/external/mpvqt": "gitlink→subtree"}


def test_schone_fork_in_orde(simple_setup):
    _up, fork = simple_setup
    result = check_clients.check(fork.path)
    assert result.violations == []
    assert result.changed == {}


def test_niet_geregistreerde_wijziging_faalt(simple_setup):
    _up, fork = simple_setup
    write_files(fork.path, {"app/src/main.txt": "regel 1\nJELLY LEON\nregel 3\n"})
    fork.commit_all("ongeregistreerde patch")
    result = check_clients.check(fork.path)
    assert any("niet-geregistreerde afwijking" in v and "app/src/main.txt" in v for v in result.violations)


def test_toegevoegd_en_verwijderd_bestand_tellen_als_afwijking(simple_setup):
    _up, fork = simple_setup
    write_files(fork.path, {"app/extra.txt": "nieuw\n", "app/README.md": None})
    fork.commit_all("toevoegen en verwijderen")
    result = check_clients.check(fork.path)
    assert result.changed == {"app/extra.txt": "A", "app/README.md": "D"}
    assert len([v for v in result.violations if "niet-geregistreerde" in v]) == 2


def test_geregistreerde_wijziging_in_orde(simple_setup):
    _up, fork = simple_setup
    write_files(fork.path, {"app/src/main.txt": "regel 1\nJELLY LEON\nregel 3\n"})
    fork.write_register(patch_block("JLC-0001", "app", ["app/src/main.txt"]))
    fork.commit_all("geregistreerde patch")
    assert check_clients.check(fork.path).violations == []


def test_map_dekking_alleen_met_slash(simple_setup):
    _up, fork = simple_setup
    write_files(fork.path, {"app/src/main.txt": "anders\n"})
    fork.write_register(patch_block("JLC-0001", "app", ["app/src"]))
    fork.commit_all("register zonder slash")
    assert any("niet-geregistreerde" in v for v in check_clients.check(fork.path).violations)
    fork.write_register(patch_block("JLC-0001", "app", ["app/src/"]))
    fork.commit_all("register met slash")
    assert check_clients.check(fork.path).violations == []


def test_verouderd_register_faalt(simple_setup):
    _up, fork = simple_setup
    fork.write_register(patch_block("JLC-0001", "app", ["app/src/main.txt"]))
    fork.commit_all("register zonder echte afwijking")
    result = check_clients.check(fork.path)
    assert any("JLC-0001" in v and "wijkt niet (meer) af" in v for v in result.violations)


def test_vervallen_patch_telt_niet_mee(simple_setup):
    _up, fork = simple_setup
    fork.write_register(patch_block("JLC-0001", "app", ["app/src/main.txt"], status="vervallen"))
    fork.commit_all("vervallen patch")
    assert check_clients.check(fork.path).violations == []


def test_beschermd_bestand_faalt_ook_met_registratie(simple_setup):
    _up, fork = simple_setup
    write_files(fork.path, {"app/LICENSE": "iets anders\n"})
    fork.write_register(patch_block("JLC-0001", "app", ["app/LICENSE"]))
    fork.commit_all("licentie gewijzigd")
    result = check_clients.check(fork.path)
    assert any("beschermd bestand 'app/LICENSE'" in v for v in result.violations)


@pytest.mark.parametrize("veld", ["Test", "Waarom nodig", "Client"])
def test_verplichte_velden(simple_setup, veld):
    _up, fork = simple_setup
    write_files(fork.path, {"app/src/main.txt": "anders\n"})
    fork.write_register(patch_block("JLC-0001", "app", ["app/src/main.txt"], drop_field=veld))
    fork.commit_all("onvolledige patch")
    result = check_clients.check(fork.path)
    assert any("verplichte velden ontbreken" in v and veld in v for v in result.violations)


def test_onbekende_client_en_status(simple_setup):
    _up, fork = simple_setup
    fork.write_register(patch_block("JLC-0001", "bestaatniet", ["app/x"], status="misschien"))
    fork.commit_all("onzin")
    violations = check_clients.check(fork.path).violations
    assert any("onbekende client" in v for v in violations)
    assert any("onbekende status" in v for v in violations)


def test_basislijn_wijkt_af_van_squashcommit(simple_setup):
    up, fork = simple_setup
    data = fork.baseline_data()
    data["clients"]["app"]["upstream_commit"] = "0" * 40
    fork.write_baseline(data)
    fork.commit_all("verkeerde basislijn")
    result = check_clients.check(fork.path)
    assert any("basislijn zegt 0000000000" in v for v in result.violations)


def test_forkversie_moet_bij_tag_passen(simple_setup):
    _up, fork = simple_setup
    data = fork.baseline_data()
    data["clients"]["app"]["forkversie"] = "9.9.9-jl.0"
    fork.write_baseline(data)
    fork.commit_all("verkeerde forkversie")
    assert any("forkversie" in v for v in check_clients.check(fork.path).violations)


def test_gitlink_in_boom_faalt(tmp_path, make_upstream):
    dep = make_upstream("dep")
    n1 = dep.commit({"dep.txt": "1\n"}, "dep")
    up = make_upstream("desk")
    up.commit({"LICENSE": "GPL\n"}, "v1", tag="v1.0.0", gitlinks={"external/dep": n1})
    from conftest import ClientSpec  # noqa: PLC0415

    fork = Fork(tmp_path / "fork", [ClientSpec("desk", up, "v1.0.0")])  # gitlink niet vervangen
    result = check_clients.check(fork.path)
    assert any("gitlink (submodule zonder inhoud)" in v and "desk/external/dep" in v for v in result.violations)


def test_root_gitmodules_faalt(simple_setup):
    _up, fork = simple_setup
    write_files(fork.path, {".gitmodules": "[submodule \"x\"]\n"})
    fork.commit_all("submodule in root")
    assert any(".gitmodules" in v for v in check_clients.check(fork.path).violations)


def test_geneste_subtree_moet_register_hebben(nested_setup):
    _up, _dep, fork, _n1, _n2 = nested_setup
    result = check_clients.check(fork.path)
    assert result.changed == {"desk/external/dep": "gitlink→subtree"}
    expected = "niet-geregistreerde afwijking van upstream (gitlink→subtree): desk/external/dep"
    assert any(expected in v for v in result.violations)
    fork.write_register(patch_block("JLC-0001", "desk", ["desk/external/dep"]))
    fork.commit_all("vendoring geregistreerd")
    assert check_clients.check(fork.path).violations == []


def test_geneste_subtree_pin_moet_gelijk_zijn_aan_upstream(nested_setup):
    _up, _dep, fork, _n1, n2 = nested_setup
    fork.write_register(patch_block("JLC-0001", "desk", ["desk/external/dep"]))
    data = fork.baseline_data()
    data["clients"]["desk"]["geneste_subtrees"]["external/dep"]["upstream_commit"] = n2
    fork.write_baseline(data)
    fork.commit_all("verkeerde geneste pin")
    violations = check_clients.check(fork.path).violations
    assert any("upstream pint 'external/dep'" in v for v in violations)


def test_wijziging_binnen_geneste_subtree_niet_gedekt_door_vendoring(nested_setup):
    _up, _dep, fork, _n1, _n2 = nested_setup
    write_files(fork.path, {"desk/external/dep/dep.txt": "gepatcht\n"})
    fork.write_register(patch_block("JLC-0001", "desk", ["desk/external/dep"]))
    fork.commit_all("patch in vendored code")
    violations = check_clients.check(fork.path).violations
    assert any("niet-geregistreerde afwijking van upstream (M): desk/external/dep/dep.txt" in v for v in violations)


def test_find_squash_commit_exacte_prefix(nested_setup):
    _up, _dep, fork, n1, _n2 = nested_setup
    outer = find_squash_commit(fork.path, "desk")
    inner = find_squash_commit(fork.path, "desk/external/dep")
    assert outer and inner and outer[0] != inner[0]
    assert inner[1] == n1


def test_versiesortering_en_tagfilter():
    pattern = r"^v(\d+)\.(\d+)\.(\d+)$"
    assert newest_tag(["v2.7.3", "v2.10.0", "v2.9.9", "v3.0.0-rc1", "nightly"], pattern) == "v2.10.0"
    swift = r"^(\d+)\.(\d+)(?:\.(\d+))?$"
    assert newest_tag(["1.6", "1.6.1", "v76", "v1.1", "1.5"], swift) == "1.6.1"
    assert version_key("1.6", swift) == (1, 6, 0)


def test_cli_exitcodes(simple_setup, capsys):
    _up, fork = simple_setup
    assert check_clients.main(["--repo-root", str(fork.path)]) == 0
    write_files(fork.path, {"app/src/main.txt": "anders\n"})
    fork.commit_all("afwijking")
    capsys.readouterr()
    assert check_clients.main(["--repo-root", str(fork.path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["in_orde"] is False
    assert report["afwijkingen"] == {"app/src/main.txt": "M"}
    (fork.path / "tools/clients/baseline.json").unlink()
    fork.commit_all("basislijn weg")
    assert check_clients.main(["--repo-root", str(fork.path)]) == 3  # niet in de commit en niet in de werkboom
    assert check_clients.main(["--repo-root", str(fork.path), "--ref", "bestaat-niet"]) == 3


# ------------------------------------------------------------------ review P0: inhoud, bronnen, licenties


def _forge_squash(fork: Fork, prefix: str, split: str) -> None:
    """Een commit met kloppende subtree-trailers maar met gewijzigde inhoud, samengevoegd zoals git subtree doet."""
    message = (f"Squashed '{prefix}/' content from commit {split[:9]}\n\n"
               f"git-subtree-dir: {prefix}\ngit-subtree-split: {split}\n")
    forged = git(fork.path, "commit-tree", f"HEAD:{prefix}", "-m", message)
    merge = git(fork.path, "commit-tree", "HEAD^{tree}", "-p", "HEAD", "-p", forged, "-m", "Merge vervalst")
    git(fork.path, "reset", "-q", "--hard", merge)


def test_squashcommit_met_kloppende_trailer_maar_andere_inhoud_faalt(simple_setup):
    """Zonder tree-controle zou een patch verborgen kunnen worden in een 'squashcommit' met de juiste trailer."""
    _up, fork = simple_setup
    split = fork.baseline_data()["clients"]["app"]["upstream_commit"]
    write_files(fork.path, {"app/src/main.txt": "regel 1\nVERBORGEN PATCH\nregel 3\n"})
    fork.commit_all("ongeregistreerde patch")
    _forge_squash(fork, "app", split)
    squash = find_squash_commit(fork.path, "app")
    assert squash is not None and squash[1] == split, "de vervalste squashcommit hoort als basis gevonden te worden"
    result = check_clients.check(fork.path)
    assert result.changed == {}, "t.o.v. de vervalste basis lijkt er niets te zijn veranderd"
    assert any("bevat niet exact de upstream-boom" in v for v in result.violations), result.violations


def test_basislijn_zonder_upstream_tree_faalt(simple_setup):
    _up, fork = simple_setup
    data = fork.baseline_data()
    del data["clients"]["app"]["upstream_tree"]
    fork.write_baseline(data)
    fork.commit_all("basislijn zonder tree")
    assert any("mist 'upstream_tree'" in v for v in check_clients.check(fork.path).violations)


def test_geneste_squash_met_andere_inhoud_faalt(nested_setup):
    _up, _dep, fork, n1, _n2 = nested_setup
    fork.write_register(patch_block("JLC-0001", "desk", ["desk/external/dep"]))
    fork.commit_all("vendoring geregistreerd")
    assert check_clients.check(fork.path).violations == []
    write_files(fork.path, {"desk/external/dep/dep.txt": "stiekem anders\n"})
    fork.commit_all("wijziging in vendored code")
    _forge_squash(fork, "desk/external/dep", n1)
    violations = check_clients.check(fork.path).violations
    assert any("desk/external/dep" in v and "upstream-boom" in v for v in violations), violations


def test_beschermd_bestand_dat_ontbreekt_faalt(simple_setup):
    """Als upstream een licentiebestand hernoemt of weghaalt, mag de bescherming niet stil vervallen."""
    _up, fork = simple_setup
    data = fork.baseline_data()
    data["clients"]["app"]["beschermde_bestanden"] = ["LICENSE", "CONTRIBUTORS.md"]
    fork.write_baseline(data)
    fork.commit_all("basislijn noemt een niet-bestaand creditbestand")
    violations = check_clients.check(fork.path).violations
    assert any("'app/CONTRIBUTORS.md' ontbreekt" in v for v in violations), violations


def test_register_en_basislijn_komen_uit_de_gecontroleerde_commit(simple_setup):
    """Een niet-gecommitte registratie mag een niet-geregistreerde afwijking in de commit niet goedpraten."""
    _up, fork = simple_setup
    write_files(fork.path, {"app/src/main.txt": "anders\n"})
    bad = fork.commit_all("afwijking zonder registratie")
    fork.write_register(patch_block("JLC-0001", "app", ["app/src/main.txt"]))  # alleen in de werkboom
    result = check_clients.check(fork.path, bad)
    assert result.bronnen == {"basislijn": bad, "patchregister": bad}
    assert any("niet-geregistreerde afwijking" in v for v in result.violations)
    good = fork.commit_all("registratie gecommit")
    assert check_clients.check(fork.path, good).violations == []
    assert check_clients.check(fork.path, bad).violations, "oudere commit wordt met zijn eigen register gecontroleerd"


def test_ref_zonder_basislijn_valt_terug_op_werkboom_en_meldt_dat(simple_setup, capsys):
    _up, fork = simple_setup
    first = git(fork.path, "log", "--format=%H", "--grep", "^init$", "HEAD")  # vóór basislijn en subtrees
    result = check_clients.check(fork.path, first)
    assert result.bronnen["basislijn"] == "werkboom"
    assert result.violations, "de eerste commit (zonder clients) voldoet niet"
    assert check_clients.main(["--repo-root", str(fork.path), "--ref", first]) == 1
    assert "LET OP: basislijn ontbreekt in" in capsys.readouterr().out
