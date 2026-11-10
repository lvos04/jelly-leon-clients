"""Tests voor tools/clients/app_identiteit.py (JLC-0002/0003/0004, ADR-0004).

- `bron`: op de echte repo (moet in orde zijn) en op kopieën met precies de fouten die naast de officiële app botsen
  (geen eigen ID, `resValue` uit `namespace`, officiële sharedpref-namen, alleen de xcconfig gewijzigd).
- Minimale patch: elk patchbestand wijkt t.o.v. de upstream-basis (subtree-squashcommit) precies zoveel regels af als
  vastgelegd, en alleen in regels over de app-identiteit.
- `apk`/`bouwmap`: met een nep-aapt2 die uitvoer in het echte aapt2-formaat (build-tools 36.0.0, gemeten op de lokaal
  gebouwde APK's) teruggeeft — Sim-getest. De echte aapt2-controle draait in de Android-workflows en lokaal
  (zie test-evidence/contract-1.2-app-identiteit.json).
- Contract 1.3 §1.1 besluit 1 (C1.3-JLC-02): letterlijke waarden van de officiële app in manifesten, `res/xml` en
  Kotlin/Java (`bron`), en `vergelijk` tegen de officiële upstream-APK's (nep-aapt2; de echte vergelijking draait in
  de Android-workflows en lokaal, test-evidence/contract-1.3-app-identiteit.json).
"""

from __future__ import annotations

import difflib
import hashlib
import io
import json
import plistlib
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import app_identiteit as ai
import pytest
from clients_common import DEFAULT_REPO_ROOT, ToolError, find_squash_commit

ROOT = Path(DEFAULT_REPO_ROOT)
NS = "http://schemas.android.com/apk/res/android"
ANDROIDTV = "org.jellyfin.androidtv.jellyleon"
ANDROID = "org.jellyfin.mobile.jellyleon"


# ---------------------------------------------------------------------------------------------- bron (statisch)


#: Kotlin-bronnen met de afgeleide waarden (authority, accounttype) die de tegenproeven hieronder letterlijk maken.
KOTLIN = {
    "provider": "androidtv/app/src/main/java/org/jellyfin/androidtv/integration/MediaContentProvider.kt",
    "account": "androidtv/app/src/main/java/org/jellyfin/androidtv/auth/AccountManagerMigration.kt",
    "constants": "android/app/src/main/java/org/jellyfin/mobile/utils/Constants.kt",
}


def bron_kopie(tmp_path: Path) -> Path:
    cfg = ai.load_config(ROOT)
    rels = [ai.CONFIG_REL, *KOTLIN.values()]
    for key in ai.ANDROID_CLIENTS:
        rels += [cfg[key]["gradle"], *cfg[key]["backup_xml"]]
        for d in ai.bronsets(ROOT, key):
            rels += [p.relative_to(ROOT).as_posix() for p in (d / "AndroidManifest.xml", *d.glob("res/xml*/*.xml"))
                     if p.is_file()]
    rels += [cfg["swiftfin"]["xcconfig"], cfg["swiftfin"]["pbxproj"]]
    for rel in rels:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, tmp_path / rel)
    return tmp_path


def vervang(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) >= count, (path, old)
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_echte_repo_heeft_eigen_app_identiteit():
    assert ai.check_bron(ROOT) == []


def test_bron_kopie_zelf_is_in_orde(tmp_path):
    """De kopie voor de tegenproeven bevat alles wat `bron` leest (anders bewijzen de tegenproeven niets)."""
    assert ai.check_bron(bron_kopie(tmp_path)) == []


def test_configuratie_verschilt_van_de_officiele_ids():
    cfg = ai.load_config(ROOT)
    assert cfg["android"]["application_id"] == ANDROID
    assert cfg["androidtv"]["application_id"] == ANDROIDTV
    assert cfg["swiftfin"]["bundle_id"] == "org.jellyfin.swiftfin.jellyleon"
    for key in ai.ANDROID_CLIENTS:
        c = cfg[key]
        assert c["application_id"] not in c["officieel"]
        assert c["application_id"] + c["debug_suffix"] not in c["officieel"]
        assert c["namespace"] in c["officieel"], "namespace blijft de officiële (Kotlin-pakket ongewijzigd)"


def test_bron_zonder_eigen_applicationid_faalt(tmp_path):
    repo = bron_kopie(tmp_path)
    vervang(repo / "android/app/build.gradle.kts", f'        applicationId = "{ANDROID}"\n', "")
    violations = ai.check_bron(repo)
    assert any("android/app/build.gradle.kts" in v and "applicationId" in v for v in violations), violations


def test_bron_androidtv_terug_naar_upstream_faalt(tmp_path):
    repo = bron_kopie(tmp_path)
    gradle = repo / "androidtv/app/build.gradle.kts"
    vervang(gradle, f'applicationId = "{ANDROIDTV}"', "applicationId = namespace")
    violations = ai.check_bron(repo)
    assert any("applicationId" in v for v in violations), violations


@pytest.mark.parametrize("naam", ["app_id", "app_search_suggest_authority", "app_search_suggest_intent_data"])
def test_bron_resvalue_uit_namespace_faalt(tmp_path, naam):
    """Precies de upstream-val: eigen applicationId, maar accounttype/zoek-authority nog van de officiële app."""
    repo = bron_kopie(tmp_path)
    gradle = repo / "androidtv/app/build.gradle.kts"
    text = gradle.read_text(encoding="utf-8")
    regel = next(line for line in text.splitlines() if f'"{naam}"' in line and "applicationIdSuffix" not in line)
    gradle.write_text(text.replace(regel, regel.replace("defaultConfig.applicationId", "namespace")),
                      encoding="utf-8")
    violations = ai.check_bron(repo)
    assert any(naam in v and "namespace" in v for v in violations), violations


def test_bron_officiele_sharedpref_faalt(tmp_path):
    repo = bron_kopie(tmp_path)
    vervang(repo / "androidtv/app/src/main/res/xml/backup_rules.xml",
            f'path="{ANDROIDTV}_preferences"', 'path="org.jellyfin.androidtv_preferences"', count=2)
    violations = ai.check_bron(repo)
    assert any("backup_rules.xml" in v and "officiële app" in v for v in violations), violations
    assert any("backup_rules.xml" in v and f"{ANDROIDTV}_preferences" in v and "ontbreekt" in v for v in violations)


