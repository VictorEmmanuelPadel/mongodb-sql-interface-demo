"""Resolve current MongoDB SQL Interface download URLs."""

from __future__ import annotations

import platform
import re
from dataclasses import dataclass

import requests

ODBC_CATALOG = (
    "https://translators-connectors-releases.s3.amazonaws.com/"
    "mongosql-odbc-driver/mongo-odbc-downloads.json"
)
POWERBI_CATALOG = (
    "https://translators-connectors-releases.s3.amazonaws.com/"
    "mongo-powerbi-connector/mongo-powerbi-connector-downloads.json"
)
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


def windows_odbc_url(catalog: dict) -> str:
    versions = sorted(
        catalog.get("versions") or [],
        key=lambda item: _version_key(str(item.get("version") or "0")),
        reverse=True,
    )
    for version in versions:
        for entry in version.get("platform") or []:
            name = str(entry.get("name") or "")
            link = str(entry.get("download_link") or "")
            if name.lower().startswith("windows") and link.endswith(".msi"):
                return link
    raise RuntimeError("The ODBC download catalog did not include a Windows MSI.")


def powerbi_connector_url(catalog: dict) -> str:
    versions = sorted(
        catalog.get("versions") or [],
        key=lambda item: _version_key(str(item.get("version") or "0")),
        reverse=True,
    )
    if not versions:
        raise RuntimeError("The Power BI connector catalog did not include a version.")
    link = str(versions[0].get("download_link") or "")
    if not link:
        raise RuntimeError("The Power BI connector catalog entry has no download link.")
    return link


def _version_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in value.split("."):
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits or 0))
    return tuple(parts)


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
    powerbi_connector_url_override: str = "",
    schema_manager_url: str = "",
    session: requests.Session | None = None,
) -> Artifacts:
    http = session or requests.Session()
    odbc = odbc_driver_url or _catalog_or_fallback(
        http, ODBC_CATALOG, windows_odbc_url, FALLBACK_ODBC_WINDOWS
    )
    connector = powerbi_connector_url_override or _catalog_or_fallback(
        http, POWERBI_CATALOG, powerbi_connector_url, FALLBACK_POWERBI
    )
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


def _catalog_or_fallback(http: requests.Session, url: str, parser, fallback: str) -> str:
    try:
        response = http.get(url, timeout=60)
        response.raise_for_status()
        return parser(response.json())
    except (requests.RequestException, ValueError, RuntimeError, KeyError):
        return fallback
