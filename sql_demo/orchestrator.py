"""Configure Atlas and the Azure Power BI VM from the env file."""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import requests

from sql_demo.atlas import AtlasCli, cluster_srv_host
from sql_demo.azure_cli import current_subscription_id, ensure_azure_cli
from sql_demo.azure_run import publish_demo_files
from sql_demo.config import Config, resolve_password
from sql_demo.downloads import resolve_artifacts
from sql_demo.logutil import log
from sql_demo.mac_remote import ensure_mac_remote_desktop
from sql_demo.schema_build import (
    download_schema_manager,
    run_schema_manager,
    verify_schemas,
)
from sql_demo.terraform_runner import TerraformError, TerraformRunner, VmInfo
from sql_demo.uriutil import power_bi_uri, schema_builder_uri
from sql_demo.vm_guide import render_guide, sample_sql


def setup(config: Config, root: Path) -> None:
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    config = _prepare_runtime_config(config, output)

    client = _atlas(config)
    client.ensure_login()
    cluster = client.get_cluster(config.atlas_cluster_name)
    _require_ready_cluster(cluster)
    status = client.sql_status(config.atlas_cluster_name)
    version = cluster.get("mongoDBVersion", "unknown")
    log("atlas", f"Cluster {config.atlas_cluster_name} is MongoDB {version}.")
    log("atlas", f"SQL Interface status={status.get('status')} supported={status.get('supported')}.")
    if status.get("unsupportedReason"):
        log("atlas", f"Unsupported reason: {status['unsupportedReason']}.")
    log("atlas", f"Database: {config.primary_database}")
    client._require_supported(status)
    host = cluster_srv_host(cluster)
    log("atlas", f"Cluster host is {host}.")

    artifacts = resolve_artifacts()
    log("atlas", "Resolved the schema builder download.")

    runner: TerraformRunner | None = None
    apply_process = None
    if not config.skip_vm:
        ensure_mac_remote_desktop()
        ensure_azure_cli(require_login=True)
        config = replace(config, azure_subscription_id=current_subscription_id())
        runner = TerraformRunner(config, artifacts, root / "terraform")
        log("azure", "Planning the Windows VM. Power BI installation runs during apply.")
        apply_process = runner.start_apply()

    try:
        _configure_atlas(client, config)
    except Exception:
        if apply_process is not None and apply_process.poll() is None:
            log("azure", "Stopping the Terraform apply because Atlas setup failed.")
            apply_process.terminate()
            try:
                apply_process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                apply_process.kill()
                apply_process.wait(timeout=30)
        if runner is not None:
            runner._delete_plan()
        raise

    vm: VmInfo | None = None
    if runner is not None and apply_process is not None:
        try:
            vm = runner.finish_apply(apply_process)
        except TerraformError:
            log(
                "azure",
                "Terraform failed after Atlas was updated. Re-run setup after fixing "
                "Azure, or run destroy to remove a partial VM.",
            )
            raise
        log("azure", f"VM public IP is {vm.public_ip}.")
        client.ensure_access_entries([(vm.public_ip, "sql-interface-demo Power BI VM")])

    _write_state(output, config, vm)
    credential_uri = schema_builder_uri(host, config.sql_username, config.sql_password)

    schemas: list[dict] = []
    if not config.skip_schema:
        binary = download_schema_manager(
            artifacts.schema_manager_url,
            root / ".tools" / "mongodb-schema-manager",
        )
        run_schema_manager(
            binary,
            uri=credential_uri,
            patterns=config.schema_ns_include,
            log_dir=output / "schema-logs",
            jobs=2,
            action="merge",
            timeout_seconds=3600,
        )
        schemas = verify_schemas(credential_uri, config.databases)
        for row in schemas:
            flag = " (unstable)" if row["unstable"] else ""
            log("schema", f"{row['database']}.{row['collection']}{flag}")

    guide = render_guide(
        config,
        host=host,
        power_bi_uri=power_bi_uri(host),
        vm_public_ip=vm.public_ip if vm else "",
        schemas=schemas,
    )
    queries = sample_sql(
        config.primary_database,
        [str(row["collection"]) for row in schemas if row["database"] == config.primary_database],
    )
    connection = output / "demo-connection.txt"
    connection.write_text(guide, encoding="utf-8")
    connection.chmod(0o600)
    (output / "sample-queries.sql").write_text(queries, encoding="utf-8")
    log("setup", f"Wrote {connection}.")

    if vm is not None:
        publish_demo_files(
            config,
            vm,
            {
                r"C:\Users\Public\Desktop\MongoDB SQL Interface Demo.txt": guide,
                r"C:\SQLInterfaceDemo\README.txt": guide,
                r"C:\SQLInterfaceDemo\sample-queries.sql": queries,
            },
        )
        log("setup", f"RDP to {vm.public_ip} as {config.vm_admin_username}.")
        log("setup", f"Windows password: {config.vm_admin_password}")
        log("setup", f"Remote Desktop is allowed from {config.rdp_source_cidr}.")

    log("setup", f"Power BI database user: {config.sql_username}")
    log("setup", f"Power BI password: {config.sql_password}")
    log("setup", f"Power BI URI: {power_bi_uri(host)}")
    log("setup", f"Database: {config.primary_database}")