def test_bron_ontbrekende_sharedpref_faalt(tmp_path):
    repo = bron_kopie(tmp_path)
    path = repo / "android/app/src/main/res/xml/backup_content.xml"
    text = path.read_text(encoding="utf-8")
    blok = f'    <include\n        domain="sharedpref"\n        path="{ANDROID}.debug_preferences" />\n'
    assert blok in text
    path.write_text(text.replace(blok, ""), encoding="utf-8")
    violations = ai.check_bron(repo)
    assert any(f"{ANDROID}.debug_preferences" in v and "ontbreekt" in v for v in violations), violations


def test_bron_swiftfin_alleen_xcconfig_gewijzigd_faalt(tmp_path):
    """iOS-Release heeft een eigen doelinstelling die de xcconfig overschrijft (JC2 noemde alleen de xcconfig)."""
    repo = bron_kopie(tmp_path)
    vervang(repo / "swiftfin/Swiftfin.xcodeproj/project.pbxproj",
            "PRODUCT_BUNDLE_IDENTIFIER = org.jellyfin.swiftfin.jellyleon;",
            "PRODUCT_BUNDLE_IDENTIFIER = org.jellyfin.swiftfin;")
    violations = ai.check_bron(repo)
    assert any("project.pbxproj" in v and "officiële bundle-id" in v for v in violations), violations


def test_bron_namespace_gewijzigd_faalt(tmp_path):
    repo = bron_kopie(tmp_path)
    vervang(repo / "android/app/build.gradle.kts", 'namespace = "org.jellyfin.mobile"', 'namespace = "nl.jellyleon"')
    violations = ai.check_bron(repo)
    assert any("namespace hoort ongewijzigd" in v for v in violations), violations


def test_configuratie_met_officiele_id_faalt(tmp_path):
    repo = bron_kopie(tmp_path)
    cfg_path = repo / ai.CONFIG_REL
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["androidtv"]["application_id"] = "org.jellyfin.androidtv"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    violations = ai.check_bron(repo)
    assert any("officiële ID" in v or "gelijk aan de namespace" in v for v in violations), violations


# ------------------------------------------------- letterlijke waarden van de officiële app (contract 1.3, C1.3-JLC-02)


def test_bronsets_omvatten_alle_modules_zonder_tests_en_bouwlogica():
    sets = {d.relative_to(ROOT).as_posix() for d in ai.bronsets(ROOT, "androidtv")}
    assert {"androidtv/app/src/main", "androidtv/app/src/debug", "androidtv/playback/core/src/main"} <= sets
    assert not any(s.endswith(("/test", "/androidTest")) or "buildSrc" in s or "/build/" in s for s in sets), sets
    assert {d.name for d in ai.bronsets(ROOT, "android")} == {"main", "debug", "libre", "proprietary"}


@pytest.mark.parametrize(("waarde", "suffixen", "verwacht"), [
    ("org.jellyfin.androidtv", None, "org.jellyfin.androidtv"),
    ("org.jellyfin.androidtv.content", None, "org.jellyfin.androidtv"),
    ("org.jellyfin.androidtv.debug.content", None, "org.jellyfin.androidtv.debug"),
    ("org.jellyfin.androidtv_preferences", None, "org.jellyfin.androidtv"),
    ("content://org.jellyfin.androidtv.content/intent", None, "org.jellyfin.androidtv"),
    (f"{ANDROIDTV}.content", None, None),
    (f"{ANDROIDTV}.debug_preferences", None, None),
    ("nl.voorbeeld.content", None, None),
    ("org.jellyfin.androidtv.content", {"content"}, "org.jellyfin.androidtv"),
    ("content://org.jellyfin.androidtv.content/intent", {"content"}, "org.jellyfin.androidtv"),
    ("org.jellyfin.androidtv", {"content"}, "org.jellyfin.androidtv"),
    ("org.jellyfin.androidtv.ui.AsyncImageView", {"content"}, None),  # klassenaam, geen identiteit
    ("org.jellyfin.androidtv.contentx", {"content"}, None),
])
def test_officiele_waarde(waarde, suffixen, verwacht):
    assert ai.officiele_waarde(waarde, ai.load_config(ROOT)["androidtv"], suffixen) == verwacht


def test_interne_intentnamen_in_de_code_zijn_toegestaan():
    """`org.jellyfin.mobile.intent.action.PLAY` e.d. zijn expliciete intents binnen de app (ADR-0004), geen ID."""
    c = ai.load_config(ROOT)["android"]
    assert ai.officiele_waarde("org.jellyfin.mobile.intent.action.PLAY", c, {"image-provider"}) is None
    assert ai.officiele_waarde("org.jellyfin.mobile.image-provider", c, {"image-provider"}) == "org.jellyfin.mobile"


def test_bron_letterlijke_authority_in_het_manifest_faalt(tmp_path):
    repo = bron_kopie(tmp_path)
    vervang(repo / "androidtv/app/src/main/AndroidManifest.xml", 'android:authorities="${applicationId}.content"',
            'android:authorities="org.jellyfin.androidtv.content"')
    violations = ai.check_bron(repo)
    assert any("AndroidManifest.xml: provider authorities='org.jellyfin.androidtv.content'" in v
               for v in violations), violations


def test_bron_letterlijke_permissie_in_een_flavor_manifest_faalt(tmp_path):
    repo = bron_kopie(tmp_path)
    vervang(repo / "android/app/src/libre/AndroidManifest.xml", "</manifest>",
            '    <permission android:name="org.jellyfin.mobile.debug.EIGEN" />\n</manifest>')
    violations = ai.check_bron(repo)
    assert any("android/app/src/libre/AndroidManifest.xml: permission name='org.jellyfin.mobile.debug.EIGEN'" in v
               for v in violations), violations


@pytest.mark.parametrize(("bestand", "oud", "nieuw", "melding"), [
    ("authenticator.xml", 'android:accountType="@string/app_id"', 'android:accountType="org.jellyfin.androidtv"',
     "account-authenticator accountType='org.jellyfin.androidtv'"),
    ("searchable.xml", 'android:searchSuggestAuthority="@string/app_search_suggest_authority"',
     'android:searchSuggestAuthority="org.jellyfin.androidtv.content"', "searchSuggestAuthority="),
    ("searchable.xml", 'android:searchSuggestIntentData="@string/app_search_suggest_intent_data"',
     'android:searchSuggestIntentData="content://org.jellyfin.androidtv.debug.content/intent"',
     "searchSuggestIntentData="),
])
def test_bron_letterlijke_waarde_in_res_xml_faalt(tmp_path, bestand, oud, nieuw, melding):
    repo = bron_kopie(tmp_path)
    vervang(repo / "androidtv/app/src/main/res/xml" / bestand, oud, nieuw)
    violations = ai.check_bron(repo)
    assert any(bestand in v and melding in v for v in violations), violations


