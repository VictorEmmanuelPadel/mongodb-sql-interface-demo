"""Push the demo guide onto the Windows VM with the Azure Run Command API."""

from __future__ import annotations

import base64
import subprocess
import time

import requests

from sql_demo.config import Config
from sql_demo.logutil import ok, warn
from sql_demo.terraform_runner import VmInfo

_API_VERSION = "2024-03-01"


def publish_demo_files(config: Config, vm: VmInfo, files: dict[str, str]) -> None:
    try:
        token = _access_token(config)
        script = _write_script(files)
        url = (
            "https://management.azure.com"
            f"/subscriptions/{config.azure_subscription_id}"
            f"/resourceGroups/{vm.resource_group}"
            "/providers/Microsoft.Compute"
            f"/virtualMachines/{vm.vm_name}/runCommand"
            f"?api-version={_API_VERSION}"
        )
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"commandId": "RunPowerShellScript", "script": [script]},
            timeout=120,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
        if response.status_code == 202:
            operation = response.headers.get("Azure-AsyncOperation") or response.headers.get("Location")
            if not operation:
                raise RuntimeError("Azure accepted the command without an operation URL.")
            _wait_for_operation(operation, token)
        ok("azure", "Wrote the connection guide to the VM desktop.")
    except Exception as exc:
        warn(
            "azure",
            "Could not copy the guide onto the VM desktop. "
            f"Use output/demo-connection.txt instead. {exc}",
        )


def _write_script(files: dict[str, str]) -> str:
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "New-Item -ItemType Directory -Force -Path 'C:\\SQLInterfaceDemo' | Out-Null",
        "New-Item -ItemType Directory -Force -Path 'C:\\Users\\Public\\Desktop' | Out-Null",
    ]
    for path, content in files.items():
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        escaped = path.replace("'", "''")
        lines.append(
            f"[IO.File]::WriteAllText('{escaped}', "
            f"[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}')))"
        )
    lines.append("Write-Output 'demo files written'")
    return "\n".join(lines)


def _access_token(config: Config) -> str:
    completed = subprocess.run(
        [
            "az",
            "account",
            "get-access-token",
            "--resource",
            "https://management.azure.com",
            "--query",
            "accessToken",
            "-o",
            "tsv",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "az account get-access-token failed"
        raise RuntimeError(detail)
    token = completed.stdout.strip()
    if not token:
        raise RuntimeError("Azure CLI did not return an access token. Run az login.")
    return token


def _wait_for_operation(url: str, token: str, timeout_seconds: int = 300) -> None:
    deadline = time.time() + timeout_seconds
    headers = {"Authorization": f"Bearer {token}"}
    while time.time() < deadline:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        body = response.json()
        status = str(body.get("status") or "")
        if status.lower() == "succeeded":
            return
        if status.lower() in {"failed", "canceled", "cancelled"}:
            raise RuntimeError(f"Azure run command {status}: {str(body)[:500]}")
        time.sleep(5)
    raise RuntimeError("Timed out waiting for the Azure run command.")
