import json

from sql_demo.atlas import (
    AtlasCli,
    AtlasError,
    CliResult,
    database_user_roles,
    schema_privileges,
)


def test_schema_privileges_cover_sql_schema_writes() -> None:
    assert schema_privileges(("sample_mflix",)) == [
        "FIND@sample_mflix.__sql_schemas",
        "INSERT@sample_mflix.__sql_schemas",
        "UPDATE@sample_mflix.__sql_schemas",
    ]


def test_database_user_roles_include_the_internal_database() -> None:
    assert database_user_roles(("sample_mflix",), "sqlSchemaWriter") == [
        "read@sample_mflix",
        "sqlSchemaWriter@admin",
        "read@__mdb_internal_sqlinterface",
    ]


def test_enable_sql_returns_immediately_when_already_on() -> None:
    calls: list[list[str]] = []

    def runner(args: list[str], _stdin: str | None) -> CliResult:
        calls.append(args)
        if args[:4] == ["api", "clusters", "getClusterSqlInterface", "--help"]:
            return CliResult(0, "getClusterSqlInterface")
        if "getClusterSqlInterface" in args:
            return CliResult(0, json.dumps({"status": "ON", "supported": True}))
        raise AssertionError(args)

    status = AtlasCli("abc123abc123abc123abc123", runner=runner).enable_sql_interface("Cluster0")
    assert status["status"] == "ON"
    assert not any("updateClusterSqlInterface" in arg for call in calls for arg in call)


def test_current_ip_allow_uses_the_atlas_cli() -> None:
    seen: list[list[str]] = []

    def runner(args: list[str], _stdin: str | None) -> CliResult:
        seen.append(args)
        return CliResult(0, "{}")

    AtlasCli("abc123abc123abc123abc123", runner=runner).allow_current_ip("schema builder")
    assert seen[0][:4] == ["accessLists", "create", "--currentIp", "--comment"]
    assert "--projectId" in seen[0]


def test_database_user_password_is_not_logged(capsys) -> None:
    def runner(args: list[str], _stdin: str | None) -> CliResult:
        assert any(arg == "--password=s3cret" for arg in args)
        return CliResult(0, "{}")

    AtlasCli("abc123abc123abc123abc123", runner=runner).ensure_database_user(
        username="sql-demo",
        password="s3cret",
        databases=("sample_mflix",),
        schema_role="sqlSchemaWriter",
        cluster_name="Cluster0",
        scope_to_cluster=True,
    )
    output = capsys.readouterr().out
    assert "s3cret" not in output
    assert "--password=***" in output


def test_sql_status_uses_the_cli_login_when_the_command_is_missing(monkeypatch) -> None:
    seen: list[tuple[str, str, str]] = []

    class Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"status": "OFF", "supported": True}

    def request(method: str, url: str, **kwargs: object) -> Response:
        headers = kwargs["headers"]
        assert isinstance(headers, dict)
        seen.append((method, url, str(headers["Authorization"])))
        assert headers["Accept"] == "application/vnd.atlas.preview+json"
        return Response()

    monkeypatch.setattr("sql_demo.atlas.requests.request", request)

    def runner(args: list[str], _stdin: str | None) -> CliResult:
        if "getClusterSqlInterface" in args:
            return CliResult(1, "", 'Error: unknown command "getClusterSqlInterface"')
        raise AssertionError(args)

    status = AtlasCli(
        "abc123abc123abc123abc123",
        runner=runner,
        token_provider=lambda: "session-token",
    ).sql_status("Cluster0")
    assert status["status"] == "OFF"
    assert seen == [
        (
            "GET",
            "https://cloud.mongodb.com/api/atlas/v2/groups/abc123abc123abc123abc123/clusters/Cluster0/sqlInterface",
            "Bearer session-token",
        )
    ]


def test_unsupported_cluster_is_rejected() -> None:
    try:
        AtlasCli._require_supported({"supported": False, "unsupportedReason": "UNSUPPORTED_TIER"})
    except AtlasError as exc:
        assert "M10" in str(exc)
    else:
        raise AssertionError("expected AtlasError")