@pytest.mark.parametrize(("sleutel", "oud", "nieuw", "letterlijk"), [
    ("provider", 'AUTHORITY = "${BuildConfig.APPLICATION_ID}.content"', 'AUTHORITY = "org.jellyfin.androidtv.content"',
     "org.jellyfin.androidtv.content"),
    ("account", "ACCOUNT_TYPE = BuildConfig.APPLICATION_ID", 'ACCOUNT_TYPE = "org.jellyfin.androidtv"',
     "org.jellyfin.androidtv"),
])
def test_bron_letterlijke_waarde_in_kotlin_faalt(tmp_path, sleutel, oud, nieuw, letterlijk):
    repo = bron_kopie(tmp_path)
    vervang(repo / KOTLIN[sleutel], oud, nieuw)
    violations = ai.check_bron(repo)
    assert any(KOTLIN[sleutel] in v and f'"{letterlijk}"' in v for v in violations), violations


def test_bron_testcode_en_interne_namen_tellen_niet(tmp_path):
    repo = bron_kopie(tmp_path)
    test_kt = repo / "androidtv/app/src/test/kotlin/X.kt"
    test_kt.parent.mkdir(parents=True)
    test_kt.write_text('val a = "org.jellyfin.androidtv.content"\n', encoding="utf-8")
    assert "org.jellyfin.mobile.intent.action.PLAY" in (repo / KOTLIN["constants"]).read_text(encoding="utf-8")
    assert ai.check_bron(repo) == []


def test_bron_zonder_hoofdmanifest_is_geen_bewijs(tmp_path):
    repo = bron_kopie(tmp_path)
    (repo / "android/app/src/main/AndroidManifest.xml").unlink()
    assert any("geen android/app/src/main/AndroidManifest.xml" in v for v in ai.check_bron(repo))


# Minimale patch: per bestand precies zoveel regels als nu (toegevoegd, verwijderd) t.o.v. de upstream-basis (de jongste
# subtree-squashcommit), en elke gewijzigde regel gaat over de app-identiteit. Groeit een patch, dan is dat een bewuste
# keuze die ook hier, in PATCHES.md en in de review zichtbaar wordt; kleine patches blijven bij een upstream-sync los
# te herbasen (ADR-0002/0003).
PATCH_OMVANG = {
    "android/app/build.gradle.kts": (2, 0),  # JLC-0002: commentaar + applicationId
    "android/app/src/main/res/xml/backup_content.xml": (2, 2),  # JLC-0002: twee sharedpref-namen
    "androidtv/app/build.gradle.kts": (8, 7),  # JLC-0003: applicationId + 2× drie resValue's
    "androidtv/app/src/main/res/xml/backup_content.xml": (2, 2),  # JLC-0003
    "androidtv/app/src/main/res/xml/backup_rules.xml": (4, 4),  # JLC-0003
    "swiftfin/Swiftfin.xcodeproj/project.pbxproj": (1, 1),  # JLC-0004: doelinstelling iOS-Release
    "swiftfin/XcodeConfig/Shared.xcconfig": (2, 1),  # JLC-0004: commentaar + bundle-id
}
IDENTITEITSREGEL_RE = re.compile(r"jellyleon|applicationId|\"app_id\"|app_search_suggest_|_preferences\"|"
                                 r"PRODUCT_BUNDLE_IDENTIFIER|Jelly Leon \(JLC-000[234]\)")


def upstream_basis(rel: str) -> list[str]:
    prefix, _, binnen = rel.partition("/")
    gevonden = find_squash_commit(ROOT, prefix)
    assert gevonden, f"geen subtree-squashcommit voor {prefix}/ (volledige historie nodig, zoals CI fetch-depth 0)"
    proc = subprocess.run(["git", "-C", str(ROOT), "show", f"{gevonden[0]}:{binnen}"], capture_output=True,
                          text=True, check=True)
    return proc.stdout.splitlines()


def test_patch_bestanden_volgen_de_configuratie():
    cfg = ai.load_config(ROOT)
    verwacht = {cfg["swiftfin"]["xcconfig"], cfg["swiftfin"]["pbxproj"]}
    for key in ai.ANDROID_CLIENTS:
        verwacht |= {cfg[key]["gradle"], *cfg[key]["backup_xml"]}
    assert set(PATCH_OMVANG) == verwacht


@pytest.mark.parametrize("rel", sorted(PATCH_OMVANG))
def test_patch_is_minimaal_en_raakt_alleen_de_app_identiteit(rel):
    basis = upstream_basis(rel)
    nu = (ROOT / rel).read_text(encoding="utf-8").splitlines()
    diff = list(difflib.unified_diff(basis, nu, lineterm="", n=0))
    plus = [regel[1:] for regel in diff if regel.startswith("+") and not regel.startswith("+++")]
    min_ = [regel[1:] for regel in diff if regel.startswith("-") and not regel.startswith("---")]
    assert (len(plus), len(min_)) == PATCH_OMVANG[rel], f"{rel}: patch-omvang veranderd:\n" + "\n".join(diff)
    vreemd = [regel for regel in plus + min_ if regel.strip() and not IDENTITEITSREGEL_RE.search(regel)]
    assert not vreemd, f"{rel}: wijziging buiten de app-identiteit: {vreemd}"


def test_minimaliteitstoets_vangt_een_wijziging_buiten_de_identiteit(tmp_path):
    """Tegenproef op de regelcontrole: een extra (niet-identiteits)regel in een patchbestand valt op."""
    basis = upstream_basis("android/app/build.gradle.kts")
    nu = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8").splitlines()
    nu.insert(nu.index("    defaultConfig {") + 1, "        minSdk = 26")
    diff = difflib.unified_diff(basis, nu, lineterm="", n=0)
    plus = [r[1:] for r in diff if r.startswith("+") and not r.startswith("+++")]
    assert [r for r in plus if not IDENTITEITSREGEL_RE.search(r)] == ["        minSdk = 26"]


def test_cli_bron_exitcodes(tmp_path, capsys):
    assert ai.main(["--repo-root", str(ROOT), "bron"]) == 0
    repo = bron_kopie(tmp_path)
    vervang(repo / "swiftfin/XcodeConfig/Shared.xcconfig", "org.jellyfin.swiftfin.jellyleon", "org.jellyfin.swiftfin")
    assert ai.main(["--repo-root", str(repo), "bron"]) == 1
    assert "OVERTREDING" in capsys.readouterr().out
    (repo / ai.CONFIG_REL).unlink()
    assert ai.main(["--repo-root", str(repo), "bron"]) == 3


# ------------------------------------------------------------------------------------- aapt2-uitvoer (nep-aapt2)


