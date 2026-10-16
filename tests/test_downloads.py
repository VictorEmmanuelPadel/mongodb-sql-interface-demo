from sql_demo.downloads import (
    parse_schema_manager_links,
    powerbi_connector_url,
    resolve_artifacts,
    windows_odbc_url,
)


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


def test_catalog_parsers_pick_the_newest_version() -> None:
    odbc = windows_odbc_url(
        {
            "versions": [
                {
                    "version": "1.2.0",
                    "platform": [{"name": "Windows", "download_link": "https://example.test/old.msi"}],
                },
                {
                    "version": "3.0.0",
                    "platform": [{"name": "Windows", "download_link": "https://example.test/new.msi"}],
                },
            ]
        }
    )
    connector = powerbi_connector_url(
        {
            "versions": [
                {"version": "1.0.0", "download_link": "https://example.test/old.pqx"},
                {"version": "1.2.2", "download_link": "https://example.test/new.pqx"},
            ]
        }
    )
    assert odbc.endswith("/new.msi")
    assert connector.endswith("/new.pqx")


def test_resolve_artifacts_uses_overrides_without_network() -> None:
    artifacts = resolve_artifacts(
        odbc_driver_url="https://example.test/odbc.msi",
        powerbi_connector_url_override="https://example.test/connector.pqx",
        schema_manager_url="https://example.test/schema",
    )
    assert artifacts.odbc_windows_url.endswith("/odbc.msi")
    assert artifacts.powerbi_connector_url.endswith("/connector.pqx")
    assert artifacts.schema_manager_url.endswith("/schema")
    assert artifacts.schema_manager_windows_url.endswith(".exe")
