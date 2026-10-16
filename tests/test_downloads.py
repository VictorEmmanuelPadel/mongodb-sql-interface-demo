from sql_demo.downloads import parse_official_download_links, parse_schema_manager_links, resolve_artifacts


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


def test_official_page_links_prefer_the_newest_mongodb_download() -> None:
    html = """
    https://downloads.mongodb.org/mongosql-odbc-driver/windows/1.2.0/release/mongoodbc-1.2.0.msi
    https://downloads.mongodb.org/mongosql-odbc-driver/windows/3.0.0/release/mongoodbc-3.0.0.msi
    https://downloads.mongodb.org/mongosql-odbc-driver/ubuntu2204/3.1.0/release/mongoodbc-3.1.0.tar.gz
    https://downloads.mongodb.org/mongo-powerbi-connector/MongoDBAtlasODBC-1.0.0.pqx
    https://downloads.mongodb.org/mongo-powerbi-connector/MongoDBAtlasODBC-1.2.2.pqx
    """
    odbc, connector = parse_official_download_links(html)
    assert odbc.endswith("/mongoodbc-3.0.0.msi")
    assert connector.endswith("/MongoDBAtlasODBC-1.2.2.pqx")


def test_resolve_artifacts_uses_overrides_without_network() -> None:
    artifacts = resolve_artifacts(
        odbc_driver_url="https://example.test/odbc.msi",
        powerbi_connector_url="https://example.test/connector.pqx",
        schema_manager_url="https://example.test/schema",
    )
    assert artifacts.odbc_windows_url.endswith("/odbc.msi")
    assert artifacts.powerbi_connector_url.endswith("/connector.pqx")
    assert artifacts.schema_manager_url.endswith("/schema")
    assert artifacts.schema_manager_windows_url.endswith(".exe")