def manifest_tree(package: str, authorities: list[str], permissions: list[str]) -> str:
    lines = [f"N: android={NS} (line=2)", "  E: manifest (line=2)",
             f"    A: {NS}:versionCode(0x0101021b)=1",
             f'    A: package="{package}" (Raw: "{package}")']
    for perm in permissions:
        lines += ["      E: permission (line=50)",
                  f'        A: {NS}:name(0x01010003)="{perm}" (Raw: "{perm}")',
                  f"        A: {NS}:protectionLevel(0x01010009)=0x00000002",
                  "      E: uses-permission (line=54)",
                  f'        A: {NS}:name(0x01010003)="{perm}" (Raw: "{perm}")']
    lines.append("      E: application (line=60)")
    for auth in authorities:
        lines += ["          E: provider (line=99)",
                  f'            A: {NS}:name(0x01010003)="androidx.startup.InitializationProvider" '
                  '(Raw: "androidx.startup.InitializationProvider")',
                  f"            A: {NS}:exported(0x01010010)=false",
                  f'            A: {NS}:authorities(0x01010018)="{auth}" (Raw: "{auth}")']
    return "\n".join(lines) + "\n"


def backup_tree(prefs: list[str]) -> str:
    lines = ["E: data-extraction-rules (line=2)", "    E: cloud-backup (line=3)"]
    for pref in [*prefs, "systemprefs"]:
        lines += ["        E: include (line=12)", '          A: domain="sharedpref" (Raw: "sharedpref")',
                  f'          A: path="{pref}" (Raw: "{pref}")']
    return "\n".join(lines) + "\n"


def resources_dump(package: str, strings: dict[str, str],
                   xml_files: dict[str, str]) -> tuple[str, dict[str, str]]:
    lines = ["Binary APK", f"Package name={package} id=7f", "  type string id=12 entryCount=3"]
    ids = {}
    for i, (name, value) in enumerate(strings.items()):
        rid = f"0x7f1200{0x27 + i:02x}"
        ids[name] = rid
        lines += [f"    resource {rid} string/{name}", f'      () "{value}"', f'      (nl) "{value}"']
    lines.append("  type xml id=16 entryCount=5")
    for i, (name, path) in enumerate(xml_files.items()):
        lines += [f"    resource 0x7f1600{i:02x} xml/{name}", f"      () (file) {path} type=XML"]
    return "\n".join(lines) + "\n", ids


def androidtv_archief(package: str, *, app_id: str | None = None, authority: str | None = None,
                      authorities: list[str] | None = None, permissions: list[str] | None = None,
                      prefs: list[str] | None = None, account_ref: str = "app_id") -> dict:
    authority = authority or f"{package}.content"
    strings = {"app_id": app_id or package, "app_name": "Jellyfin",
               "app_search_suggest_authority": authority,
               "app_search_suggest_intent_data": f"content://{authority}/intent"}
    xml_files = {"authenticator": "res/xml/authenticator.xml", "backup_content": "res/xml/backup_content.xml",
                 "backup_rules": "res/Ab.xml", "searchable": "res/xml/searchable.xml"}
    resources, ids = resources_dump(package, strings, xml_files)
    base = package.removesuffix(".debug")
    prefs = prefs if prefs is not None else [f"{base}_preferences", f"{base}.debug_preferences"]
    return {
        "packagename": package + "\n",
        "resources": resources,
        "xmltree": {
            "AndroidManifest.xml": manifest_tree(
                package, authorities if authorities is not None else
                [f"{package}.androidx-startup", f"{package}.content", f"{package}.integration.provider.ImageProvider"],
                permissions if permissions is not None else [f"{package}.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"]),
            "res/xml/authenticator.xml": (
                f"N: android={NS} (line=6)\n  E: account-authenticator (line=6)\n"
                f"    A: {NS}:label(0x01010001)=@{ids['app_name']}\n"
                f"    A: {NS}:accountType(0x0101028f)=@{ids[account_ref]}\n"),
            "res/xml/searchable.xml": (
                f"N: android={NS} (line=2)\n  E: searchable (line=2)\n"
                f"    A: {NS}:searchSuggestAuthority(0x010101d6)=@{ids['app_search_suggest_authority']}\n"
                f"    A: {NS}:searchSuggestIntentData(0x010101d8)=@{ids['app_search_suggest_intent_data']}\n"),
            "res/xml/backup_content.xml": backup_tree(prefs),
            "res/Ab.xml": backup_tree(prefs),
        },
    }


def android_archief(package: str, **kw) -> dict:
    base = package.removesuffix(".debug")
    resources, _ids = resources_dump(package, {"app_name": "Jellyfin"},
                                     {"backup_content": "res/xml/backup_content.xml"})
    return {
        "packagename": package + "\n",
        "resources": resources,
        "xmltree": {
            "AndroidManifest.xml": manifest_tree(
                package, kw.get("authorities", [f"{package}.image-provider", f"{package}.androidx-startup"]),
                kw.get("permissions", [f"{package}.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"])),
            "res/xml/backup_content.xml": backup_tree(
                kw.get("prefs", [f"{base}_preferences", f"{base}.debug_preferences"])),
        },
    }


FAKE_AAPT2 = """
import json, os, sys
data = json.load(open(os.environ["FAKE_AAPT2_DATA"], encoding="utf-8"))
args = sys.argv[1:]
archief = data.get(args[-1])
if archief is None or args[0] != "dump":
    sys.stderr.write("W/ziparchive: Unable to open '" + args[-1] + "': No such file or directory\\n")
    sys.exit(1)
if args[1] == "packagename":
    sys.stdout.write(archief["packagename"])
elif args[1] == "resources":
    sys.stdout.write(archief["resources"])
elif args[1] == "xmltree" and args[2] == "--file" and args[3] in archief["xmltree"]:
    sys.stdout.write(archief["xmltree"][args[3]])
else:
    sys.stderr.write("error: file not found\\n")
    sys.exit(1)
"""


@pytest.fixture
def nep_aapt2(tmp_path, monkeypatch):
    script = tmp_path / "aapt2"
    script.write_text(f"#!{sys.executable}\n{FAKE_AAPT2}", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    data_file = tmp_path / "aapt2-data.json"
    archives: dict[str, dict] = {}

    def add(rel: str, archief: dict) -> Path:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"PK\x03\x04 nep-archief")
        archives[str(path)] = archief
        data_file.write_text(json.dumps(archives), encoding="utf-8")
        return path

    monkeypatch.setenv("FAKE_AAPT2_DATA", str(data_file))
    data_file.write_text("{}", encoding="utf-8")
    add.aapt2 = str(script)
    return add


