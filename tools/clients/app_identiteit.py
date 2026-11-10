#!/usr/bin/env python3
"""Controle van de eigen app-identiteit naast de officiële Jellyfin-apps (ADR-0004; JLC-0002, JLC-0003, JLC-0004).

Waarom: Android installeert twee apps met dezelfde pakketnaam niet naast elkaar; twee apps met hetzelfde accounttype
(androidtv `app_id`) of dezelfde content-provider-authority (zoeksuggesties) botsen bij installatie of breken stil.
Deze controle bewijst per build dat pakketnaam, `app_id` en authorities bij de eigen ID horen en verschillen van de
officiële app. De verwachte waarden staan in `tools/clients/app_identiteit.json`.

Subcommando's:
  bron                      statisch op de bron (Gradle-bestanden, back-upregels, xcconfig/pbxproj); geen SDK nodig
  apk <client> <bestand>…   met `aapt2` op gebouwde APK's of op de gelinkte resources (`*.ap_`) van een variant
  bouwmap <client> <map>    zoekt in een Gradle-bouwmap (`<client>/app/build`) alle APK's en de `*.ap_` van de
                            release-variant(en) en controleert ze; `--verwacht debug,release` eist beide
  vergelijk <client> <map>  contract 1.3 §1.1 besluit 1 (C1.3-JLC-02): meet dezelfde waarden in de officiële
                            upstream-APK's (alle varianten van dezelfde versie, sha256-gepind in
                            `app_identiteit.json`, zo nodig gedownload) en eist dat geen pakketnaam, authority,
                            permissie, accounttype, `app_search_suggest_*`-waarde of sharedpref-naam van de eigen
                            builds gelijk is aan een waarde van de officiële app
  xcode --instellingen <json>…  Swiftfin: uitvoer van `xcodebuild -showBuildSettings -json` (per schema en
                            configuratie, alleen op macOS te maken): elk app-doel heeft de eigen bundle-id; met
                            `--plist` ook `CFBundleIdentifier` in de Info.plist van de gebouwde app

Controles per APK/.ap_ (aapt2 `dump packagename`, `dump xmltree`, `dump resources`):
  - pakketnaam = eigen ID (+ `.debug` bij debug) en nooit een officiële ID;
  - elke provider-authority en elke zelf gedefinieerde `<permission>` begint met de pakketnaam (anders botsen ze met
    de officiële app: INSTALL_FAILED_CONFLICTING_PROVIDER / DUPLICATE_PERMISSION);
  - de sharedpref-namen in de back-upregels horen bij de pakketnaam (anders vallen instellingen buiten de back-up);
  - androidtv: `string/app_id` = pakketnaam, `app_search_suggest_authority` = pakketnaam + `.content`,
    `app_search_suggest_intent_data` = `content://` + die authority + `/intent`; het accounttype in
    `xml/authenticator` en de zoek-authority/-data in `xml/searchable` verwijzen (opgelost) naar precies die waarden,
    en de zoek-authority bestaat als provider in het manifest.

`bron` zoekt daarnaast in de manifesten, `res/xml` en de Kotlin/Java-bron van android en androidtv naar letterlijk
geschreven waarden van de officiële app (authority, permissie, accounttype, zoek-authority, `targetPackage`,
sharedpref-naam): die moeten van de applicationId afgeleid zijn (`${applicationId}`, `BuildConfig.APPLICATION_ID`,
`@string/app_id`), anders botst of verwijst de build naar de officiële app.

Sharedpref-namen die niet van een pakketnaam zijn afgeleid (`systemprefs`, `AuthenticationPreferences`) zijn per app
afgeschermd en mogen gelijk zijn aan die van de officiële app; `vergelijk` meldt ze apart (ADR-0012).

Exitcodes: 0 = in orde, 1 = overtreding, 3 = gebruiks- of omgevingsfout (bv. geen aapt2, niets gevonden).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from clients_common import DEFAULT_REPO_ROOT, ToolError  # noqa: E402

CONFIG_REL = "tools/clients/app_identiteit.json"
ANDROID_NS = "http://schemas.android.com/apk/res/android"
ANDROID_CLIENTS = ("android", "androidtv")
VARIANTEN = ("debug", "release")


# --------------------------------------------------------------------------------------------------------------------
# configuratie


def load_config(repo: Path) -> dict:
    path = repo / CONFIG_REL
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"configuratie onleesbaar: {path}: {exc}") from exc
    if data.get("schema_versie") != 1:
        raise ToolError(f"{CONFIG_REL}: onbekende schema_versie {data.get('schema_versie')!r}")
    return data


def config_violations(cfg: dict) -> list[str]:
    """De configuratie zelf: eigen ID's verschillen van elke officiële ID en van elkaar."""
    out: list[str] = []
    officieel = {o for key in (*ANDROID_CLIENTS, "swiftfin") for o in cfg[key]["officieel"]}
    eigen: list[str] = []
    for key in ANDROID_CLIENTS:
        c = cfg[key]
        for app_id in (c["application_id"], c["application_id"] + c["debug_suffix"]):
            eigen.append(app_id)
            if app_id in officieel:
                out.append(f"{key}: eigen ID '{app_id}' is een officiële ID")
        if c["application_id"] == c["namespace"]:
            out.append(f"{key}: application_id is gelijk aan de namespace (= de officiële ID)")
    eigen.append(cfg["swiftfin"]["bundle_id"])
    if cfg["swiftfin"]["bundle_id"] in officieel:
        out.append(f"swiftfin: bundle-id '{cfg['swiftfin']['bundle_id']}' is een officiële ID")
    dubbel = sorted({e for e in eigen[:-1] if eigen[:-1].count(e) > 1})
    if dubbel:
        out.append(f"eigen Android-ID's niet uniek: {', '.join(dubbel)}")
    return out


