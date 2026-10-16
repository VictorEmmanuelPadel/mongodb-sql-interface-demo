"""Run the Azure Terraform configuration."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sql_demo.config import Config
from sql_demo.downloads import Artifacts


class TerraformError(RuntimeError):
    pass


@dataclass(frozen=True)
class VmInfo:
    public_ip: str
    resource_group: str
    vm_name: str


class TerraformRunner:
    def __init__(self, config: Config, artifacts: Artifacts, workdir: Path) -> None:
        self.config = config
        self.artifacts = artifacts
        self.workdir = workdir
        self.env = _terraform_env(config, artifacts)

    def init(self) -> None:
        _require_terraform()
        self._run(["terraform", "init", "-input=false"])

    def start_apply(self) -> subprocess.Popen[bytes]:
        self.init()
        self._run(["terraform", "plan", "-input=false", "-out=tfplan"])
        return subprocess.Popen(
            ["terraform", "apply", "-input=false", "tfplan"],
            cwd=self.workdir,
            env=self.env,
        )

    def finish_apply(self, process: subprocess.Popen[bytes]) -> VmInfo:
        code = process.wait()
        self._delete_plan()
        if code != 0:
            raise TerraformError(f"terraform apply exited {code}.")
        return self.outputs()

    def destroy(self) -> None:
        if not (self.workdir / "terraform.tfstate").exists() and not (
            self.workdir / ".terraform"
        ).exists():
            return
        self.init()
        self._run(["terraform", "destroy", "-input=false", "-auto-approve"])

    def outputs(self) -> VmInfo:
        completed = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=self.workdir,
            env=self.env,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise TerraformError(completed.stderr.strip() or "terraform output failed.")
        data = json.loads(completed.stdout)
        return VmInfo(
            public_ip=data["public_ip"]["value"],
            resource_group=data["resource_group_name"]["value"],
            vm_name=data["vm_name"]["value"],
        )

    def _run(self, command: list[str]) -> None:
        completed = subprocess.run(command, cwd=self.workdir, env=self.env, check=False)
        if completed.returncode != 0:
            raise TerraformError(f"{' '.join(command)} exited {completed.returncode}.")

    def _delete_plan(self) -> None:
        plan = self.workdir / "tfplan"
        if plan.exists():
            plan.unlink()


def _require_terraform() -> None:
    if shutil.which("terraform") is None:
        raise TerraformError(
            "terraform is not on PATH. Install Terraform 1.6 or later and try again."
        )


def _terraform_env(config: Config, artifacts: Artifacts) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "TF_IN_AUTOMATION": "1",
            "ARM_SUBSCRIPTION_ID": config.azure_subscription_id,
            "TF_VAR_subscription_id": config.azure_subscription_id,
            "TF_VAR_location": config.azure_location,
            "TF_VAR_vm_size": "Standard_D8s_v5",
            "TF_VAR_windows_sku": "win11-24h2-pro",
            "TF_VAR_admin_username": config.vm_admin_username,
            "TF_VAR_admin_password": config.vm_admin_password,
            "TF_VAR_rdp_source_cidr": config.rdp_source_cidr,
            "TF_VAR_resource_group_name": "sql-interface-demo-rg",
            "TF_VAR_name_prefix": "sqldemo",
            "TF_VAR_odbc_url": artifacts.odbc_windows_url,
            "TF_VAR_connector_url": artifacts.powerbi_connector_url,
            "TF_VAR_schema_manager_windows_url": artifacts.schema_manager_windows_url,
        }
    )
    return env
