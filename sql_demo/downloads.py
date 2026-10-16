"""Resolve current MongoDB SQL Interface download URLs."""

from __future__ import annotations

import platform
import re
from dataclasses import dataclass

import requests

ODBC_PAGE = "https://www.mongodb.com/try/download/odbc-driver"
SCHEMA_PAGE = "https://www.mongodb.com/try/download/sql-schema-builder"

FALLBACK_ODBC_WINDOWS = (
    "https://downloads.mongodb.org/mongosql-odbc-driver/windows/3.0.0/release/mongoodbc-3.0.0.msi"
)
FALLBACK_POWERBI = "https://downloads.mongodb.org/mongo-powerbi-connector/MongoDBAtlasODBC-1.2.2.pqx"

FALLBACK_SCHEMA = {
    "darwin-arm64": "https://downloads.mongodb.org/mongodb-schema-manager/arm64/macos/mongodb-schema-manager-v2.0.0",
    "darwin-x86_64": "https://downloads.mongodb.org/mongodb-schema-manager/x86_64/macos/mongodb-schema-manager-v2.0.0",
    "linux-x86_64": "https://downloads.mongodb.org/mongodb-schema-manager/x86_64/linux/openssl3/mongodb-schema-manager-v2.0.0",
    "linux-aarch64": "https://downloads.mongodb.org/mongodb-schema-manager/arm64/linux/openssl3/mongodb-schema-manager-v2.0.0",
    "windows-x86_64": "https://downloads.mongodb.org/mongodb-schema-manager/x86_64/win/mongodb-schema-manager-v2.0.0.exe",
}


@dataclass(frozen=True)
class Artifacts:
    odbc_windows_url: str
    powerbi_connector_url: str
    schema_manager_url: str
    schema_manager_windows_url: str


def host_schema_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin" and machine in {"arm64", "aarch64"}:
        return "darwin-arm64"
    if system == "darwin":
        return "darwin-x86_64"
    if system == "linux" and machine in {"aarch64", "arm64"}:
        return "linux-aarch64"
    if system == "linux":
        return "linux-x86_64"
    if system == "windows":
        return "windows-x86_64"
    raise RuntimeError(f"Unsupported schema builder platform: {system} {machine}")


def parse_official_download_links(html: str) -> tuple[str, str]:
    """Return the newest official Windows ODBC MSI and Power BI connector URLs."""
    links = re.findall(r"https://downloads\.mongodb\.org/[^\s\"'<>]+", html)
    odbc = _newest(
        link
        for link in links
        if "/mongosql-odbc-driver/windows/" in link and link.endswith(".msi")
    )
    connector = _newest(
        link for link in links if "/mongo-powerbi-connector/" in link and link.endswith(".pqx")
    )
    return odbc, connector


def _newest(links) -> str:
    ranked = sorted(links, key=_version_key, reverse=True)
    return ranked[0] if ranked else ""


def _version_key(value: str) -> tuple[int, ...]:
    match = re.search(r"(\d+\.\d+\.\d+)", value)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def parse_schema_manager_links(html: str) -> dict[str, str]:
    links = re.findall(
        r"https://downloads\.mongodb\.org/mongodb-schema-manager/[^\s\"'<>]+",
        html,
    )
    found: dict[str, str] = {}
    for link in links:
        if "/arm64/macos/" in link:
            found["darwin-arm64"] = link
        elif "/x86_64/macos/" in link:
            found["darwin-x86_64"] = link
        elif "/x86_64/win/" in link:
            found["windows-x86_64"] = link
        elif "/x86_64/linux/openssl3/" in link:
            found["linux-x86_64"] = link
        elif "/arm64/linux/openssl3/" in link:
            found["linux-aarch64"] = link
    return found


def resolve_artifacts(
    *,
    odbc_driver_url: str = "",
    powerbi_connector_url: str = "",
    schema_manager_url: str = "",
    session: requests.Session | None = None,
) -> Artifacts:
    http = session or requests.Session()
    odbc = odbc_driver_url
    connector = powerbi_connector_url
    if not odbc or not connector:
        try:
            response = http.get(ODBC_PAGE, timeout=60)
            response.raise_for_status()
            page_odbc, page_connector = parse_official_download_links(response.text)
            odbc = odbc or page_odbc
            connector = connector or page_connector
        except requests.RequestException:
            pass
    odbc = odbc or FALLBACK_ODBC_WINDOWS
    connector = connector or FALLBACK_POWERBI
    schema_links = dict(FALLBACK_SCHEMA)
    if not schema_manager_url:
        try:
            response = http.get(SCHEMA_PAGE, timeout=60)
            response.raise_for_status()
            schema_links.update(parse_schema_manager_links(response.text))
        except requests.RequestException:
            pass
    host_url = schema_manager_url or schema_links[host_schema_key()]
    windows_url = schema_links["windows-x86_64"]
    return Artifacts(
        odbc_windows_url=odbc,
        powerbi_connector_url=connector,
        schema_manager_url=host_url,
        schema_manager_windows_url=windows_url,
    )