def destroy(config: Config, root: Path, *, purge_atlas: bool) -> None:
    output = root / "output"
    state = _read_state(output / "state.json")
    if (root / "terraform" / "terraform.tfstate").exists():
        artifacts = resolve_artifacts(schema_manager_url="https://example.invalid/schema")
        if not config.rdp_source_cidr:
            config = replace(config, rdp_source_cidr="127.0.0.1/32")
        if not config.vm_admin_password:
            config = replace(config, vm_admin_password="Unused-Password1")
        ensure_azure_cli(require_login=True)
        config = replace(config, azure_subscription_id=current_subscription_id())
        TerraformRunner(config, artifacts, root / "terraform").destroy()
        log("azure", "Deleted the demo resource group.")

    client = _atlas(config)
    client.ensure_login()
    vm_ip = str(state.get("vm_public_ip") or "")
    if vm_ip:
        client.delete_access_entry(vm_ip)
        state["vm_public_ip"] = ""
        _write_state_raw(output / "state.json", state)

    if not purge_atlas:
        log("setup", "Left the SQL Interface and database user in place. Use --purge-atlas to remove them.")
        return

    username = str(state.get("sql_username") or config.sql_username)
    role = str(state.get("schema_role") or config.schema_role)
    cluster = str(state.get("atlas_cluster_name") or config.atlas_cluster_name)
    client.delete_database_user(username)
    client.delete_schema_role(role)
    client.disable_sql_interface(cluster)


def _prepare_runtime_config(config: Config, output: Path) -> Config:
    sql_password = resolve_password(config.sql_password, output, "sql-password")
    vm_password = resolve_password(config.vm_admin_password, output, "vm-password")
    rdp_source = config.rdp_source_cidr
    if not config.skip_vm and not rdp_source:
        rdp_source = f"{_public_ip()}/32"
        log("azure", f"RDP will be limited to {rdp_source}.")
    return replace(
        config,
        sql_password=sql_password,
        vm_admin_password=vm_password,
        rdp_source_cidr=rdp_source,
    )


def _atlas(config: Config) -> AtlasCli:
    return AtlasCli(config.atlas_project_id)


def _configure_atlas(client: AtlasCli, config: Config) -> None:
    client.enable_sql_interface(config.atlas_cluster_name)
    client.ensure_schema_role(config.schema_role, config.databases)
    client.ensure_database_user(
        username=config.sql_username,
        password=config.sql_password,
        databases=config.databases,
        schema_role=config.schema_role,
        cluster_name=config.atlas_cluster_name,
        scope_to_cluster=True,
    )
    client.allow_current_ip("sql-interface-demo schema builder")


def _require_ready_cluster(cluster: dict) -> None:
    if cluster.get("paused"):
        raise RuntimeError("The cluster is paused. Resume it in Atlas before running setup.")


def _public_ip() -> str:
    response = requests.get("https://api.ipify.org", timeout=20)
    response.raise_for_status()
    address = response.text.strip()
    if not address:
        raise RuntimeError("Could not detect this machine's public IP.")
    return address


def _write_state(output: Path, config: Config, vm: VmInfo | None) -> None:
    payload = {
        "atlas_project_id": config.atlas_project_id,
        "atlas_cluster_name": config.atlas_cluster_name,
        "sql_username": config.sql_username,
        "schema_role": config.schema_role,
        "databases": list(config.databases),
        "vm_public_ip": vm.public_ip if vm else "",
        "resource_group_name": vm.resource_group if vm else "",
        "vm_name": vm.vm_name if vm else "",
    }
    _write_state_raw(output / "state.json", payload)


def _write_state_raw(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
