"""Veiligheidsregels voor de fork-eigen workflows (ADR-0002, ADR-0006): statisch, op de echte bestanden.

Deze tests bewijzen niets over een echte run op GitHub (die runs staan apart in EVIDENCE.json); ze bewaken wel dat de
workflows nooit stilletjes gaan publiceren, samenvoegen, force-pushen, geheimen gebruiken of onbeoordeelde
upstream-code met schrijfrechten of schrijfbare caches laten draaien.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from clients_common import DEFAULT_REPO_ROOT

WORKFLOW_DIR = Path(DEFAULT_REPO_ROOT) / ".github" / "workflows"
WORKFLOWS = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))
SHA_PIN_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?@[0-9a-f]{40}$")
CLIENT_WORKFLOWS = {"clients-android.yml", "clients-androidtv.yml", "clients-desktop.yml", "clients-swiftfin.yml"}
SYNC_ONE = "clients-upstream-sync-een.yml"
SYNC_ALL = "clients-upstream-sync.yml"
# Alleen deze jobs mogen schrijven, en alleen `contents` (een sync/<client>-<tag>-branch maken).
WRITE_ALLOWED = {(SYNC_ONE, "sync")} | {(SYNC_ALL, f"sync-{c}") for c in ("android", "androidtv", "desktop",
                                                                         "swiftfin")}
FORBIDDEN_COMMANDS = [
    (re.compile(r"\bgit\s+push\b[^\n]*(--force|--force-with-lease|\s-f\b|\s\+)"), "force-push"),
    (re.compile(r"\bgit\s+merge\b"), "samenvoegen"),
    (re.compile(r"\bgit\s+tag\b"), "tag maken"),
    (re.compile(r"\bgh\s+(release|pr|api)\b"), "release/PR/API via gh"),
    (re.compile(r"\bdocker\s+(push|login)\b"), "image publiceren"),
    (re.compile(r"\bfastlane\b"), "fastlane (upstream-publicatiepad)"),
    (re.compile(r"\bgradlew?\b[^\n]*\b(publish|bundleRelease|assembleRelease)\b"), "release-build/publicatie"),
]


def load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), path.name
    return data


def triggers(data: dict) -> dict:
    # PyYAML (YAML 1.1) leest de sleutel `on` als True.
    value = data.get("on", data.get(True))
    if isinstance(value, str):
        return {value: None}
    if isinstance(value, list):
        return dict.fromkeys(value)
    return value or {}


def steps(data: dict):
    for job_id, job in (data.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            yield job_id, job, step


def code_only(text: str) -> str:
    """Workflowtekst zonder commentaarregels (daar staat juist uitgelegd wat er níet gebeurt)."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def all_code() -> dict[str, str]:
    return {p.name: code_only(p.read_text(encoding="utf-8")) for p in WORKFLOWS}


