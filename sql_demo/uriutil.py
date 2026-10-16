"""MongoDB URI helpers for the schema builder and Power BI."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import quote_plus


def redact_uri(uri: str) -> str:
    """Hide a password embedded in a MongoDB URI."""
    return re.sub(r"(//[^:/@]+:)([^@]+)@", r"\1***@", uri)


def cluster_host(standard_srv: str) -> str:
    """Return the hostname from an Atlas standardSrv connection string."""
    value = standard_srv.strip()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0]
    value = value.split("?", 1)[0]
    if "@" in value:
        value = value.split("@", 1)[1]
    if not value:
        raise ValueError("Cluster connection string did not include a host.")
    return value


def schema_builder_uri(host: str, username: str, password: str) -> str:
    """Credentialed URI for mongodb-schema-manager and pymongo."""
    user = quote_plus(username)
    secret = quote_plus(password)
    return (
        f"mongodb+srv://{user}:{secret}@{host}/"
        "?ssl=true&authSource=admin&retryWrites=true&w=majority"
    )


def power_bi_uri(host: str) -> str:
    """URI for the Power BI connector. Credentials are entered separately."""
    return f"mongodb+srv://{host}/?ssl=true&authSource=admin"


def access_list_entry(address: str, comment: str) -> dict[str, str]:
    """Build one Atlas project access-list entry from an IP or CIDR."""
    raw = address.strip()
    if "/" not in raw:
        ipaddress.ip_address(raw)
        raw = f"{raw}/32" if ":" not in raw else f"{raw}/128"
    network = ipaddress.ip_network(raw, strict=False)
    note = comment[:80]
    host_bits = 32 if network.version == 4 else 128
    if network.prefixlen == host_bits:
        return {"ipAddress": str(network.network_address), "comment": note}
    return {"cidrBlock": str(network), "comment": note}
