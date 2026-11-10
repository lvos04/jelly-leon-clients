"""Tests voor server_api_compat.py met nep-controllers, nep-SDK-bronnen en nep-clientbronnen (Sim-getest)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import server_api_compat as sac

BASE_CONTROLLER = """
[ApiController]
[Route("[controller]")]
public class BaseJellyfinApiController : ControllerBase
{
}
"""


def controller(name: str, body: str, route: str | None = None) -> str:
    head = f'[Route("{route}")]\n' if route is not None else ""
    return f"{head}[Authorize]\npublic class {name}Controller : BaseJellyfinApiController\n{{\n{body}\n}}\n"


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


@pytest.fixture
def opstelling(tmp_path: Path) -> dict[str, Path]:
    server_a, server_b = tmp_path / "srv-a", tmp_path / "srv-b"
    gemeenschappelijk = {
        "BaseJellyfinApiController.cs": BASE_CONTROLLER,
        "UserController.cs": controller("User", """
    [HttpGet("{userId}")]
    public ActionResult<UserDto> GetUserById([FromRoute] Guid userId) { }
    [HttpPost("AuthenticateByName")]
    public ActionResult Authenticate() { }
""", route="Users"),
    }
    write(server_a, {**gemeenschappelijk,
                     "HlsSegmentController.cs": controller("HlsSegment", """
    [HttpDelete("Videos/ActiveEncodings")]
    public ActionResult StopEncodingProcess() { }
    [HttpGet("Videos/{itemId}/hls/{playlistId}/stream.m3u8")]
    public ActionResult GetHlsPlaylistLegacy() { }
""", route=""),
                     "SystemController.cs": controller("System", """
    [HttpGet("Info/Public")]
    [HttpGet("/System/Ping")] [HttpPost("/System/Ping", Name = "PostPing")]
    public ActionResult Info() { }
""")})
    # Server B: StopEncodingProcess en de legacy-HLS-route zijn weg; System heeft dezelfde routes.
    write(server_b, {**gemeenschappelijk,
                     "HlsSegmentController.cs": controller("HlsSegment", """
    [HttpGet("Videos/{itemId:guid}/hls1/{playlistId}/{segmentId}.{container}")]
    public ActionResult GetHlsVideoSegment() { }
""", route=""),
                     "SystemController.cs": controller("System", """
    [HttpGet("info/public")]
    [HttpGet("~/System/Ping")]
    [HttpPost("/System/Ping")]
    public ActionResult Info() { }
""")})
    sdk = tmp_path / "sdk-ops"
    write(sdk, {
        "UserApi.kt": """
public class UserApi(private val api: ApiClient) : Api {
\tpublic suspend fun getUserById(userId: UUID): Response<UserDto> {
\t\tval response = api.`get`<UserDto>("/Users/{userId}", pathParameters, queryParameters, data)
\t}
\tpublic suspend fun authenticateUserByName(data: AuthenticateUserByName): Response<AuthenticationResult> {
\t\tval response = api.post<AuthenticationResult>("/Users/AuthenticateByName", pathParameters, queryParameters, data)
\t}
}
""",
        "HlsSegmentApi.kt": """
public class HlsSegmentApi(private val api: ApiClient) : Api {
\tpublic suspend fun stopEncodingProcess(deviceId: String, playSessionId: String): Response<Unit> {
\t\tval response = api.delete<Unit>("/Videos/ActiveEncodings", pathParameters, queryParameters, data)
\t}
\tpublic fun getHlsPlaylistLegacyUrl(itemId: UUID, playlistId: String): String {
\t\treturn api.createUrl("/Videos/{itemId}/hls/{playlistId}/stream.m3u8", pathParameters, queryParameters)
\t}
}
""",
        "SystemApi.kt": """