def check(nep, client: str, path: Path):
    return ai.check_apk(ai.load_config(ROOT), client, path, nep.aapt2)


def test_androidtv_debug_en_release_in_orde(nep_aapt2):
    debug = nep_aapt2("debug/jellyfin-androidtv-debug.apk", androidtv_archief(f"{ANDROIDTV}.debug"))
    release = nep_aapt2("release/linked-resources-binary-format-release.ap_", androidtv_archief(ANDROIDTV))
    for path, pkg in ((debug, f"{ANDROIDTV}.debug"), (release, ANDROIDTV)):
        r = check(nep_aapt2, "androidtv", path)
        assert r.violations == [], r.violations
        assert r.pakket == pkg
        assert r.res_waarden["xml/authenticator:accountType"] == pkg
        assert r.res_waarden["xml/searchable:searchSuggestAuthority"] == f"{pkg}.content"


def test_officiele_pakketnaam_faalt(nep_aapt2):
    path = nep_aapt2("x-release.apk", androidtv_archief("org.jellyfin.androidtv"))
    r = check(nep_aapt2, "androidtv", path)
    assert any("officiële app" in v for v in r.violations), r.violations


def test_debug_apk_met_release_pakketnaam_faalt(nep_aapt2):
    path = nep_aapt2("x-debug.apk", androidtv_archief(ANDROIDTV))
    r = check(nep_aapt2, "androidtv", path)
    assert any("verwacht" in v and f"{ANDROIDTV}.debug" in v for v in r.violations), r.violations


def test_app_id_en_zoek_authority_van_de_namespace_falen(nep_aapt2):
    """Upstream-gedrag met alleen een andere applicationId: accounttype en zoek-authority van de officiële app."""
    archief = androidtv_archief(ANDROIDTV, app_id="org.jellyfin.androidtv", authority="org.jellyfin.androidtv.content")
    r = check(nep_aapt2, "androidtv", nep_aapt2("app-release.apk", archief))
    tekst = "\n".join(r.violations)
    assert "string/app_id = 'org.jellyfin.androidtv'" in tekst
    assert "string/app_search_suggest_authority" in tekst
    assert "zoek-authority 'org.jellyfin.androidtv.content' bestaat niet als provider" in tekst
    assert "xml/authenticator accountType" in tekst


def test_authenticator_met_ander_accounttype_faalt(nep_aapt2):
    archief = androidtv_archief(ANDROIDTV, account_ref="app_name")
    r = check(nep_aapt2, "androidtv", nep_aapt2("app-release.apk", archief))
    assert any("xml/authenticator accountType = 'Jellyfin'" in v for v in r.violations), r.violations


def test_authority_of_permissie_zonder_pakketprefix_faalt(nep_aapt2):
    archief = android_archief(f"{ANDROID}.debug", authorities=[f"{ANDROID}.debug.image-provider",
                                                               "org.jellyfin.mobile.androidx-startup"],
                              permissions=["org.jellyfin.mobile.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"])
    r = check(nep_aapt2, "android", nep_aapt2("app-libre-debug.apk", archief))
    tekst = "\n".join(r.violations)
    assert "provider-authority 'org.jellyfin.mobile.androidx-startup'" in tekst
    assert "DUPLICATE_PERMISSION" in tekst


def test_android_debug_en_release_in_orde(nep_aapt2):
    for rel, pkg in (("libre/app-libre-debug.apk", f"{ANDROID}.debug"),
                     ("proprietary/app-proprietary-debug.apk", f"{ANDROID}.debug"),
                     ("libre/linked-resources-binary-format-libre-release.ap_", ANDROID)):
        r = check(nep_aapt2, "android", nep_aapt2(rel, android_archief(pkg)))
        assert r.violations == [], (rel, r.violations)


def test_officiele_sharedpref_in_apk_faalt(nep_aapt2):
    archief = android_archief(f"{ANDROID}.debug", prefs=["org.jellyfin.mobile_preferences",
                                                         "org.jellyfin.mobile.debug_preferences"])
    r = check(nep_aapt2, "android", nep_aapt2("app-debug.apk", archief))
    assert any(f"'{ANDROID}.debug_preferences' ontbreekt" in v for v in r.violations), r.violations
    assert any("'org.jellyfin.mobile_preferences' hoort niet bij" in v for v in r.violations)


def test_geen_authorities_is_geen_bewijs(nep_aapt2):
    r = check(nep_aapt2, "android", nep_aapt2("app-debug.apk", android_archief(f"{ANDROID}.debug", authorities=[])))
    assert any("geen enkele provider-authority" in v for v in r.violations)


def test_variant_niet_af_te_leiden_is_gebruiksfout(nep_aapt2):
    path = nep_aapt2("app.apk", android_archief(ANDROID))
    with pytest.raises(ToolError, match="variant"):
        check(nep_aapt2, "android", path)
    assert ai.check_apk(ai.load_config(ROOT), "android", path, nep_aapt2.aapt2, "release").violations == []


def test_aapt2_fout_is_gebruiksfout(nep_aapt2, tmp_path):
    kapot = tmp_path / "kapot-debug.apk"
    kapot.write_bytes(b"geen zip")
    with pytest.raises(ToolError, match="aapt2 dump packagename"):
        check(nep_aapt2, "android", kapot)


def test_bouwmap_vindt_apks_en_release_ap(nep_aapt2, tmp_path, capsys):
    build = "tvbuild"
    nep_aapt2(f"{build}/outputs/apk/debug/jellyfin-androidtv-debug.apk", androidtv_archief(f"{ANDROIDTV}.debug"))
    nep_aapt2(f"{build}/intermediates/linked_resources_binary_format/release/processReleaseResources/"
              "linked-resources-binary-format-release.ap_", androidtv_archief(ANDROIDTV))
    nep_aapt2(f"{build}/intermediates/linked_resources_binary_format/debug/processDebugResources/"
              "linked-resources-binary-format-debug.ap_", androidtv_archief("org.jellyfin.androidtv.debug"))
    found = ai.find_artifacts(tmp_path / build)
    assert [(p.suffix, v) for p, v in found] == [(".apk", "debug"), (".ap_", "release")], found
    rc = ai.main(["--repo-root", str(ROOT), "bouwmap", "androidtv", str(tmp_path / build), "--aapt2", nep_aapt2.aapt2])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "2 artefact(en) gecontroleerd, 0 overtreding(en)." in out