def test_alleen_eigen_clients_workflows_in_de_root():
    names = {p.name for p in WORKFLOWS}
    assert names, "geen workflows gevonden"
    assert all(n.startswith("clients-") for n in names), names
    assert CLIENT_WORKFLOWS | {SYNC_ONE, SYNC_ALL, "clients-forkregels.yml"} == names


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_acties_op_commit_sha_gepind(path):
    data = load(path)
    for job_id, job in data["jobs"].items():
        if "uses" in job:  # herbruikbare workflow
            assert job["uses"].startswith("./.github/workflows/clients-"), (path.name, job_id, job["uses"])
            assert "secrets" not in job, f"{path.name}:{job_id} geeft geheimen door"
    for job_id, _job, step in steps(data):
        uses = step.get("uses")
        if uses:
            assert SHA_PIN_RE.match(uses), f"{path.name}:{job_id}: '{uses}' niet op een commit-SHA gepind"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_minimale_rechten_en_schrijven_alleen_in_de_syncjob(path):
    data = load(path)
    assert data.get("permissions") == {"contents": "read"}, f"{path.name}: workflowrechten niet minimaal"
    for job_id, job in data["jobs"].items():
        perms = job.get("permissions")
        if perms is None:
            continue
        assert isinstance(perms, dict), f"{path.name}:{job_id}: rechten als tekst ({perms!r})"
        writes = {k for k, v in perms.items() if v == "write"}
        if (path.name, job_id) in WRITE_ALLOWED:
            assert writes <= {"contents"}, f"{path.name}:{job_id}: meer dan contents: write ({writes})"
        else:
            assert not writes, f"{path.name}:{job_id}: schrijfrechten {writes} niet toegestaan"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_geen_geheimen_en_geen_gevaarlijke_triggers(path):
    text = path.read_text(encoding="utf-8")
    assert "secrets." not in text and "secrets:" not in text, f"{path.name} gebruikt geheimen"
    assert "pull_request_target" not in text, f"{path.name}: pull_request_target draait vreemde code met rechten"
    assert "workflow_run" not in triggers(load(path)), f"{path.name}: workflow_run-trigger"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_geen_publicatie_samenvoegen_of_force_push(path):
    code = code_only(path.read_text(encoding="utf-8"))
    for pattern, what in FORBIDDEN_COMMANDS:
        assert not pattern.search(code), f"{path.name}: verboden actie ({what})"


def test_alleen_de_syncstap_pusht_en_alleen_een_nieuwe_syncbranch():
    pushers = {name for name, code in all_code().items() if re.search(r"\bgit\b[^\n]*\bpush\b", code)}
    assert pushers == {SYNC_ONE}
    data = load(WORKFLOW_DIR / SYNC_ONE)
    push_steps = [s for _j, _job, s in steps(data) if re.search(r"\bgit\b[^\n]*\bpush\b", s.get("run") or "")]
    assert len(push_steps) == 1
    run = push_steps[0]["run"]
    assert 'case "$BRANCH" in sync/*)' in run, "branchnaam niet tot sync/* beperkt"
    assert 'push origin "HEAD:refs/heads/$BRANCH"' in run
    assert "ls-remote --exit-code --heads" in run, "bestaande syncbranch wordt niet eerst gecontroleerd"
    assert '[ "$rc" -eq 2 ]' in run, "push hoort alleen te gebeuren als de branch aantoonbaar niet bestaat"
    assert "github.token" in str(push_steps[0].get("env")), "token hoort alleen in de pushstap"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_checkout_zonder_opgeslagen_token(path):
    for job_id, _job, step in steps(load(path)):
        if str(step.get("uses", "")).startswith("actions/checkout@"):
            assert (step.get("with") or {}).get("persist-credentials") is False, (
                f"{path.name}:{job_id}: checkout bewaart het token in de git-config")