public class SystemApi(private val api: ApiClient) : Api {
\tpublic suspend fun getPublicSystemInfo(): Response<PublicSystemInfo> {
\t\tval response = api.`get`<PublicSystemInfo>("/System/Info/Public", pathParameters, queryParameters, data)
\t}
\tpublic fun postPingSystemUrl(): String {
\t\treturn api.createUrl("/System/Ping", pathParameters, queryParameters)
\t}
\tpublic suspend fun getItemsList(): Response<List<BaseItemDto>> {
\t\tval response = api.`get`<List<BaseItemDto>>("/Users/{id}", pathParameters, queryParameters, data)
\t}
}
""",
    })
    client = tmp_path / "client" / "src" / "main"
    write(client, {
        "PlaybackManager.kt": "fun stop() { api.hlsSegmentApi.stopEncodingProcess(api.deviceInfo.id, id) }\n",
        "Login.kt": "suspend fun login() { api.userApi.authenticateUserByName(AuthenticateUserByName(u, p)) }\n",
        "Ping.kt": "val url = api.systemApi.postPingSystemUrl()\n",
    })
    ander = tmp_path / "ander" / "src"
    write(ander, {"Alleen.kt": "suspend fun info() = api.systemApi.getPublicSystemInfo()\n"})
    return {"a": server_a, "b": server_b, "sdk": sdk, "client": client, "ander": ander, "root": tmp_path}


def test_normalisatie_padparameters_hoofdletters_en_tilde():
    assert sac.normalize_path("/Users/{userId:guid}/Items/") == "/users/{}/items"
    assert sac.normalize_path("~/System/Ping") == "/system/ping"
    assert sac.normalize_path("") == "/"


def test_routes_klasse_prefix_standaard_controller_en_absoluut(opstelling):
    routes = sac.server_routes(opstelling["a"])
    assert ("GET", "/users/{}") in routes
    assert ("POST", "/users/authenticatebyname") in routes
    assert ("DELETE", "/videos/activeencodings") in routes  # [Route("")] → geen prefix
    assert ("GET", "/system/info/public") in routes  # geen eigen [Route] → [controller] = System
    assert ("GET", "/system/ping") in routes and ("POST", "/system/ping") in routes  # absolute routes, 2 per regel
    assert not any(path.startswith("/basejellyfinapi") for _, path in routes)


def test_sdk_endpoints_get_met_backticks_generics_post_delete_en_url(opstelling):
    endpoints = sac.sdk_endpoints(opstelling["sdk"])
    assert endpoints[("GET", "/users/{}")] == {"UserApi.getUserById", "SystemApi.getItemsList"}
    assert endpoints[("POST", "/users/authenticatebyname")] == {"UserApi.authenticateUserByName"}
    assert endpoints[("DELETE", "/videos/activeencodings")] == {"HlsSegmentApi.stopEncodingProcess"}
    assert endpoints[("URL", "/videos/{}/hls/{}/stream.m3u8")] == {"HlsSegmentApi.getHlsPlaylistLegacyUrl"}


def test_vergelijking_vindt_verdwenen_routes_en_gebruik_per_client(opstelling):
    result = sac.compare(opstelling["a"], opstelling["b"], opstelling["sdk"],
                         {"client": [opstelling["client"]], "ander": [opstelling["ander"]]}, opstelling["root"])
    assert result["routes_weg_in_b"] == ["DELETE /videos/activeencodings", "GET /videos/{}/hls/{}/stream.m3u8"]
    assert result["routes_nieuw_in_b"] == 1
    assert result["sdk_endpoints_ontbrekend_in_b"] == ["DELETE /videos/activeencodings",
                                                       "URL /videos/{}/hls/{}/stream.m3u8"]
    gebruikt = result["per_client"]["client"]
    assert gebruikt == [{"methode": "DELETE", "pad": "/videos/activeencodings",
                         "sdk_functies": ["HlsSegmentApi.stopEncodingProcess"],
                         "gebruikt_in": ["client/src/main/PlaybackManager.kt"]}]
    # URL-bouwer voor een pad dat in B nog onder een (andere) methode bestaat telt niet als ontbrekend.
    assert "URL /system/ping" not in result["sdk_endpoints_ontbrekend_in_b"]
    assert result["per_client"]["ander"] == []
    assert "bewijst geen compatibiliteit" in result["grenzen"]


def test_cli_exitcodes_en_json(opstelling, capsys):
    base = ["--server-a", str(opstelling["a"]), "--server-b", str(opstelling["b"]), "--sdk-ops", str(opstelling["sdk"]),
            "--root", str(opstelling["root"])]
    assert sac.main([*base, "--client", f"client={opstelling['client']}"]) == 1
    uit = json.loads(capsys.readouterr().out)
    assert uit["per_client"]["client"][0]["pad"] == "/videos/activeencodings"
    assert sac.main([*base, "--client", f"ander={opstelling['ander']}"]) == 0
    capsys.readouterr()
    assert sac.main([*base, "--client", f"x={opstelling['root'] / 'bestaat-niet'}"]) == 2
    assert "bestaat niet" in capsys.readouterr().err


def test_cli_lege_map_is_ongeldige_invoer(opstelling, tmp_path, capsys):
    leeg = tmp_path / "leeg"
    leeg.mkdir()
    assert sac.main(["--server-a", str(leeg), "--server-b", str(opstelling["b"]), "--sdk-ops",
                     str(opstelling["sdk"])]) == 2
    assert "geen routes" in capsys.readouterr().err


def test_cli_ongeldige_clientparameter():
    with pytest.raises(SystemExit) as exc:
        sac.main(["--server-a", "a", "--server-b", "b", "--sdk-ops", "c", "--client", "zonder-gelijkteken"])
    assert exc.value.code == 2


# --- jellyfin-sdk-swift (Swiftfin; P4-0, JC3) ------------------------------------------------------------------------

SWIFT_PATHS = {
    "GetItemAPI.swift": """