def test_bouwmap_android_release_uit_proto_ap_per_flavor(nep_aapt2, tmp_path):
    """android release met resource-shrinking: alleen proto-.ap_, één per flavor; binair wint als beide er zijn."""
    b = "mbuild"
    nep_aapt2(f"{b}/outputs/apk/libre/debug/app-libre-debug.apk", android_archief(f"{ANDROID}.debug"))
    proto = "intermediates/linked_resources_proto_format"
    for flavor in ("libre", "proprietary"):
        nep_aapt2(f"{b}/{proto}/{flavor}Release/process{flavor.title()}ReleaseResources/"
                  f"linked-resources-proto-format-{flavor}Release.ap_", android_archief(ANDROID))
    binair = nep_aapt2(f"{b}/intermediates/linked_resources_binary_format/libreRelease/x/"
                       "linked-resources-binary-format-libreRelease.ap_", android_archief(ANDROID))
    found = ai.find_artifacts(tmp_path / b)
    assert [v for _p, v in found] == ["debug", "release", "release"]
    assert found[1][0] == binair and "proprietaryRelease" in str(found[2][0])
    assert all(check(nep_aapt2, "android", p).violations == [] for p, _v in found)


def test_bouwmap_zonder_release_of_leeg_is_gebruiksfout(nep_aapt2, tmp_path, capsys):
    leeg = tmp_path / "leeg"
    leeg.mkdir()
    assert ai.main(["--repo-root", str(ROOT), "bouwmap", "android", str(leeg), "--aapt2", nep_aapt2.aapt2]) == 3
    nep_aapt2("b/outputs/apk/libre/debug/app-libre-debug.apk", android_archief(f"{ANDROID}.debug"))
    assert ai.main(["--repo-root", str(ROOT), "bouwmap", "android", str(tmp_path / "b"),
                    "--aapt2", nep_aapt2.aapt2]) == 3
    assert "geen artefact voor release" in capsys.readouterr().err
    assert ai.main(["--repo-root", str(ROOT), "bouwmap", "android", str(tmp_path / "b"), "--verwacht", "debug",
                    "--aapt2", nep_aapt2.aapt2]) == 0


def test_cli_apk_overtreding_geeft_exit_1(nep_aapt2, capsys):
    path = nep_aapt2("x-release.apk", android_archief("org.jellyfin.mobile"))
    assert ai.main(["--repo-root", str(ROOT), "apk", "android", str(path), "--aapt2", nep_aapt2.aapt2]) == 1
    assert "OVERTREDING: pakketnaam 'org.jellyfin.mobile' is de officiële app" in capsys.readouterr().out


def test_find_aapt2_kiest_de_hoogste_build_tools(tmp_path, monkeypatch):
    for versie in ("9.0.0", "36.0.0", "35.0.0", "36.1.0-rc1"):
        d = tmp_path / "sdk" / "build-tools" / versie
        d.mkdir(parents=True)
        (d / "aapt2").write_text("", encoding="utf-8")
    monkeypatch.delenv("AAPT2", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path / "sdk"))
    assert ai.find_aapt2().endswith("36.1.0-rc1/aapt2")
    monkeypatch.setenv("AAPT2", "/elders/aapt2")
    assert ai.find_aapt2() == "/elders/aapt2"
    assert ai.find_aapt2("/expliciet/aapt2") == "/expliciet/aapt2"


def test_find_aapt2_zonder_sdk_is_gebruiksfout(tmp_path, monkeypatch):
    for env in ("AAPT2", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ToolError, match="aapt2 niet gevonden"):
        ai.find_aapt2()


REAL_AUTHENTICATOR = """N: android=http://schemas.android.com/apk/res/android (line=6)
  E: account-authenticator (line=6)
    A: http://schemas.android.com/apk/res/android:label(0x01010001)=@0x7f120028
    A: http://schemas.android.com/apk/res/android:icon(0x01010002)=@0x7f0f0001
    A: http://schemas.android.com/apk/res/android:accountType(0x0101028f)=@0x7f120027
"""
REAL_RESOURCES = """    resource 0x7f120027 string/app_id
      () "org.jellyfin.androidtv.jellyleon.debug"
    resource 0x7f160000 xml/authenticator
      () (file) res/xml/authenticator.xml type=XML
"""


def test_parsers_op_echte_aapt2_uitvoer():
    """Fragmenten letterlijk uit aapt2 36.0.0 op de lokaal gebouwde androidtv-debug-APK."""
    tree = ai.parse_xmltree(REAL_AUTHENTICATOR)
    assert tree[0].tag == "account-authenticator" and tree[0].attrs["accountType"] == "@0x7f120027"
    res = ai.parse_resources(REAL_RESOURCES)
    assert res.files["xml/authenticator"] == "res/xml/authenticator.xml"
    assert ai.resolve(res, tree[0].attrs["accountType"]) == "org.jellyfin.androidtv.jellyleon.debug"
    assert ai.parse_attr_value('"a.b" (Raw: "a.b")') == "a.b" and ai.parse_attr_value("false") == "false"
    assert ai.parse_attr_value(r'"Jelly \"Leon\" é\\x" (Raw: "…")') == 'Jelly "Leon" é\\x'


# -------------------------------------------------- vergelijking met de officiële APK's (contract 1.3, C1.3-JLC-02)


def officiele_set(nep, client: str) -> list:
    cfg = ai.load_config(ROOT)
    maak = androidtv_archief if client == "androidtv" else android_archief
    out = []
    for o in cfg[client]["officieel"]:
        variant = "debug" if o.endswith(".debug") else "release"
        path = nep(f"officieel/{o}-{variant}.apk", maak(o))
        out.append(ai.check_apk(cfg, client, path, nep.aapt2, variant))
    return out


def eigen_set(nep, client: str, **kw) -> list:
    cfg = ai.load_config(ROOT)
    maak = androidtv_archief if client == "androidtv" else android_archief
    eigen = cfg[client]["application_id"]
    return [ai.check_apk(cfg, client, nep(f"eigen/{pkg}-{variant}.apk", maak(pkg, **kw)), nep.aapt2, variant)
            for pkg, variant in ((f"{eigen}.debug", "debug"), (eigen, "release"))]


@pytest.mark.parametrize("client", ai.ANDROID_CLIENTS)
def test_vergelijk_eigen_builds_hebben_geen_officiele_waarde(nep_aapt2, client):
    v = ai.vergelijk_met_officieel(ai.load_config(ROOT), client, eigen_set(nep_aapt2, client),
                                   officiele_set(nep_aapt2, client))
    assert v.violations == []
    # systemprefs is in beide apps gelijk, maar per app afgeschermd en niet van de pakketnaam afgeleid
    assert any("sharedpref 'systemprefs'" in g and "afgeschermd" in g for g in v.gelijk_toegestaan), v.gelijk_toegestaan
    soorten = ai.identiteitswaarden(v.eigen[0])
    assert soorten["authority"] and soorten["permissie"] and soorten["sharedpref"]
    if client == "androidtv":
        assert soorten["accounttype"] == {f"{ANDROIDTV}.debug"}
        assert soorten["app_search_suggest"] == {f"{ANDROIDTV}.debug.content",
                                                 f"content://{ANDROIDTV}.debug.content/intent"}