@pytest.mark.parametrize("name", sorted(CLIENT_WORKFLOWS | {"clients-forkregels.yml"}))
def test_clientworkflows_zijn_aanroepbaar_voor_een_syncbranch(name):
    data = load(WORKFLOW_DIR / name)
    call = triggers(data).get("workflow_call") or {}
    assert "ref" in (call.get("inputs") or {}), f"{name}: geen input 'ref'"
    checkouts = [s for _j, _job, s in steps(data) if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert checkouts and all((s.get("with") or {}).get("ref") == "${{ inputs.ref }}" for s in checkouts)


def test_onbeoordeelde_upstream_code_schrijft_geen_cache():
    """Syncbranch-builds draaien in de cache-scope van de aanroepende (standaard)branch: alleen lezen."""
    for name in ("clients-android.yml", "clients-androidtv.yml"):
        gradle = [s for _j, _job, s in steps(load(WORKFLOW_DIR / name))
                  if str(s.get("uses", "")).startswith("gradle/actions/setup-gradle@")]
        assert len(gradle) == 1, name
        assert "inputs.ref != ''" in str((gradle[0].get("with") or {}).get("cache-read-only")), name
    caches = [s for _j, _job, s in steps(load(WORKFLOW_DIR / "clients-swiftfin.yml"))
              if str(s.get("uses", "")).startswith("actions/cache")]
    schrijvend = [s for s in caches if str(s["uses"]).startswith("actions/cache@")]
    assert schrijvend and all(s.get("if") == "inputs.ref == ''" for s in schrijvend)
    for name in CLIENT_WORKFLOWS | {"clients-forkregels.yml", SYNC_ONE, SYNC_ALL}:
        for _j, _job, step in steps(load(WORKFLOW_DIR / name)):
            uses = str(step.get("uses", ""))
            if uses.startswith(("actions/cache@", "actions/cache/save@")):
                assert name == "clients-swiftfin.yml", f"{name}: onverwachte schrijvende cache"


def test_upstream_sync_roept_ci_aan_zonder_rechten_of_geheimen():
    data = load(WORKFLOW_DIR / SYNC_ALL)
    assert set(triggers(data)) == {"schedule", "workflow_dispatch"}
    assert data.get("concurrency", {}).get("cancel-in-progress") is False
    for job_id, job in data["jobs"].items():
        if job_id.startswith(("forkregels-", "ci-")):
            client = job_id.split("-", 1)[1]
            assert job.get("needs") == f"sync-{client}"
            assert job.get("if") == f"needs.sync-{client}.outputs.branch != ''"
            assert "permissions" not in job and "secrets" not in job
            assert job["with"]["ref"] == f"${{{{ needs.sync-{client}.outputs.branch }}}}"


APP_ID_CHECKS = {
    "clients-android.yml": ("bouwmap android app/build --verwacht debug,release",
                            ["processLibreReleaseResources", "processProprietaryReleaseResources"]),
    "clients-androidtv.yml": ("bouwmap androidtv app/build --verwacht debug,release", ["processReleaseResources"]),
}


@pytest.mark.parametrize("name", sorted(APP_ID_CHECKS))
def test_android_ci_controleert_de_eigen_app_identiteit_met_aapt2(name):
    """JLC-0002/0003: elke Android-run bewijst met aapt2 pakketnaam/app_id/authorities voor debug én release."""
    data = load(WORKFLOW_DIR / name)
    runs = [str(s.get("run") or "") for _j, _job, s in steps(data)]
    aanroep, taken = APP_ID_CHECKS[name]
    gradle = [i for i, r in enumerate(runs) if "./gradlew" in r]
    check = [i for i, r in enumerate(runs) if "app_identiteit.py" in r]
    assert len(gradle) == 1 and len(check) == 1 and check[0] > gradle[0], name
    assert all(t in runs[gradle[0]] for t in taken), f"{name}: release-resources worden niet gelinkt"
    assert aanroep in runs[check[0]], name
    for trigger in ("push", "pull_request"):
        assert "tools/clients/app_identiteit.*" in triggers(data)[trigger]["paths"], (name, trigger)


def test_forkregels_controleert_de_app_identiteit_in_de_bron():
    runs = [str(s.get("run") or "") for _j, _job, s in steps(load(WORKFLOW_DIR / "clients-forkregels.yml"))]
    assert any("tools/clients/app_identiteit.py bron" in r for r in runs)


def test_swiftfin_ci_controleert_de_bundle_id_in_debug_en_release():
    data = load(WORKFLOW_DIR / "clients-swiftfin.yml")
    runs = [str(s.get("run") or "") for _j, _job, s in steps(data)]
    check = [r for r in runs if "app_identiteit.py xcode" in r]
    assert len(check) == 1
    assert "--plist" in check[0] and "-showBuildSettings -json" in check[0]
    assert "for configuratie in Debug Release" in check[0]
    assert "instellingen-Debug.json" in check[0] and "instellingen-Release.json" in check[0]
    assert runs.index(check[0]) > next(i for i, r in enumerate(runs) if "xcodebuild build" in r)