extension Paths {
    /// Gets an item from a user's library.
    public static func getItem(itemID: String, userID: String? = nil) -> Request<BaseItemDto> {
        Request(path: "/Items/\\(itemID)", method: "GET", query: makeGetItemQuery(userID), id: "GetItem")
    }

    private static func makeGetItemQuery(_ userID: String?) -> [(String, String?)] {
        Request(path: "/Nooit/Meetellen", method: "DELETE")
    }
}
""",
    "AddMediaPathAPI.swift": """
public extension Paths {
    static func addMediaPath(isRefreshLibrary: Bool? = nil, _ body: MediaPathDto) -> Request<Void> {
        Request(
            path: "/Library/VirtualFolders/Paths",
            method: "POST",
            body: body
        )
    }
}
""",
    "GetPublicSystemInfoAPI.swift": """
public extension Paths {
    static var getPublicSystemInfo: Request<PublicSystemInfo> {
        Request(path: "/System/Info/Public", id: "GetPublicSystemInfo")
    }
}
""",
}


def test_swift_sdk_endpoints_enkel_meerregelig_var_en_nooit_private(tmp_path):
    write(tmp_path / "Paths", SWIFT_PATHS)
    endpoints = sac.sdk_endpoints_swift(tmp_path / "Paths")
    assert endpoints == {("GET", "/items/{}"): {"Paths.getItem"},
                         ("POST", "/library/virtualfolders/paths"): {"Paths.addMediaPath"},
                         ("GET", "/system/info/public"): {"Paths.getPublicSystemInfo"}}


def test_swift_gebruik_alleen_als_paths_aanroep(tmp_path):
    write(tmp_path / "Paths", SWIFT_PATHS)
    write(tmp_path / "app", {"A.swift": "let r = Paths.getItem(itemID: id)\n",
                             "B.swift": "func getPublicSystemInfo() {}\n", "C.kt": "Paths.addMediaPath(x)\n"})
    endpoints = sac.sdk_endpoints_swift(tmp_path / "Paths")
    teksten = sac.client_texts([tmp_path / "app"], "swift")
    assert sac.used_functions(teksten, endpoints, "swift") == {"getItem"}  # C.kt telt niet mee voor Swift
    weg = {("GET", "/items/{}"): {"Paths.getItem"}}
    assert sac.client_usages([tmp_path / "app"], weg, tmp_path, "swift")[0]["gebruikt_in"] == ["app/A.swift"]


def test_cli_swift(opstelling, tmp_path, capsys):
    write(tmp_path / "Paths", SWIFT_PATHS)
    write(tmp_path / "app", {"A.swift": "Paths.getPublicSystemInfo\nPaths.getItem(itemID: i)\n"})
    code = sac.main(["--sdk-taal", "swift", "--server-a", str(opstelling["a"]), "--server-b", str(opstelling["b"]),
                     "--sdk-ops", str(tmp_path / "Paths"), "--client", f"swiftfin={tmp_path / 'app'}",
                     "--root", str(tmp_path)])
    uit = json.loads(capsys.readouterr().out)
    assert uit["sdk_taal"] == "swift" and "GET /items/{}" in uit["sdk_endpoints_ontbrekend_in_b"]
    assert code == 1 and uit["per_client"]["swiftfin"][0]["sdk_functies"] == ["Paths.getItem"]