@pytest.mark.parametrize(("kw", "melding"), [
    ({"authorities": ["org.jellyfin.androidtv.content"]}, "authority 'org.jellyfin.androidtv.content' is gelijk aan"),
    ({"permissions": ["org.jellyfin.androidtv.debug.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"]}, "permissie"),
    ({"app_id": "org.jellyfin.androidtv"}, "accounttype 'org.jellyfin.androidtv' is gelijk aan"),
    ({"authority": "org.jellyfin.androidtv.debug.content"},
     "app_search_suggest 'org.jellyfin.androidtv.debug.content'"),
    ({"prefs": ["org.jellyfin.androidtv_preferences"]}, "sharedpref 'org.jellyfin.androidtv_preferences' is gelijk"),
])
def test_vergelijk_vindt_elke_soort_gelijke_waarde(nep_aapt2, kw, melding):
    v = ai.vergelijk_met_officieel(ai.load_config(ROOT), "androidtv", eigen_set(nep_aapt2, "androidtv", **kw),
                                   officiele_set(nep_aapt2, "androidtv"))
    assert any(melding in x for x in v.violations), v.violations


def test_vergelijk_met_onbruikbare_officiele_meting_is_gebruiksfout(nep_aapt2):
    cfg = ai.load_config(ROOT)
    eigen = eigen_set(nep_aapt2, "android")
    officieel = officiele_set(nep_aapt2, "android")
    with pytest.raises(ToolError, match="dekt niet alle officiële ID's"):
        ai.vergelijk_met_officieel(cfg, "android", eigen, officieel[:1])
    with pytest.raises(ToolError, match="geen officiële ID"):
        ai.vergelijk_met_officieel(cfg, "android", eigen, [*officieel, eigen[1]])
    zonder = ai.check_apk(cfg, "android", nep_aapt2("off/x-release.apk", android_archief("org.jellyfin.mobile",
                                                                                         authorities=[])),
                          nep_aapt2.aapt2, "release")
    with pytest.raises(ToolError, match="geen authorities"):
        ai.vergelijk_met_officieel(cfg, "android", eigen, [zonder, officieel[1]])
    with pytest.raises(ToolError, match="bewijst niets"):
        ai.vergelijk_met_officieel(cfg, "android", [], officieel)


def test_officiele_apks_in_de_configuratie_volgen_de_basislijn():
    """Zelfde upstream-versie als de subtree, elke officiële ID gedekt, sha256 van de GitHub-release."""
    cfg = ai.load_config(ROOT)
    basis = json.loads((ROOT / "tools/clients/baseline.json").read_text(encoding="utf-8"))["clients"]
    for client in ai.ANDROID_CLIENTS:
        lijst = ai.officiele_apks(cfg, client)
        tag = basis[client]["upstream_tag"]
        repo_naam = basis[client]["upstream_repo"].removeprefix("https://github.com/").removesuffix(".git")
        assert len({a["naam"] for a in lijst}) == len(lijst)
        assert {a["variant"] for a in lijst} == set(ai.VARIANTEN)
        for a in lijst:
            assert f"-{tag}-" in a["naam"], f"{client}: {a['naam']} hoort bij {tag} (upstream-sync: officiele_apks mee)"
            assert a["url"] == f"https://github.com/{repo_naam}/releases/download/{tag}/{a['naam']}", a["url"]


@pytest.mark.parametrize("fout", [
    {"variant": "beta"}, {"sha256": "abc"}, {"url": "https://voorbeeld.invalid/x.apk"}, {"naam": "../x.apk"},
    {"naam": "x.aab"},
])
def test_ongeldige_officiele_apk_regel_is_gebruiksfout(fout):
    cfg = ai.load_config(ROOT)
    cfg["android"]["officiele_apks"] = [{**cfg["android"]["officiele_apks"][0], **fout}]
    with pytest.raises(ToolError, match="ongeldige officiele_apks-regel"):
        ai.officiele_apks(cfg, "android")
    cfg["android"]["officiele_apks"] = []
    with pytest.raises(ToolError, match="geen officiele_apks"):
        ai.officiele_apks(cfg, "android")


