from sql_demo.downloads import parse_schema_manager_links, resolve_artifacts


def test_parse_schema_manager_links_keeps_openssl3_builds() -> None:
    html = """
    https://downloads.mongodb.org/mongodb-schema-manager/x86_64/linux/openssl1_1/mongodb-schema-manager-v2.0.0
    https://downloads.mongodb.org/mongodb-schema-manager/x86_64/linux/openssl3/mongodb-schema-manager-v2.0.0
    https://downloads.mongodb.org/mongodb-schema-manager/arm64/macos/mongodb-schema-manager-v2.0.0
    https://downloads.mongodb.org/mongodb-schema-manager/x86_64/win/mongodb-schema-manager-v2.0.0.exe
    """
    found = parse_schema_manager_links(html)
    assert found["linux-x86_64"].endswith("/openssl3/mongodb-schema-manager-v2.0.0")
    assert found["darwin-arm64"].endswith("/arm64/macos/mongodb-schema-manager-v2.0.0")
    assert found["windows-x86_64"].endswith(".exe")


def test_resolve_artifacts_uses_overrides_without_network() -> None:
    artifacts = resolve_artifacts(schema_manager_url="https://example.test/schema")
    assert artifacts.schema_manager_url.endswith("/schema")
    assert artifacts.schema_manager_windows_url.endswith(".exe")
