"""Atlas setup through the Atlas CLI.

Stable operations use `atlas` commands. Enabling the SQL Interface is a preview
API. Current CLI releases call it with `atlas api clusters getClusterSqlInterface`
and `updateClusterSqlInterface`. Older releases do not have those commands yet,
so this module reuses the access token from the CLI login for that one call.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from sql_demo.logutil import log
from sql_demo.uriutil import access_list_entry, cluster_host

PREVIEW_ACCEPT = "application/vnd.atlas.preview+json"
API_ROOT = "https://cloud.mongodb.com"

UNSUPPORTED_REASONS = {
    "UNSUPPORTED_TIER": "SQL Interface requires a dedicated cluster, M10 or larger.",
    "UNSUPPORTED_TYPE": "SQL Interface requires a dedicated cluster. Flex and shared clusters are not supported.",
    "UNSUPPORTED_MONGODB_VERSION": "SQL Interface requires MongoDB 6.0 or later.",
}


class AtlasError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, payload: dict | None = None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}


@dataclass
class CliResult:
    code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def text(self) -> str:
        return f"{self.stdout}\n{self.stderr}".strip()


Runner = Callable[[list[str], str | None], CliResult]
TokenProvider = Callable[[], str]


class AtlasCli:
    def __init__(
        self,
        project_id: str,
        profile: str = "",
        *,
        runner: Runner | None = None,
        token_provider: TokenProvider | None = None,
    ) -> None:
        self.project_id = project_id
        self.profile = profile
        self._runner = runner
        self._token_provider = token_provider
        self._sql_cli: bool | None = None

    def ensure_login(self) -> None:
        if self._runner is not None:
            result = self._run(["auth", "whoami"])
            if result.code != 0:
                raise AtlasError(
                    "The Atlas CLI is not logged in. Run `atlas auth login` and try again.\n"
                    + result.text
                )
            return
        from sql_demo.atlas_install import ensure_atlas_cli

        ensure_atlas_cli()

    def get_cluster(self, cluster_name: str) -> dict[str, Any]:
        result = self._run(
            ["clusters", "describe", cluster_name, *self._project_flags(), "-o", "json"],
            check=True,
        )
        return _parse_json(result.stdout or result.text)

    def sql_status(self, cluster_name: str) -> dict[str, Any]:
        if self._has_sql_command():
            result = self._run(
                [
                    "api",
                    "clusters",
                    "getClusterSqlInterface",
                    "--groupId",
                    self.project_id,
                    "--clusterName",
                    cluster_name,
                    "--version",
                    "preview",
                    "-o",
                    "json",
                ],
                check=True,
            )
            return _parse_json(result.stdout or result.text)
        return self._sql_http("GET", cluster_name)

    def enable_sql_interface(self, cluster_name: str, *, timeout_seconds: int = 600) -> dict[str, Any]:
        status = self.sql_status(cluster_name)
        self._require_supported(status)
        if status.get("status") == "ON":
            log("atlas", "SQL Interface is already ON.")
            return status

        log("atlas", "Turning the SQL Interface ON. Propagation can take a few minutes.")
        deadline = time.time() + timeout_seconds
        while True:
            try:
                self._set_sql_status(cluster_name, "ON")
                break
            except AtlasError as exc:
                if "CLUSTER_INVALID_STATE" in str(exc) and time.time() < deadline:
                    log("atlas", "Cluster is busy. Waiting to retry the SQL Interface change.")
                    time.sleep(20)
                    continue
                raise

        while time.time() < deadline:
            current = self.sql_status(cluster_name)
            if current.get("status") == "ON":
                log("atlas", "SQL Interface status is ON.")
                return current
            log("atlas", f"SQL Interface status is {current.get('status', 'unknown')}. Waiting.")
            time.sleep(15)
        raise AtlasError(
            "Timed out waiting for the SQL Interface to report ON. "
            "Check the cluster in Atlas and run setup again."
        )

    def disable_sql_interface(self, cluster_name: str) -> None:
        self._set_sql_status(cluster_name, "OFF")
        log("atlas", "SQL Interface status set to OFF.")

    def ensure_schema_role(self, role_name: str, databases: tuple[str, ...]) -> None:
        privileges = schema_privileges(databases)
        created = self._run(
            [
                "customDbRoles",
                "create",
                role_name,
                *_repeat("--privilege", privileges),
                *self._project_flags(),
                "-o",
                "json",
            ]
        )
        if created.code == 0:
            log("atlas", f"Created custom role {role_name}.")
            return
        if not _is_conflict(created.text):
            _raise_cli(created)
        updated = self._run(
            [
                "customDbRoles",
                "update",
                role_name,
                *_repeat("--privilege", privileges),
                *self._project_flags(),
                "-o",
                "json",
            ],
            check=True,
        )
        del updated
        log("atlas", f"Updated custom role {role_name}.")

    def ensure_database_user(
        self,
        *,
        username: str,
        password: str,
        databases: tuple[str, ...],
        schema_role: str,
        cluster_name: str,
        scope_to_cluster: bool,
    ) -> None:
        roles = database_user_roles(databases, schema_role)
        scope = [f"{cluster_name}:CLUSTER"] if scope_to_cluster else []
        created = self._run(
            [
                "dbusers",
                "create",
                "--username",
                username,
                f"--password={password}",
                *_repeat("--role", roles),
                *_repeat("--scope", scope),
                *self._project_flags(),
                "-o",
                "json",
            ]
        )
        if created.code == 0:
            log("atlas", f"Created database user {username}.")
            return
        if not _is_conflict(created.text):
            _raise_cli(created)
        self._run(
            [
                "dbusers",
                "update",
                username,
                f"--password={password}",
                *_repeat("--role", roles),
                *_repeat("--scope", scope),
                *self._project_flags(),
                "-o",
                "json",
            ],
            check=True,
        )
        log("atlas", f"Updated database user {username}.")

    def allow_current_ip(self, comment: str) -> None:
        result = self._run(
            [
                "accessLists",
                "create",
                "--currentIp",
                "--comment",
                comment[:80],
                *self._project_flags(),
                "-o",
                "json",
            ]
        )
        if result.code == 0:
            log("atlas", "Allowed this machine through the cluster firewall.")
            return
        if _is_conflict(result.text):
            log("atlas", "This machine is already allowed through the cluster firewall.")
            return
        _raise_cli(result)

    def ensure_access_entries(self, entries: list[tuple[str, str]]) -> None:
        for address, comment in entries:
            entry = access_list_entry(address, comment)
            if "cidrBlock" in entry:
                target = entry["cidrBlock"]
                entry_type = "cidrBlock"
            else:
                target = entry["ipAddress"]
                entry_type = "ipAddress"
            result = self._run(
                [
                    "accessLists",
                    "create",
                    target,
                    "--type",
                    entry_type,
                    "--comment",
                    entry["comment"],
                    *self._project_flags(),
                    "-o",
                    "json",
                ]
            )
            if result.code == 0:
                log("atlas", f"Allowed {target} through the cluster firewall.")
            elif _is_conflict(result.text):
                log("atlas", f"{target} is already allowed through the cluster firewall.")
            else:
                _raise_cli(result)

    def delete_access_entry(self, address: str) -> None:
        entry = access_list_entry(address, "remove")
        target = entry.get("ipAddress") or entry.get("cidrBlock") or address
        result = self._run(
            ["accessLists", "delete", str(target), "--force", *self._project_flags()]
        )
        if result.code == 0 or _is_missing(result.text):
            log("atlas", f"Removed {target} from the cluster firewall.")
            return
        _raise_cli(result)

    def delete_database_user(self, username: str) -> None:
        result = self._run(["dbusers", "delete", username, "--force", *self._project_flags()])
        if result.code == 0 or _is_missing(result.text):
            log("atlas", f"Removed database user {username}.")
            return
        _raise_cli(result)

    def delete_schema_role(self, role_name: str) -> None:
        result = self._run(["customDbRoles", "delete", role_name, "--force", *self._project_flags()])
        if result.code == 0 or _is_missing(result.text):
            log("atlas", f"Removed custom role {role_name}.")
            return
        _raise_cli(result)

    def load_sample_dataset(self, cluster_name: str) -> str:
        result = self._run(
            ["clusters", "sampleData", "load", cluster_name, *self._project_flags(), "-o", "json"]
        )
        if result.code != 0:
            if "already" in result.text.lower():
                log("atlas", "Sample dataset is already loaded.")
                return "already-loaded"
            _raise_cli(result)
        payload = _parse_json(result.stdout or result.text)
        job_id = str(payload.get("id") or "")
        log("atlas", "Sample dataset load started.")
        if job_id:
            self._run(
                ["clusters", "sampleData", "watch", job_id, *self._project_flags()],
                check=True,
                timeout=1800,
            )
            log("atlas", "Sample dataset load finished.")
        return "started"

    def _set_sql_status(self, cluster_name: str, status: str) -> None:
        payload = json.dumps({"status": status})
        if self._has_sql_command():
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
                handle.write(payload)
                path = handle.name
            try:
                self._run(
                    [
                        "api",
                        "clusters",
                        "updateClusterSqlInterface",
                        "--groupId",
                        self.project_id,
                        "--clusterName",
                        cluster_name,
                        "--version",
                        "preview",
                        "--file",
                        path,
                        "-o",
                        "json",
                    ],
                    check=True,
                )
            finally:
                Path(path).unlink(missing_ok=True)
            return
        self._sql_http("PATCH", cluster_name, body={"status": status})

    def _sql_http(self, method: str, cluster_name: str, body: dict | None = None) -> dict[str, Any]:
        url = (
            f"{API_ROOT}/api/atlas/v2/groups/{quote(self.project_id, safe='')}"
            f"/clusters/{quote(cluster_name, safe='')}/sqlInterface"
        )
        response = self._authorized_request(method, url, body)
        if response.status_code == 401:
            response = self._authorized_request(method, url, body, refresh=True)
        if response.status_code >= 400:
            _raise_http(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise AtlasError(f"Atlas returned a non-JSON SQL Interface response: {response.text[:500]}") from exc
        if not isinstance(payload, dict):
            raise AtlasError(f"Unexpected SQL Interface response: {payload}")
        return payload

    def _authorized_request(
        self,
        method: str,
        url: str,
        body: dict | None,
        *,
        refresh: bool = False,
    ) -> requests.Response:
        token = self._access_token(refresh=refresh)
        headers = {"Authorization": f"Bearer {token}", "Accept": PREVIEW_ACCEPT}
        if body is not None:
            headers["Content-Type"] = PREVIEW_ACCEPT
        return requests.request(method, url, headers=headers, json=body, timeout=90)

    def _access_token(self, *, refresh: bool = False) -> str:
        if refresh:
            self._run(["projects", "list", "--limit", "1", "-o", "json"])
        if self._token_provider is not None:
            return self._token_provider()
        profile = self.profile or "default"
        service = f"atlascli_{profile}"
        if sys.platform == "darwin":
            command = ["security", "find-generic-password", "-s", service, "-a", "access_token", "-w"]
        elif sys.platform.startswith("linux"):
            command = ["secret-tool", "lookup", "service", service, "username", "access_token"]
        else:
            raise AtlasError(
                "This Atlas CLI does not include the SQL Interface commands, and this "
                "operating system cannot read the CLI login automatically. Upgrade the "
                "Atlas CLI and run `atlas auth login`."
            )
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        token = completed.stdout.strip()
        if completed.returncode != 0 or not token:
            raise AtlasError(
                "Could not read the Atlas CLI login. Run `atlas auth login` and try again."
            )
        return token

    def _has_sql_command(self) -> bool:
        if self._sql_cli is None:
            result = self._run(["api", "clusters", "getClusterSqlInterface", "--help"])
            self._sql_cli = result.code == 0 and "unknown command" not in result.text.lower()
        return self._sql_cli

    def _project_flags(self) -> list[str]:
        if not self.project_id:
            return []
        return ["--projectId", self.project_id]

    def _run(
        self,
        args: list[str],
        *,
        stdin: str | None = None,
        check: bool = False,
        timeout: int = 180,
    ) -> CliResult:
        if self.profile:
            args = [*args, "--profile", self.profile]
        log("atlas", _display(args))
        if self._runner is not None:
            result = self._runner(args, stdin)
        else:
            try:
                completed = subprocess.run(
                    ["atlas", *args],
                    input=stdin,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=timeout,
                )
            except FileNotFoundError as exc:
                raise AtlasError(
                    "The Atlas CLI is not installed. Install it from "
                    "https://www.mongodb.com/docs/atlas/cli/stable/install-atlas-cli/ "
                    "and run `atlas auth login`."
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise AtlasError(f"atlas {' '.join(_display(args).split()[:4])} timed out.") from exc
            result = CliResult(completed.returncode, completed.stdout, completed.stderr)
        if check and result.code != 0:
            _raise_cli(result)
        return result

    @staticmethod
    def _require_supported(status: dict[str, Any]) -> None:
        if status.get("supported", False):
            return
        reason = str(status.get("unsupportedReason") or "UNKNOWN")
        meaning = UNSUPPORTED_REASONS.get(reason, "This cluster cannot use the SQL Interface.")
        raise AtlasError(f"{reason}: {meaning}")


def schema_privileges(databases: tuple[str, ...]) -> list[str]:
    privileges: list[str] = []
    for database in databases:
        for action in ("FIND", "INSERT", "UPDATE"):
            privileges.append(f"{action}@{database}.__sql_schemas")
    return privileges


def database_user_roles(databases: tuple[str, ...], schema_role: str) -> list[str]:
    roles = [f"read@{database}" for database in databases]
    roles.append(f"{schema_role}@admin")
    roles.append("read@__mdb_internal_sqlinterface")
    return roles


def cluster_srv_host(cluster: dict[str, Any]) -> str:
    strings = cluster.get("connectionStrings") or {}
    standard = strings.get("standardSrv") or strings.get("standard") or ""
    if not standard:
        raise AtlasError("The cluster description did not include a connection string.")
    return cluster_host(str(standard))


def _repeat(flag: str, values: list[str]) -> list[str]:
    args: list[str] = []
    for value in values:
        args.extend([flag, value])
    return args


def _display(args: list[str]) -> str:
    shown: list[str] = []
    for arg in args:
        if arg.startswith("--password="):
            shown.append("--password=***")
        else:
            shown.append(arg)
    return "atlas " + " ".join(shown)


def _parse_json(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise AtlasError(text.strip() or "Atlas CLI returned no JSON.")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AtlasError(f"Atlas CLI returned invalid JSON: {text[:500]}") from exc
    if not isinstance(payload, dict):
        raise AtlasError(f"Atlas CLI returned unexpected JSON: {payload}")
    return payload


def _is_conflict(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "already exists",
        "already exist",
        "duplicate",
        "already_exists",
        "already in",
        "409",
    )
    return any(marker in lowered for marker in markers)


def _is_missing(text: str) -> bool:
    lowered = text.lower()
    return "not found" in lowered or "404" in lowered


def _raise_cli(result: CliResult) -> None:
    raise AtlasError(result.text or f"Atlas CLI exited {result.code}.")


def _raise_http(response: requests.Response) -> None:
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": response.text[:1000]}
    if not isinstance(payload, dict):
        payload = {"detail": str(payload)}
    detail = payload.get("detail") or payload.get("reason") or payload.get("error") or response.text
    code = payload.get("errorCode") or ""
    prefix = f"{code}: " if code else ""
    raise AtlasError(
        f"Atlas API {response.status_code} {prefix}{detail}",
        status=response.status_code,
        payload=payload,
    )