class NepAntwoord(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_haal_officiele_apk_controleert_sha256_en_hernoemt_atomair(tmp_path, monkeypatch):
    inhoud = b"PK\x03\x04 officieel"
    a = {"naam": "jellyfin-android-v2.7.3-libre-release.apk", "variant": "release",
         "url": "https://github.com/jellyfin/jellyfin-android/releases/download/v2.7.3/x.apk",
         "sha256": hashlib.sha256(inhoud).hexdigest()}
    gevraagd = []
    monkeypatch.setattr(ai.urllib.request, "urlopen", lambda url, timeout: gevraagd.append(url) or NepAntwoord(inhoud))
    doel = ai.haal_officiele_apk(a, tmp_path / "off")
    assert doel.read_bytes() == inhoud and gevraagd == [a["url"]]
    assert ai.haal_officiele_apk(a, tmp_path / "off") == doel and len(gevraagd) == 1  # hergebruikt, geen download
    monkeypatch.setattr(ai.urllib.request, "urlopen", lambda url, timeout: NepAntwoord(b"vervalst"))
    doel.write_bytes(b"beschadigd")
    with pytest.raises(ToolError, match="sha256"):
        ai.haal_officiele_apk(a, tmp_path / "off")
    assert sorted(p.name for p in (tmp_path / "off").iterdir()) == [a["naam"]]  # geen .deel achtergelaten
    with pytest.raises(ToolError, match="download uitgezet"):
        ai.haal_officiele_apk(a, tmp_path / "off", download=False)

    def kapot(url, timeout):
        raise OSError("netwerk weg")
    monkeypatch.setattr(ai.urllib.request, "urlopen", kapot)
    with pytest.raises(ToolError, match="download van .* mislukt"):
        ai.haal_officiele_apk(a, tmp_path / "leeg")


def test_cli_vergelijk(nep_aapt2, tmp_path, capsys):
    """Eind-tot-eind met een eigen configuratie (sha256 van de nep-APK's) en een bouwmap; geen netwerk."""
    cfg = ai.load_config(ROOT)
    repo = tmp_path / "repo"
    (repo / ai.CONFIG_REL).parent.mkdir(parents=True)
    off = tmp_path / "officieel"
    lijst = []
    for o in cfg["androidtv"]["officieel"]:
        variant = "debug" if o.endswith(".debug") else "release"
        naam = f"jellyfin-androidtv-v0.19.10-{variant}.apk"
        path = nep_aapt2(f"officieel/{naam}", androidtv_archief(o))
        lijst.append({"naam": naam, "variant": variant, "sha256": ai.sha256_bestand(path),
                      "url": f"https://github.com/jellyfin/jellyfin-androidtv/releases/download/v0.19.10/{naam}"})
    cfg["androidtv"]["officiele_apks"] = lijst
    (repo / ai.CONFIG_REL).write_text(json.dumps(cfg), encoding="utf-8")
    nep_aapt2("tvbuild/outputs/apk/debug/jellyfin-androidtv-debug.apk", androidtv_archief(f"{ANDROIDTV}.debug"))
    nep_aapt2("tvbuild/outputs/apk/release/jellyfin-androidtv-release.apk", androidtv_archief(ANDROIDTV))
    args = ["--repo-root", str(repo), "vergelijk", "androidtv", str(tmp_path / "tvbuild"), "--officieel-map", str(off),
            "--geen-download", "--aapt2", nep_aapt2.aapt2]
    assert ai.main(args) == 0, capsys.readouterr()
    out = capsys.readouterr().out
    assert "2 eigen artefact(en) tegen 2 officiële APK('s): 0 gelijke identiteitswaarde(n)." in out
    assert "gelijk, toegestaan" in out and "systemprefs" in out
    assert ai.main(["--json", *args]) == 0
    assert json.loads(capsys.readouterr().out)["in_orde"] is True
    nep_aapt2("tvbuild/outputs/apk/release/jellyfin-androidtv-release.apk",
              androidtv_archief(ANDROIDTV, app_id="org.jellyfin.androidtv"))
    assert ai.main(args) == 1
    assert "OVERTREDING: release org.jellyfin.androidtv.jellyleon: accounttype 'org.jellyfin.androidtv'" in \
        capsys.readouterr().out
    (off / lijst[0]["naam"]).unlink()
    assert ai.main(args) == 3
    assert "download uitgezet" in capsys.readouterr().err


# --------------------------------------------------------------------------------- Swiftfin (xcodebuild-instellingen)


def build_settings(tmp_path: Path, naam: str, rows: list[tuple[str, str, str]], plist_ids: dict | None = None) -> Path:
    """Vorm van `xcodebuild -showBuildSettings -json` (lijst met action/target/buildSettings); Sim-getest."""
    entries = []
    for target, configuratie, bundle_id in rows:
        build_dir = tmp_path / "DerivedData" / f"{configuratie}-{target.replace(' ', '_')}"
        bs = {"WRAPPER_EXTENSION": "app", "CONFIGURATION": configuratie, "PLATFORM_NAME": "iphonesimulator",
              "PRODUCT_BUNDLE_IDENTIFIER": bundle_id, "TARGET_BUILD_DIR": str(build_dir),
              "INFOPLIST_PATH": f"{target}.app/Info.plist"}
        if plist_ids and target in plist_ids:
            info = build_dir / bs["INFOPLIST_PATH"]
            info.parent.mkdir(parents=True, exist_ok=True)
            info.write_bytes(plistlib.dumps({"CFBundleIdentifier": plist_ids[target]}, fmt=plistlib.FMT_BINARY))
        entries.append({"action": "build", "target": target, "buildSettings": bs})
    entries.append({"action": "build", "target": "Pakket", "buildSettings": {"WRAPPER_EXTENSION": "framework",
                                                                             "PRODUCT_BUNDLE_IDENTIFIER": "x.y"}})
    path = tmp_path / naam
    path.write_text("Command line invocation:\n    xcodebuild -showBuildSettings -json\n\n" + json.dumps(entries),
                    encoding="utf-8")
    return path


def test_xcode_eigen_bundle_id_in_orde(tmp_path, capsys):
    eigen = "org.jellyfin.swiftfin.jellyleon"
    debug = build_settings(tmp_path, "debug.json", [("Swiftfin iOS", "Debug", eigen)], {"Swiftfin iOS": eigen})
    release = build_settings(tmp_path, "release.json", [("Swiftfin iOS", "Release", eigen)])
    rc = ai.main(["--repo-root", str(ROOT), "xcode", "--instellingen", str(debug), "--instellingen", str(release),
                  "--plist"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "2 app-doel(en) gecontroleerd, 0 overtreding(en)." in out and "Info.plist: " + eigen in out


def test_xcode_release_met_officiele_doelinstelling_faalt(tmp_path):
    """De val uit JC2: xcconfig gewijzigd, maar de doelinstelling van iOS-Release houdt de officiële ID."""
    eigen = "org.jellyfin.swiftfin.jellyleon"
    path = build_settings(tmp_path, "s.json", [("Swiftfin iOS", "Debug", eigen),
                                               ("Swiftfin iOS", "Release", "org.jellyfin.swiftfin")])
    _report, violations = ai.check_xcode(ai.load_config(ROOT), [path])
    assert violations == ["Swiftfin iOS (Release): officiële bundle-id org.jellyfin.swiftfin"]


def test_xcode_plist_afwijkend_of_ontbrekend_faalt(tmp_path):
    eigen = "org.jellyfin.swiftfin.jellyleon"
    cfg = ai.load_config(ROOT)
    path = build_settings(tmp_path, "a.json", [("Swiftfin tvOS", "Debug", eigen)],
                          {"Swiftfin tvOS": "org.jellyfin.swiftfin"})
    assert any("CFBundleIdentifier 'org.jellyfin.swiftfin'" in v for v in ai.check_xcode(cfg, [path], True)[1])
    zonder = build_settings(tmp_path, "b.json", [("Swiftfin tvOS", "Release", eigen)])
    assert any("geen Info.plist" in v for v in ai.check_xcode(cfg, [zonder], True)[1])
    assert ai.check_xcode(cfg, [zonder], False)[1] == []


def test_xcode_zonder_app_doel_of_kapotte_json(tmp_path):
    leeg = tmp_path / "leeg.json"
    leeg.write_text("[]", encoding="utf-8")
    assert any("geen app-doel" in v for v in ai.check_xcode(ai.load_config(ROOT), [leeg])[1])
    kapot = tmp_path / "kapot.json"
    kapot.write_text("error: scheme not found", encoding="utf-8")
    assert ai.main(["--repo-root", str(ROOT), "xcode", "--instellingen", str(kapot)]) == 3
