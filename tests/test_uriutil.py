from sql_demo.uriutil import (
    access_list_entry,
    cluster_host,
    power_bi_uri,
    redact_uri,
    schema_builder_uri,
)


def test_cluster_host_strips_a_standard_srv_uri() -> None:
    assert cluster_host("mongodb+srv://cluster0.example.mongodb.net") == "cluster0.example.mongodb.net"
    assert (
        cluster_host("mongodb+srv://user:secret@cluster0.example.mongodb.net/db?retryWrites=true")
        == "cluster0.example.mongodb.net"
    )


def test_power_bi_uri_has_no_credentials() -> None:
    uri = power_bi_uri("cluster0.example.mongodb.net")
    assert uri == "mongodb+srv://cluster0.example.mongodb.net/?ssl=true&authSource=admin"
    assert "@" not in uri


def test_schema_uri_encodes_the_password() -> None:
    uri = schema_builder_uri("cluster0.example.mongodb.net", "sql-demo", "p@ss/word")
    assert "sql-demo:p%40ss%2Fword@" in uri
    assert redact_uri(uri) == (
        "mongodb+srv://sql-demo:***@cluster0.example.mongodb.net/"
        "?ssl=true&authSource=admin&retryWrites=true&w=majority"
    )


def test_access_list_uses_ip_or_cidr() -> None:
    assert access_list_entry("203.0.113.10", "vm")["ipAddress"] == "203.0.113.10"
    assert access_list_entry("203.0.113.0/24", "office")["cidrBlock"] == "203.0.113.0/24"
