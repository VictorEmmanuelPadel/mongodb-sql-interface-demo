"""Download and run the MongoDB SQL Schema Builder, then read the schemas it wrote."""

from __future__ import annotations

import platform
import stat
import subprocess
import time
from pathlib import Path

import requests
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from sql_demo.logutil import log
from sql_demo.uriutil import redact_uri

_NETWORK_MARKERS = (
    "timed out",
    "timeout",
    "not allowed",
    "connection refused",
    "server selection",
    "no such host",
    "econn",
    "handshake",
    "network error",
    "could not connect",
)


def download_schema_manager(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.stat().st_size == 0:
        log("schema", f"Downloading schema builder from {url}")
        partial = dest.with_suffix(dest.suffix + ".partial")
        with requests.get(url, stream=True, timeout=180) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        handle.write(chunk)
        partial.replace(dest)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if platform.system() == "Darwin":
        subprocess.run(
            ["xattr", "-d", "com.apple.quarantine", str(dest)],
            check=False,
            capture_output=True,
        )
    return dest


def run_schema_manager(
    binary: Path,
    *,
    uri: str,
    patterns: tuple[str, ...],
    log_dir: Path,
    jobs: int,
    action: str,
    timeout_seconds: int,
    attempts: int = 8,
) -> str:
    log_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(binary),
        "--uri",
        uri,
        "--logpath",
        str(log_dir),
        "--verbosity",
        "info",
        "--jobs",
        str(jobs),
        "--action",
        action,
    ]
    for pattern in patterns:
        command.extend(["--ns-include", pattern])

    shown = [redact_uri(part) if part == uri else part for part in command]
    log("schema", "Running " + " ".join(shown))
    log(
        "schema",
        "The schema builder reads every document in each included collection. "
        "Use a small demo database; large collections can take a long time.",
    )

    last_output = ""
    for attempt in range(1, attempts + 1):
        started = time.time()
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        last_output = output
        if completed.returncode == 0:
            if output.strip():
                print(output.rstrip(), flush=True)
            return output
        elapsed = time.time() - started
        retryable = elapsed < 90 and _looks_like_network(output)
        log("schema", f"Schema builder exited {completed.returncode}.")
        if output.strip():
            print(output.rstrip(), flush=True)
        if not retryable or attempt == attempts:
            hint = ""
            if "not authorized" in output.lower() or "unauthorized" in output.lower():
                hint = (
                    " The database user needs read on __mdb_internal_sqlinterface "
                    "and find/insert/update on __sql_schemas."
                )
            raise RuntimeError(f"Schema builder failed.{hint}")
        log("schema", f"Cluster firewall may still be propagating. Retry {attempt}/{attempts}.")
        time.sleep(15)
    raise RuntimeError(f"Schema builder failed.\n{last_output}")


def verify_schemas(uri: str, databases: tuple[str, ...]) -> list[dict]:
    rows: list[dict] = []
    try:
        with MongoClient(uri, serverSelectionTimeoutMS=30000) as client:
            client.admin.command("ping")
            for database in databases:
                cursor = client[database]["__sql_schemas"].find({}, {"schema": 0})
                for document in cursor:
                    rows.append(
                        {
                            "database": database,
                            "collection": document.get("_id"),
                            "unstable": bool(document.get("unstable")),
                            "lastUpdated": document.get("lastUpdated"),
                        }
                    )
    except PyMongoError as exc:
        raise RuntimeError(f"Could not read __sql_schemas: {exc}") from exc
    if not rows:
        raise RuntimeError(
            "The schema builder finished without writing __sql_schemas documents. "
            "Confirm the configured database contains collections with documents."
        )
    return rows


def _looks_like_network(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in _NETWORK_MARKERS)
