#!/usr/bin/env python3
"""Statische vergelijking: welke REST-routes van de Jellyfin-server die een client via jellyfin-sdk-kotlin aanroept,
bestaan niet (meer) in een andere serverversie? (ADR-0009: Android-clients controleren vóór de serverupgrade naar 12.x.)

Invoer zijn uitsluitend lokale mappen (alleen gelezen, niets uitgevoerd):

- ``--server-a`` / ``--server-b``: ``Jellyfin.Api/Controllers`` van twee serverversies (bv. v10.11.11 en v12.4);
- ``--sdk-ops``: ``jellyfin-api/src/commonMain/kotlin-generated/org/jellyfin/sdk/api/operations`` van de
  jellyfin-sdk-kotlin-versie die de client gebruikt (android/androidtv: zie ``gradle/libs.versions.toml``);
- ``--client naam=map[,map…]``: Kotlin-bronmappen van een client.

Werkwijze: routes uit de ASP.NET-attributen (``[Route]`` op de klasse, standaard ``[controller]`` van
``BaseJellyfinApiController``; ``[HttpGet("…")]`` enz. op methoden), padparameters genormaliseerd naar ``{}``, alles in
kleine letters (ASP.NET-routing is hoofdletterongevoelig). SDK-functies worden gekoppeld aan hun (methode, pad);
URL-bouwers (``api.createUrl``) tellen als ontbrekend alleen als het pad onder géén methode meer bestaat. Daarna wordt
in de clientbronnen gezocht naar aanroepen van die SDK-functies.

Grenzen (bewust, staat ook in de uitvoer): alleen het bestaan van routes. Niet gezien worden gewijzigde parameters,
DTO-velden, enum-waarden, authenticatie, gedrag, routes die alleen via conventies of ``[AcceptVerbs]`` bestaan,
en clientcode die URL's zelf samenstelt of de web-client van de server gebruikt (android). Een lege uitkomst is dus
**geen** bewijs van compatibiliteit; dat vraagt een echte test tegen een server van die versie.

Exitcodes: 0 = geen gebruikte route ontbreekt, 1 = minstens één client roept een ontbrekende route aan,
2 = ongeldige invoer.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HTTP_ATTR_RE = re.compile(r"\[\s*Http(Get|Post|Delete|Put|Patch|Head)\s*(?:\(\s*\"([^\"]*)\"[^)\]]*\))?")
CLASS_ROUTE_RE = re.compile(r"^\s*\[\s*Route\s*\(\s*\"([^\"]*)\"\s*\)\s*\]")
CLASS_RE = re.compile(r"^\s*public\s+(?:(?:sealed|partial|abstract)\s+)*class\s+(\w+?)Controller\b")
SDK_FUN_RE = re.compile(r"public\s+(?:suspend\s+)?fun\s+(\w+)\s*\(")
SDK_REQUEST_RE = re.compile(r"api\.`?(get|post|delete|put|patch)`?<.*?>\(\s*\"([^\"]+)\"")
SDK_URL_RE = re.compile(r"api\.createUrl\(\s*\"([^\"]+)\"")
URL_METHOD = "URL"
GRENZEN = (
    "Statisch en alleen op routeniveau: gewijzigde parameters, DTO-velden, enums, authenticatie en gedrag worden "
    "niet gezien, evenmin zelf samengestelde URL's of de web-client van de server. Een lege uitkomst bewijst geen "
    "compatibiliteit."
)


def normalize_path(path: str) -> str:
    """'/Users/{userId:guid}/Items/' -> '/users/{}/items'."""
    path = path.strip()
    if path.startswith("~/"):
        path = path[1:]
    path = re.sub(r"\{[^}]*\}", "{}", path.strip("/"))
    return "/" + path.lower()


def server_routes(controllers: Path) -> set[tuple[str, str]]:
    """Alle (METHODE, pad) uit de controllers van één serverversie."""
    routes: set[tuple[str, str]] = set()
    for source in sorted(controllers.rglob("*.cs")):
        prefix: str | None = None
        controller: str | None = None
        for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
            if controller is None:
                class_route = CLASS_ROUTE_RE.search(line)
                if class_route:
                    prefix = class_route.group(1)
                    continue
                cls = CLASS_RE.search(line)
                if cls:
                    controller = cls.group(1)
                    # Zonder eigen [Route] erft een controller [Route("[controller]")] van BaseJellyfinApiController.
                    prefix = (prefix if prefix is not None else "[controller]").replace("[controller]", controller)
                continue
            for attr in HTTP_ATTR_RE.finditer(line):
                template = attr.group(2) or ""
                absolute = template.startswith(("/", "~/"))
                full = template if absolute or not prefix else f"{prefix}/{template}"
                routes.add((attr.group(1).upper(), normalize_path(full)))
    return routes


def sdk_endpoints(operations: Path) -> dict[tuple[str, str], set[str]]:
    """(METHODE of URL, pad) -> {'KlasseApi.functie', …} uit de gegenereerde SDK-bronnen."""
    endpoints: dict[tuple[str, str], set[str]] = {}
    for source in sorted(operations.glob("*.kt")):
        function: str | None = None
        for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
            fun = SDK_FUN_RE.search(line)
            if fun:
                function = fun.group(1)
            if function is None:
                continue
            request = SDK_REQUEST_RE.search(line)
            if request:
                key = (request.group(1).upper(), normalize_path(request.group(2)))
                endpoints.setdefault(key, set()).add(f"{source.stem}.{function}")
            url = SDK_URL_RE.search(line)
            if url:
                endpoints.setdefault((URL_METHOD, normalize_path(url.group(1))), set()).add(f"{source.stem}.{function}")
    return endpoints


def missing_endpoints(endpoints: dict[tuple[str, str], set[str]],
                      routes_b: set[tuple[str, str]]) -> dict[tuple[str, str], set[str]]:
    paths_b = {path for _, path in routes_b}
    missing = {}
    for (method, path), functions in endpoints.items():
        gone = path not in paths_b if method == URL_METHOD else (method, path) not in routes_b
        if gone:
            missing[(method, path)] = functions
    return missing


def client_usages(source_dirs: list[Path], missing: dict[tuple[str, str], set[str]], root: Path) -> list[dict]:
    texts = []
    for directory in source_dirs:
        for source in sorted(directory.rglob("*.kt")):
            texts.append((source, source.read_text(encoding="utf-8", errors="replace")))
    used = []
    for (method, path), functions in sorted(missing.items()):
        hits: set[str] = set()
        for qualified in functions:
            name = qualified.split(".", 1)[1]
            pattern = re.compile(rf"\b{re.escape(name)}\s*\(")
            hits.update(display_path(src, root) for src, text in texts if pattern.search(text))
        if hits:
            used.append({"methode": method, "pad": path, "sdk_functies": sorted(functions),
                         "gebruikt_in": sorted(hits)})
    return used


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def compare(server_a: Path, server_b: Path, sdk_ops: Path, clients: dict[str, list[Path]], root: Path) -> dict:
    routes_a, routes_b = server_routes(server_a), server_routes(server_b)
    endpoints = sdk_endpoints(sdk_ops)
    missing = missing_endpoints(endpoints, routes_b)
    return {
        "routes_server_a": len(routes_a),
        "routes_server_b": len(routes_b),
        "routes_weg_in_b": sorted(f"{m} {p}" for m, p in routes_a - routes_b),
        "routes_nieuw_in_b": len(routes_b - routes_a),
        "sdk_endpoints": len(endpoints),
        "sdk_endpoints_ontbrekend_in_b": sorted(f"{m} {p}" for m, p in missing),
        "per_client": {name: client_usages(dirs, missing, root) for name, dirs in clients.items()},
        "grenzen": GRENZEN,
    }


def parse_client(value: str) -> tuple[str, list[Path]]:
    name, sep, dirs = value.partition("=")
    if not sep or not name or not dirs:
        raise argparse.ArgumentTypeError(f"verwacht naam=map[,map…], kreeg {value!r}")
    return name, [Path(d) for d in dirs.split(",") if d]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--server-a", type=Path, required=True, help="Jellyfin.Api/Controllers van de huidige server")
    parser.add_argument("--server-b", type=Path, required=True, help="Jellyfin.Api/Controllers van de doelserver")
    parser.add_argument("--sdk-ops", type=Path, required=True, help="operations-map van jellyfin-sdk-kotlin")
    parser.add_argument("--client", type=parse_client, action="append", default=[], help="naam=map[,map…]")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="paden in de uitvoer relatief hieraan")
    args = parser.parse_args(argv)

    for label, directory in (("--server-a", args.server_a), ("--server-b", args.server_b),
                             ("--sdk-ops", args.sdk_ops), *((f"--client {n}", d) for n, ds in args.client for d in ds)):
        if not directory.is_dir():
            print(f"fout: {label}: map {directory} bestaat niet", file=sys.stderr)
            return 2
    result = compare(args.server_a, args.server_b, args.sdk_ops, dict(args.client), args.root)
    if result["routes_server_a"] == 0 or result["routes_server_b"] == 0 or result["sdk_endpoints"] == 0:
        print("fout: geen routes of SDK-endpoints gevonden (verkeerde map?)", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if any(result["per_client"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