# --------------------------------------------------------------------------------------------------------------------
# bron (statisch)

GRADLE_NAMESPACE_RE = re.compile(r'^\s*namespace\s*=\s*"([^"]+)"', re.MULTILINE)
GRADLE_APPID_RE = re.compile(r"^\s*applicationId\s*=\s*(.+?)\s*$", re.MULTILINE)
GRADLE_RESVALUE_RE = re.compile(r'resValue\(\s*"string"\s*,\s*"(\w+)"\s*,\s*(.+)\)\s*$', re.MULTILINE)
XCCONFIG_BUNDLE_RE = re.compile(r"^\s*PRODUCT_BUNDLE_IDENTIFIER\s*=\s*(\S+)\s*$", re.MULTILINE)
PBX_BUNDLE_RE = re.compile(r"\bPRODUCT_BUNDLE_IDENTIFIER\s*=\s*\"?([^\";]+)\"?\s*;")


def _read(repo: Path, rel: str, out: list[str]) -> str | None:
    try:
        return (repo / rel).read_text(encoding="utf-8")
    except OSError as exc:
        out.append(f"{rel}: onleesbaar ({exc.strerror or exc})")
        return None


def sharedpref_paths(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    return [el.get("path", "") for el in root.iter() if el.tag in {"include", "exclude"}
            and el.get("domain") == "sharedpref" and el.get("path", "").endswith("_preferences")]


def expected_prefs(app_id: str, suffix: str) -> set[str]:
    return {f"{app_id}_preferences", f"{app_id}{suffix}_preferences"}


def check_backup_xml(label: str, xml_text: str, c: dict, out: list[str]) -> None:
    try:
        paths = sharedpref_paths(xml_text)
    except ET.ParseError as exc:
        out.append(f"{label}: geen geldige XML ({exc})")
        return
    verwacht = expected_prefs(c["application_id"], c["debug_suffix"])
    officieel = {f"{o}_preferences" for o in c["officieel"]}
    for path in paths:
        if path in officieel:
            out.append(f"{label}: sharedpref '{path}' hoort bij de officiële app")
        elif path not in verwacht:
            out.append(f"{label}: sharedpref '{path}' hoort niet bij '{c['application_id']}'")
    for naam in sorted(verwacht):
        if naam not in paths:
            out.append(f"{label}: sharedpref '{naam}' ontbreekt (instellingen vallen buiten de back-up)")


def check_gradle(key: str, text: str, c: dict, out: list[str]) -> None:
    rel = c["gradle"]
    namespaces = GRADLE_NAMESPACE_RE.findall(text)
    if namespaces != [c["namespace"]]:
        out.append(f"{rel}: namespace hoort ongewijzigd '{c['namespace']}' te zijn, gevonden {namespaces}")
    appids = GRADLE_APPID_RE.findall(text)
    if appids != [f'"{c["application_id"]}"']:
        out.append(f"{rel}: verwacht precies één 'applicationId = \"{c['application_id']}\"', gevonden {appids}")
    for name in c.get("res_waarden", []):
        exprs = [expr for n, expr in GRADLE_RESVALUE_RE.findall(text) if n == name]
        if len(exprs) != 2:
            out.append(f"{rel}: resValue '{name}' hoort precies 2× (release en debug) te staan, gevonden {len(exprs)}")
        for expr in exprs:
            if "namespace" in expr or "applicationId" not in expr:
                out.append(f"{rel}: resValue '{name}' = {expr} volgt de namespace (officiële ID) in plaats van de "
                           "applicationId")


MANIFEST_ATTRS = {"provider": ("authorities",), "permission": ("name",), "permission-tree": ("name",),
                  "permission-group": ("name",)}
RES_XML_ATTRS = ("accountType", "searchSuggestAuthority", "searchSuggestIntentData", "targetPackage", "authorities")
STRING_LITERAL_RE = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
APPID_PLACEHOLDER_RE = re.compile(r"^\$\{applicationId\}\.(?P<suffix>[\w.-]+)$")


def officiele_waarde(value: str, c: dict, suffixen: set[str] | None = None) -> str | None:
    """De officiële ID waar ``value`` letterlijk bij hoort, of ``None``.

    Hoort bij een officiële ID: gelijk eraan, of die ID gevolgd door ``.``/``_`` (authority, permissie,
    sharedpref ``<id>_preferences``). Waarden van de eigen ID (``org.jellyfin.mobile.jellyleon…``) tellen niet mee.
    Met ``suffixen`` (Kotlin/Java) telt alleen ``<id>``, ``<id>_preferences`` en ``<id>.<suffix>`` met een suffix
    uit het eigen manifest (bv. ``content``), zodat interne intent-namen (``org.jellyfin.mobile.intent.…``) vrij zijn.
    """
    value = value.removeprefix("content://")
    if value == c["application_id"] or value.startswith((c["application_id"] + ".", c["application_id"] + "_")):
        return None
    for o in sorted(c["officieel"], key=len, reverse=True):  # langste eerst: org.jellyfin.mobile.debug vóór …mobile
        if value in {o, f"{o}_preferences"}:
            return o
        if suffixen is None and value.startswith((o + ".", o + "_")):
            return o
        if suffixen is not None and value.startswith(o + "."):
            rest = value[len(o) + 1:]
            if any(rest == s or rest.startswith(s + "/") for s in suffixen):
                return o
    return None


def _xml_attrs(root: ET.Element, names: tuple[str, ...]) -> list[tuple[str, str, str]]:
    found = []
    for el in root.iter():
        for name in names:
            value = el.get(f"{{{ANDROID_NS}}}{name}")
            if value is not None:
                found.append((el.tag, name, value))
    return found


TEST_SETS = {"test", "androidTest", "testFixtures"}
OVERSLAAN = {"build", ".gradle", ".kotlin", "buildSrc"}


def bronsets(repo: Path, key: str) -> list[Path]:
    """Alle bronsets (``<module>/src/<set>``) van een client, alle Gradle-modules, zonder tests, bouwmappen en
    ``buildSrc`` (bouwlogica, komt niet in de app)."""
    base = repo / key
    found = []
    for src in sorted(base.rglob("src")):
        rel = src.relative_to(base).parts
        if not src.is_dir() or OVERSLAAN & set(rel):
            continue
        found += [d for d in sorted(src.iterdir()) if d.is_dir() and d.name not in TEST_SETS]
    return found


def check_letterlijk(repo: Path, key: str, c: dict, out: list[str]) -> None:
    """Letterlijk geschreven waarden van de officiële app in manifesten, res/xml en Kotlin/Java van alle modules
    (contract 1.3 §1.1 besluit 1). Testbronnen tellen niet mee."""
    sets = bronsets(repo, key)
    if not (repo / key / "app" / "src" / "main").is_dir():
        out.append(f"{key}/app/src/main ontbreekt (letterlijke waarden niet gecontroleerd)")
        return
    suffixen: set[str] = set()
    manifesten = [d / "AndroidManifest.xml" for d in sets if (d / "AndroidManifest.xml").is_file()]
    if repo / key / "app" / "src" / "main" / "AndroidManifest.xml" not in manifesten:
        out.append(f"{key}: geen {key}/app/src/main/AndroidManifest.xml (letterlijke waarden niet gecontroleerd)")
    for manifest in manifesten:
        rel = manifest.relative_to(repo).as_posix()
        try:
            root = ET.parse(manifest).getroot()
        except ET.ParseError as exc:
            out.append(f"{rel}: geen geldige XML ({exc})")
            continue
        for el in root.iter():
            for attr in MANIFEST_ATTRS.get(el.tag, ()):
                for value in filter(None, (el.get(f"{{{ANDROID_NS}}}{attr}") or "").split(";")):
                    m = APPID_PLACEHOLDER_RE.match(value)
                    if m:
                        suffixen.add(m.group("suffix"))
                    elif officiele_waarde(value, c):
                        out.append(f"{rel}: {el.tag} {attr}='{value}' is een waarde van de officiële app "
                                   "(gebruik ${applicationId})")
    for d in sets:
        for xml_file in sorted((d / "res").glob("xml*/*.xml")):
            rel = xml_file.relative_to(repo).as_posix()
            try:
                root = ET.parse(xml_file).getroot()
            except ET.ParseError as exc:
                out.append(f"{rel}: geen geldige XML ({exc})")
                continue
            for tag, attr, value in _xml_attrs(root, RES_XML_ATTRS):
                if not value.startswith("@") and officiele_waarde(value, c):
                    out.append(f"{rel}: {tag} {attr}='{value}' is een waarde van de officiële app (gebruik "
                               "@string/app_id of een resValue uit de applicationId)")
    for d in sets:
        for code in sorted([*d.rglob("*.kt"), *d.rglob("*.java")]):
            rel = code.relative_to(repo).as_posix()
            try:
                text = code.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                out.append(f"{rel}: onleesbaar ({exc})")
                continue
            for nr, line in enumerate(text.splitlines(), 1):
                for literal in STRING_LITERAL_RE.findall(line):
                    if officiele_waarde(literal, c, suffixen):
                        out.append(f"{rel}:{nr}: tekst \"{literal}\" is een waarde van de officiële app (gebruik "
                                   "BuildConfig.APPLICATION_ID of context.packageName)")


def check_bron(repo: Path, cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_config(repo)
    out = config_violations(cfg)
    for key in ANDROID_CLIENTS:
        c = cfg[key]
        text = _read(repo, c["gradle"], out)
        if text is not None:
            check_gradle(key, text, c, out)
        for rel in c["backup_xml"]:
            xml_text = _read(repo, rel, out)
            if xml_text is not None:
                check_backup_xml(rel, xml_text, c, out)
        check_letterlijk(repo, key, c, out)
    s = cfg["swiftfin"]
    for rel, regex in ((s["xcconfig"], XCCONFIG_BUNDLE_RE), (s["pbxproj"], PBX_BUNDLE_RE)):
        text = _read(repo, rel, out)
        if text is None:
            continue
        values = regex.findall(text)
        if not values:
            out.append(f"{rel}: geen PRODUCT_BUNDLE_IDENTIFIER gevonden")
        for value in values:
            if value != s["bundle_id"]:
                bron = "officiële bundle-id" if value in s["officieel"] else "andere waarde"
                out.append(f"{rel}: PRODUCT_BUNDLE_IDENTIFIER = {value} ({bron}); verwacht {s['bundle_id']}")
    return out


# --------------------------------------------------------------------------------------------------------------------
# aapt2


def find_aapt2(explicit: str | None = None) -> str:
    """--aapt2, dan $AAPT2, dan de hoogste build-tools-versie in $ANDROID_HOME/$ANDROID_SDK_ROOT, dan PATH."""
    if explicit:
        return explicit
    if os.environ.get("AAPT2"):
        return os.environ["AAPT2"]
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        sdk = os.environ.get(env)
        if not sdk:
            continue
        kandidaten = sorted((Path(sdk) / "build-tools").glob("*/aapt2"),
                            key=lambda p: [int(x) if x.isdigit() else -1 for x in re.split(r"[.-]", p.parent.name)])
        if kandidaten:
            return str(kandidaten[-1])
    found = shutil.which("aapt2")
    if found:
        return found
    raise ToolError("aapt2 niet gevonden: zet --aapt2, AAPT2 of ANDROID_HOME (build-tools)")


def run_aapt2(aapt2: str, *args: str) -> str:
    try:
        proc = subprocess.run([aapt2, *args], capture_output=True, text=True, check=False, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolError(f"aapt2 {' '.join(args[:2])} kon niet draaien: {exc}") from exc
    if proc.returncode != 0:
        raise ToolError(f"aapt2 {' '.join(args)} faalde (exit {proc.returncode}): {proc.stderr.strip()[:500]}")
    return proc.stdout


ELEMENT_RE = re.compile(r"^(?P<indent>\s*)E: (?P<tag>\S+)")
ATTR_RE = re.compile(r"^\s*A: (?:(?P<ns>\S+?):)?(?P<name>[A-Za-z_][\w.-]*)(?:\((?P<rid>0x[0-9a-f]+)\))?=(?P<val>.*)$")
QUOTED_RE = re.compile(r'^"((?:[^"\\]|\\.)*)"')
RESOURCE_RE = re.compile(r"^\s*resource (?P<rid>0x[0-9a-f]{8}) (?P<type>[\w-]+)/(?P<name>[\w.$-]+)")
VALUE_RE = re.compile(r"^\s+\((?P<cfg>[^)]*)\) (?P<val>.*)$")
FILE_RE = re.compile(r"^\(file\) (?P<path>\S+)")


@dataclass
class XmlElement:
    tag: str
    depth: int
    attrs: dict[str, str] = field(default_factory=dict)


def parse_attr_value(raw: str) -> str:
    raw = raw.strip()
    quoted = QUOTED_RE.match(raw)
    if quoted:
        # alleen de escapes die aapt2 in een tekenreeks zet (\" en \\); niets anders interpreteren (UTF-8 blijft heel)
        return re.sub(r'\\(["\\])', r"\1", quoted.group(1))
    return raw.split(" ", 1)[0]


def parse_xmltree(text: str) -> list[XmlElement]:
    """`aapt2 dump xmltree`: elementen met hun attributen (naam zonder namespace; verwijzingen als @0x…)."""
    elements: list[XmlElement] = []
    for line in text.splitlines():
        m = ELEMENT_RE.match(line)
        if m:
            elements.append(XmlElement(m.group("tag"), len(m.group("indent"))))
            continue
        a = ATTR_RE.match(line)
        if a and elements:
            elements[-1].attrs[a.group("name")] = parse_attr_value(a.group("val"))
    return elements


@dataclass
class Resources:
    by_id: dict[str, tuple[str, str]] = field(default_factory=dict)  # 0x… -> (type/naam, standaardwaarde)
    by_name: dict[str, str] = field(default_factory=dict)  # type/naam -> standaardwaarde
    files: dict[str, str] = field(default_factory=dict)  # type/naam -> pad in het archief


def parse_resources(text: str) -> Resources:
    """`aapt2 dump resources`: standaardwaarde (configuratie `()`) per resource, plus het pad van XML-bestanden."""
    res = Resources()
    current: tuple[str, str] | None = None
    for line in text.splitlines():
        r = RESOURCE_RE.match(line)
        if r:
            current = (r.group("rid"), f"{r.group('type')}/{r.group('name')}")
            continue
        v = VALUE_RE.match(line)
        if not (v and current) or v.group("cfg") != "":
            continue
        rid, name = current
        raw = v.group("val").strip()
        f = FILE_RE.match(raw)
        if f:
            res.files[name] = f.group("path")
            value = f.group("path")
        else:
            value = parse_attr_value(raw)
        res.by_id.setdefault(rid, (name, value))
        res.by_name.setdefault(name, value)
    return res


def resolve(res: Resources, value: str, depth: int = 0) -> str:
    """Volgt @0x…-verwijzingen (ook ketens) naar de standaardwaarde; onbekend blijft de verwijzing zelf."""
    if value.startswith("@0x") and depth < 10 and value[1:] in res.by_id:
        return resolve(res, res.by_id[value[1:]][1], depth + 1)
    return value


@dataclass
class ApkResult:
    pad: str
    client: str
    variant: str
    pakket: str = ""
    authorities: list[str] = field(default_factory=list)
    permissies: list[str] = field(default_factory=list)
    res_waarden: dict[str, str] = field(default_factory=dict)
    sharedprefs: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


def variant_from_name(path: Path) -> str | None:
    name = path.name.lower()
    hits = [v for v in VARIANTEN if v in name]
    return hits[0] if len(hits) == 1 else None


def check_apk(cfg: dict, client: str, path: Path, aapt2: str, variant: str | None = None) -> ApkResult:
    if client not in ANDROID_CLIENTS:
        raise ToolError(f"onbekende Android-client '{client}' (kies uit {', '.join(ANDROID_CLIENTS)})")
    if not path.is_file():
        raise ToolError(f"bestand bestaat niet: {path}")
    variant = variant or variant_from_name(path)
    if variant not in VARIANTEN:
        raise ToolError(f"{path.name}: variant (debug/release) niet uit de naam af te leiden; geef --variant")
    c = cfg[client]
    expected = c["application_id"] + (c["debug_suffix"] if variant == "debug" else "")
    result = ApkResult(str(path), client, variant)
    out = result.violations

    result.pakket = run_aapt2(aapt2, "dump", "packagename", str(path)).strip()
    pkg = result.pakket
    if pkg in c["officieel"]:
        out.append(f"pakketnaam '{pkg}' is de officiële app (botst bij installatie naast de officiële app)")
    elif pkg != expected:
        out.append(f"pakketnaam '{pkg}', verwacht '{expected}' ({variant})")

    manifest = parse_xmltree(run_aapt2(aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", str(path)))
    manifest_pkg = next((e.attrs.get("package") for e in manifest if e.tag == "manifest"), None)
    if manifest_pkg != pkg:
        out.append(f"manifest-package '{manifest_pkg}' wijkt af van de pakketnaam '{pkg}'")
    for el in manifest:
        if el.tag == "provider":
            for auth in filter(None, el.attrs.get("authorities", "").split(";")):
                result.authorities.append(auth)
                if not auth.startswith(pkg + "."):
                    out.append(f"provider-authority '{auth}' begint niet met '{pkg}.' (kan botsen met een andere app)")
        elif el.tag == "permission":
            name = el.attrs.get("name", "")
            result.permissies.append(name)
            if not name.startswith(pkg + "."):
                out.append(f"eigen permissie '{name}' begint niet met '{pkg}.' (DUPLICATE_PERMISSION naast de "
                           "officiële app)")
    if not result.authorities:
        out.append("geen enkele provider-authority gevonden in het manifest (onverwacht; controle niet bewezen)")

    res = parse_resources(run_aapt2(aapt2, "dump", "resources", str(path)))
    backup_files = [n for n in ("xml/backup_content", "xml/backup_rules") if n in res.files]
    if not backup_files:
        out.append("geen back-upregels (xml/backup_content) gevonden")
    base = pkg[: -len(c["debug_suffix"])] if variant == "debug" and pkg.endswith(c["debug_suffix"]) else pkg
    for name in backup_files:
        tree = parse_xmltree(run_aapt2(aapt2, "dump", "xmltree", "--file", res.files[name], str(path)))
        alle = [e.attrs.get("path", "") for e in tree
                if e.tag in {"include", "exclude"} and e.attrs.get("domain") == "sharedpref"]
        result.sharedprefs = list(dict.fromkeys([*result.sharedprefs, *filter(None, alle)]))
        # dict.fromkeys: backup_rules noemt elke naam per sectie (cloud-backup, device-transfer); één melding per naam
        paths = list(dict.fromkeys(e.attrs.get("path", "") for e in tree
                                   if e.tag == "include" and e.attrs.get("domain") == "sharedpref"
                                   and e.attrs.get("path", "").endswith("_preferences")))
        if f"{pkg}_preferences" not in paths:
            out.append(f"{name}: sharedpref '{pkg}_preferences' ontbreekt (gevonden: {paths})")
        for p in paths:
            if p not in expected_prefs(base, c["debug_suffix"]):
                out.append(f"{name}: sharedpref '{p}' hoort niet bij '{pkg}'")

    if client == "androidtv":
        verwacht = {"app_id": pkg, "app_search_suggest_authority": f"{pkg}.content",
                    "app_search_suggest_intent_data": f"content://{pkg}.content/intent"}
        for name, value in verwacht.items():
            actual = resolve(res, res.by_name.get(f"string/{name}", ""))
            result.res_waarden[name] = actual
            if actual != value:
                out.append(f"string/{name} = '{actual}', verwacht '{value}'")
        zoek = result.res_waarden["app_search_suggest_authority"]
        if zoek not in result.authorities:
            out.append(f"zoek-authority '{zoek}' bestaat niet als provider in het manifest (zoeksuggesties wijzen "
                       "naar een andere app of naar niets)")
        for xml_name, attr, key in (("xml/authenticator", "accountType", "app_id"),
                                    ("xml/searchable", "searchSuggestAuthority", "app_search_suggest_authority"),
                                    ("xml/searchable", "searchSuggestIntentData", "app_search_suggest_intent_data")):
            if xml_name not in res.files:
                out.append(f"{xml_name} ontbreekt in het archief")
                continue
            tree = parse_xmltree(run_aapt2(aapt2, "dump", "xmltree", "--file", res.files[xml_name], str(path)))
            raw = next((e.attrs[attr] for e in tree if attr in e.attrs), "")
            actual = resolve(res, raw)
            result.res_waarden[f"{xml_name}:{attr}"] = actual
            if actual != verwacht[key]:
                out.append(f"{xml_name} {attr} = '{actual}' (ruw {raw!r}), verwacht '{verwacht[key]}'")
    return result


LINKED_DIRS = ("linked_resources_binary_format", "linked_resources_proto_format")  # voorkeur: binair


def find_artifacts(build_dir: Path) -> list[tuple[Path, str]]:
    """APK's uit outputs/apk; zonder release-APK de gelinkte resources (*.ap_) van elke release-variant.

    De `*.ap_` van `process<Variant>Resources` bevat het samengevoegde manifest en de resources (zonder code); bij
    resource-shrinking (android release) maakt AGP die alleen in proto-formaat, dat aapt2 ook leest. Per variantmap
    (`release`, `libreRelease`, …) telt één archief, het binaire als dat er is.
    """
    found: list[tuple[Path, str]] = []
    for apk in sorted((build_dir / "outputs" / "apk").rglob("*.apk")):
        variant = variant_from_name(apk)
        if variant:
            found.append((apk, variant))
    if not any(v == "release" for _p, v in found):
        per_variant: dict[str, Path] = {}
        for sub in LINKED_DIRS:
            base = build_dir / "intermediates" / sub
            for ap in sorted(base.rglob("*.ap_")):
                variant_dir = ap.relative_to(base).parts[0]
                if variant_from_name(ap) == "release":
                    per_variant.setdefault(variant_dir, ap)
        found += [(ap, "release") for _v, ap in sorted(per_variant.items())]
    return found


# --------------------------------------------------------------------------------------------------------------------
# vergelijking met de officiële app (contract 1.3 §1.1 besluit 1, C1.3-JLC-02)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def identiteitswaarden(r: ApkResult) -> dict[str, set[str]]:
    """De waarden waarmee twee apps op één apparaat kunnen botsen of naar elkaar kunnen verwijzen."""
    waarden = {
        "pakketnaam": {r.pakket},
        "authority": set(r.authorities),
        "permissie": set(r.permissies),
        "accounttype": {v for k, v in r.res_waarden.items() if k in {"app_id", "xml/authenticator:accountType"}},
        "app_search_suggest": {v for k, v in r.res_waarden.items()
                               if k.startswith("app_search_suggest_") or k.startswith("xml/searchable:")},
        "sharedpref": set(r.sharedprefs),
    }
    return {k: {x for x in v if x} for k, v in waarden.items()}


def sha256_bestand(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for blok in iter(lambda: fh.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def officiele_apks(cfg: dict, client: str) -> list[dict]:
    lijst = cfg[client].get("officiele_apks") or []
    if not lijst:
        raise ToolError(f"{CONFIG_REL}: {client} heeft geen officiele_apks (niets om mee te vergelijken)")
    for a in lijst:
        if a.get("variant") not in VARIANTEN or not SHA256_RE.match(str(a.get("sha256", ""))) \
                or not str(a.get("url", "")).startswith("https://github.com/jellyfin/") \
                or Path(str(a.get("naam", ""))).name != a.get("naam") or not str(a["naam"]).endswith(".apk"):
            raise ToolError(f"{CONFIG_REL}: {client}: ongeldige officiele_apks-regel {a!r}")
    return lijst


def haal_officiele_apk(a: dict, map_: Path, download: bool = True) -> Path:
    """Officiële upstream-APK uit ``map_`` of via download; altijd sha256-gecontroleerd, atomair hernoemd."""
    map_.mkdir(parents=True, exist_ok=True)
    doel = map_ / a["naam"]
    if doel.is_file() and sha256_bestand(doel) == a["sha256"]:
        return doel
    if not download:
        raise ToolError(f"{doel} ontbreekt of heeft een andere sha256 (download uitgezet)")
    tijdelijk = doel.with_name(doel.name + ".deel")
    try:
        with urllib.request.urlopen(a["url"], timeout=300) as r, tijdelijk.open("wb") as fh:  # noqa: S310 - vaste URL
            shutil.copyfileobj(r, fh)
    except OSError as exc:
        tijdelijk.unlink(missing_ok=True)
        raise ToolError(f"download van {a['url']} mislukt: {exc}") from exc
    gemeten = sha256_bestand(tijdelijk)
    if gemeten != a["sha256"]:
        tijdelijk.unlink(missing_ok=True)
        raise ToolError(f"{a['naam']}: sha256 {gemeten} ≠ vastgelegde {a['sha256']}; niet gebruikt")
    tijdelijk.replace(doel)
    return doel


@dataclass
class Vergelijking:
    officieel: list[ApkResult]
    eigen: list[ApkResult]
    gelijk_toegestaan: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


def vergelijk_met_officieel(cfg: dict, client: str, eigen: list[ApkResult],
                            officieel: list[ApkResult]) -> Vergelijking:
    """Geen enkele identiteitswaarde van een eigen build is gelijk aan een waarde uit een officiële build.

    Vergeleken wordt over alle soorten heen (een eigen authority mag ook geen officieel accounttype zijn). Een gelijke
    sharedpref-naam die niet van een pakketnaam is afgeleid (`systemprefs`) is per app afgeschermd: toegestaan, wel
    gemeld. De officiële meting moet zelf bruikbaar zijn (officiële pakketnaam, authorities gemeten).
    """
    c = cfg[client]
    v = Vergelijking(officieel, eigen)
    if not officieel or not eigen:
        raise ToolError("vergelijking zonder officiële of eigen artefacten bewijst niets")
    for r in officieel:
        if r.pakket not in c["officieel"]:
            raise ToolError(f"{r.pad}: pakketnaam '{r.pakket}' is geen officiële ID {c['officieel']} (verkeerde APK?)")
        if not r.authorities:
            raise ToolError(f"{r.pad}: geen authorities gemeten in de officiële APK (meting onbruikbaar)")
    gemeten = {o.pakket for o in officieel}
    if gemeten != set(c["officieel"]):
        raise ToolError(f"officiële meting dekt niet alle officiële ID's: gemeten {sorted(gemeten)}, verwacht "
                        f"{sorted(c['officieel'])}")
    officieel_per_waarde: dict[str, set[str]] = {}
    for o in officieel:
        for soort, waarden in identiteitswaarden(o).items():
            for w in waarden:
                officieel_per_waarde.setdefault(w, set()).add(f"{soort} van {o.pakket}")
    for r in eigen:
        for soort, waarden in identiteitswaarden(r).items():
            for w in sorted(waarden):
                if w not in officieel_per_waarde:
                    continue
                bron = ", ".join(sorted(officieel_per_waarde[w]))
                if soort == "sharedpref" and not any(o in w for o in c["officieel"]):
                    v.gelijk_toegestaan.append(f"{r.variant} {r.pakket}: sharedpref '{w}' ({bron}) — per app "
                                               "afgeschermd, niet van een pakketnaam afgeleid")
                else:
                    v.violations.append(f"{r.variant} {r.pakket}: {soort} '{w}' is gelijk aan {bron}")
    return v


# --------------------------------------------------------------------------------------------------------------------
# Swiftfin (Xcode-instellingen, gemaakt op een macOS-runner)


def load_build_settings(path: Path) -> list[dict]:
    """`xcodebuild -showBuildSettings -json`; eventuele tekst vóór de JSON-lijst wordt overgeslagen."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ToolError(f"{path}: onleesbaar ({exc.strerror or exc})") from exc
    start = text.find("[")
    try:
        data = json.loads(text[start:]) if start >= 0 else None
    except json.JSONDecodeError as exc:
        raise ToolError(f"{path}: geen JSON van xcodebuild -showBuildSettings ({exc})") from exc
    if not isinstance(data, list):
        raise ToolError(f"{path}: verwacht een JSON-lijst van xcodebuild -showBuildSettings -json")
    return data


def check_xcode(cfg: dict, files: list[Path], plist: bool = False) -> tuple[list[dict], list[str]]:
    s = cfg["swiftfin"]
    report: list[dict] = []
    out: list[str] = []
    plists = 0
    for path in files:
        apps = [e for e in load_build_settings(path)
                if (e.get("buildSettings") or {}).get("WRAPPER_EXTENSION") == "app"]
        if not apps:
            out.append(f"{path.name}: geen app-doel in de build-instellingen (controle niet bewezen)")
        for entry in apps:
            bs = entry["buildSettings"]
            target = entry.get("target", "?")
            row = {"bestand": path.name, "doel": target, "configuratie": bs.get("CONFIGURATION", "?"),
                   "platform": bs.get("PLATFORM_NAME", "?"), "bundle_id": bs.get("PRODUCT_BUNDLE_IDENTIFIER", "")}
            report.append(row)
            if row["bundle_id"] in s["officieel"]:
                out.append(f"{target} ({row['configuratie']}): officiële bundle-id {row['bundle_id']}")
            elif row["bundle_id"] != s["bundle_id"]:
                out.append(f"{target} ({row['configuratie']}): bundle-id '{row['bundle_id']}', verwacht "
                           f"'{s['bundle_id']}'")
            info = Path(bs.get("TARGET_BUILD_DIR", "")) / bs.get("INFOPLIST_PATH", "")
            if plist and bs.get("INFOPLIST_PATH") and info.is_file():
                plists += 1
                with info.open("rb") as fh:
                    row["CFBundleIdentifier"] = plistlib.load(fh).get("CFBundleIdentifier")
                if row["CFBundleIdentifier"] != s["bundle_id"]:
                    out.append(f"{info}: CFBundleIdentifier '{row['CFBundleIdentifier']}', verwacht "
                               f"'{s['bundle_id']}'")
    if plist and plists == 0:
        out.append("--plist: geen Info.plist van een gebouwde app gevonden (eerst bouwen; niets gecontroleerd is "
                   "geen bewijs)")
    return report, out


# --------------------------------------------------------------------------------------------------------------------
# CLI


def print_apk(result: ApkResult) -> None:
    print(f"{result.client} {result.variant}: {result.pad}")
    print(f"  pakket {result.pakket}; authorities {', '.join(result.authorities) or '-'}")
    if result.permissies:
        print(f"  eigen permissies {', '.join(result.permissies)}")
    for key, value in result.res_waarden.items():
        print(f"  {key} = {value}")
    for v in result.violations:
        print(f"  OVERTREDING: {v}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--json", action="store_true", help="resultaat als JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bron", help="statische controle van de bron (geen SDK nodig)")
    p_apk = sub.add_parser("apk", help="aapt2-controle van APK's of *.ap_")
    p_apk.add_argument("client", choices=ANDROID_CLIENTS)
    p_apk.add_argument("bestanden", nargs="+", type=Path)
    p_apk.add_argument("--variant", choices=VARIANTEN)
    p_apk.add_argument("--aapt2")
    p_map = sub.add_parser("bouwmap", help="alle APK's en release-*.ap_ in een Gradle-bouwmap controleren")
    p_map.add_argument("client", choices=ANDROID_CLIENTS)
    p_map.add_argument("map", type=Path)
    p_map.add_argument("--verwacht", default="debug,release",
                       help="varianten die minstens één keer gevonden moeten worden (standaard debug,release)")
    p_map.add_argument("--aapt2")
    p_v = sub.add_parser("vergelijk", help="eigen builds tegen de officiële upstream-APK's (contract 1.3 §1.1)")
    p_v.add_argument("client", choices=ANDROID_CLIENTS)
    p_v.add_argument("map", type=Path, help="Gradle-bouwmap van de eigen build (<client>/app/build)")
    p_v.add_argument("--officieel-map", type=Path, required=True,
                     help="map voor de officiële APK's (hergebruikt bij gelijke sha256, anders gedownload)")
    p_v.add_argument("--geen-download", action="store_true", help="niet downloaden; ontbreken = gebruiksfout")
    p_v.add_argument("--verwacht", default="debug,release")
    p_v.add_argument("--aapt2")
    p_x = sub.add_parser("xcode", help="Swiftfin: bundle-id uit xcodebuild -showBuildSettings -json")
    p_x.add_argument("--instellingen", type=Path, action="append", required=True)
    p_x.add_argument("--plist", action="store_true", help="ook CFBundleIdentifier in de gebouwde app")
    args = parser.parse_args(argv)
    repo = args.repo_root.resolve()
    try:
        cfg = load_config(repo)
        if args.cmd == "bron":
            violations = check_bron(repo, cfg)
            if args.json:
                print(json.dumps({"in_orde": not violations, "overtredingen": violations}, indent=2,
                                 ensure_ascii=False))
            else:
                for v in violations:
                    print(f"OVERTREDING: {v}")
                if not violations:
                    print("App-identiteit in de bron in orde: "
                          f"android {cfg['android']['application_id']}, androidtv "
                          f"{cfg['androidtv']['application_id']}, swiftfin {cfg['swiftfin']['bundle_id']} "
                          "(alle verschillend van de officiële ID's; namespaces ongewijzigd).")
            return 1 if violations else 0
        if args.cmd == "xcode":
            report, violations = check_xcode(cfg, args.instellingen, args.plist)
            if args.json:
                print(json.dumps({"in_orde": not violations, "doelen": report, "overtredingen": violations},
                                 indent=2, ensure_ascii=False))
            else:
                for row in report:
                    print(f"{row['doel']:<16} {row['configuratie']:<8} {row['platform']:<18} {row['bundle_id']}"
                          + (f"  (Info.plist: {row['CFBundleIdentifier']})" if "CFBundleIdentifier" in row else ""))
                for v in violations:
                    print(f"OVERTREDING: {v}")
                print(f"{len(report)} app-doel(en) gecontroleerd, {len(violations)} overtreding(en).")
            return 1 if violations else 0

        aapt2 = find_aapt2(args.aapt2)
        if args.cmd == "apk":
            targets = [(p, args.variant) for p in args.bestanden]
        else:
            targets = find_artifacts(args.map)
            gevonden = {v for _p, v in targets}
            nodig = {v.strip() for v in args.verwacht.split(",") if v.strip()}
            if not nodig <= set(VARIANTEN):
                raise ToolError(f"--verwacht: onbekende variant in {sorted(nodig)}")
            if not nodig <= gevonden:
                raise ToolError(f"{args.map}: geen artefact voor {', '.join(sorted(nodig - gevonden))} gevonden "
                                "(eerst bouwen; niets gecontroleerd is geen bewijs)")
        results = [check_apk(cfg, args.client, path, aapt2, variant) for path, variant in targets]
        if args.cmd == "vergelijk":
            officieel = [check_apk(cfg, args.client, haal_officiele_apk(a, args.officieel_map, not args.geen_download),
                                   aapt2, a["variant"]) for a in officiele_apks(cfg, args.client)]
            vergelijking = vergelijk_met_officieel(cfg, args.client, results, officieel)
    except ToolError as exc:
        print(f"FOUT: {exc}", file=sys.stderr)
        return 3
    if args.cmd == "vergelijk":
        if args.json:
            print(json.dumps({"in_orde": not vergelijking.violations,
                              "officieel": [{"pad": o.pad, "pakket": o.pakket, **{k: sorted(w) for k, w in
                                             identiteitswaarden(o).items()}} for o in vergelijking.officieel],
                              "eigen": [{"pad": r.pad, "pakket": r.pakket, **{k: sorted(w) for k, w in
                                         identiteitswaarden(r).items()}} for r in vergelijking.eigen],
                              "gelijk_toegestaan": vergelijking.gelijk_toegestaan,
                              "overtredingen": vergelijking.violations}, indent=2, ensure_ascii=False))
        else:
            print(f"aapt2: {aapt2}")
            for o in vergelijking.officieel:
                w = identiteitswaarden(o)
                print(f"officieel {o.variant}: {Path(o.pad).name} — {o.pakket}; "
                      + "; ".join(f"{k} {len(v)}" for k, v in w.items()))
            for r in vergelijking.eigen:
                w = identiteitswaarden(r)
                print(f"eigen {r.variant}: {Path(r.pad).name} — {r.pakket}; "
                      + "; ".join(f"{k} {len(v)}" for k, v in w.items()))
            for g in vergelijking.gelijk_toegestaan:
                print(f"  gelijk, toegestaan: {g}")
            for v in vergelijking.violations:
                print(f"OVERTREDING: {v}")
            print(f"\n{len(vergelijking.eigen)} eigen artefact(en) tegen {len(vergelijking.officieel)} officiële "
                  f"APK('s): {len(vergelijking.violations)} gelijke identiteitswaarde(n).")
        return 1 if vergelijking.violations else 0
    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2, ensure_ascii=False))
    else:
        print(f"aapt2: {aapt2}")
        for r in results:
            print_apk(r)
        fout = sum(len(r.violations) for r in results)
        print(f"\n{len(results)} artefact(en) gecontroleerd, {fout} overtreding(en).")
    return 1 if any(r.violations for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
