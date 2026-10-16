"""Configure Atlas and the Azure Power BI VM from the env file."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import requests

from sql_demo.atlas import AtlasCli, cluster_srv_host
from sql_demo.azure_cli import current_subscription_id, ensure_azure_cli
from sql_demo.azure_run import publish_demo_files
from sql_demo.config import Config, resolve_password
from sql_demo.downloads import resolve_artifacts
from sql_demo.logutil import Steps, banner, details, log, note, ok, warn
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
    banner("MongoDB SQL Interface demo · setup")
    steps = Steps(
        ["Check the Atlas cluster", "Configure Atlas"]
        + ([] if config.skip_vm else ["Prepare this computer", "Create the Windows VM"])
        + ([] if config.skip_schema else ["Build the SQL schema"])
        + ["Write the connection guide"]
    )
    config = _prepare_runtime_config(config, output)

    steps.next()
    client = _atlas(config)
    client.ensure_login()
    cluster = client.get_cluster(config.atlas_cluster_name)
    _require_ready_cluster(cluster)
    status = client.sql_status(config.atlas_cluster_name)
    host = cluster_srv_host(cluster)
    rows = [
        ("Cluster", config.atlas_cluster_name),
        ("MongoDB", str(cluster.get("mongoDBVersion", "unknown"))),
        ("Host", host),
        ("SQL Interface", f"{status.get('status')} (supported: {status.get('supported')})"),
        ("Database", ", ".join(config.databases)),
    ]
    if status.get("unsupportedReason"):
        rows.append(("Unsupported", str(status["unsupportedReason"])))
    details("Cluster", rows)
    client._require_supported(status)
    artifacts = resolve_artifacts()

    steps.next()
    _configure_atlas(client, config)
    ok("atlas", "Atlas is configured.")

    vm: VmInfo | None = None
    if not config.skip_vm:
        steps.next()
        log("azure", f"Remote Desktop will be limited to {config.rdp_source_cidr}.")
        ensure_mac_remote_desktop()
        ensure_azure_cli(require_login=True)
        config = replace(config, azure_subscription_id=current_subscription_id())

        steps.next()
        log("azure", "Planning the Windows VM. Power BI installs during this step.")
        note("This step can take up to 30 minutes.")
        runner = TerraformRunner(config, artifacts, root / "terraform")
        try:
            vm = runner.finish_apply(runner.start_apply())
        except TerraformError:
            warn(
                "azure",
                "Terraform failed after Atlas was updated. Re-run setup after fixing "
                "Azure, or run destroy to remove a partial VM.",
            )
            raise
        print(flush=True)
        ok("azure", f"Windows VM is ready at {vm.public_ip}.")
        client.ensure_access_entries([(vm.public_ip, "sql-interface-demo Power BI VM")])

    _write_state(output, config, vm)
    credential_uri = schema_builder_uri(host, config.sql_username, config.sql_password)

    schemas: list[dict] = []
    if not config.skip_schema:
        steps.next()
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
        ok("schema", f"Wrote {len(schemas)} collection schemas:")
        for row in schemas:
            flag = " (unstable)" if row["unstable"] else ""
            log("schema", f"  • {row['database']}.{row['collection']}{flag}")

    steps.next()
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
    ok("setup", f"Wrote {connection.relative_to(root)} and sample-queries.sql.")

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

    banner("Demo is ready")
    if vm is not None:
        details(
            "Remote Desktop to the Windows VM",
            [
                ("Address", vm.public_ip),
                ("Username", config.vm_admin_username),
                ("Password", config.vm_admin_password),
                ("Allowed from", config.rdp_source_cidr),
            ],
        )
        if sys.platform == "darwin":
            note("  Open Windows App from Applications and add the address above.")
    details(
        "Power BI: Get data > MongoDB Atlas SQL",
        [
            ("MongoDB URI", power_bi_uri(host)),
            ("Database", config.primary_database),
            ("Username", config.sql_username),
            ("Password", config.sql_password),
        ],
    )
    print(flush=True)
    saved = f"Saved in {connection.relative_to(root)}."
    note(saved + (" The same guide is on the VM desktop." if vm is not None else ""))
    print(flush=True)


def destroy(config: Config, root: Path, *, purge_atlas: bool) -> None:
    output = root / "output"
    state = _read_state(output / "state.json")
    has_vm = (root / "terraform" / "terraform.tfstate").exists()
    banner("MongoDB SQL Interface demo · destroy")
    steps = Steps((["Delete the Windows VM"] if has_vm else []) + ["Clean up Atlas"])
    removed: list[str] = []
    if has_vm:
        steps.next()
        artifacts = resolve_artifacts(schema_manager_url="https://example.invalid/schema")
        if not config.rdp_source_cidr:
            config = replace(config, rdp_source_cidr="127.0.0.1/32")
        if not config.vm_admin_password:
            config = replace(config, vm_admin_password="Unused-Password1")
        ensure_azure_cli(require_login=True)
        config = replace(config, azure_subscription_id=current_subscription_id())
        TerraformRunner(config, artifacts, root / "terraform").destroy()
        print(flush=True)
        ok("azure", "Deleted the demo resource group.")
        removed.append("Azure resource group sql-interface-demo-rg and the Windows VM")

    steps.next()
    client = _atlas(config)
    client.ensure_login()
    vm_ip = str(state.get("vm_public_ip") or "")
    if vm_ip:
        client.delete_access_entry(vm_ip)
        state["vm_public_ip"] = ""
        _write_state_raw(output / "state.json", state)
        removed.append(f"Cluster firewall entry for the VM ({vm_ip})")

    kept = [
        f"Atlas cluster {config.atlas_cluster_name} and its data",
        "This computer's entry on the cluster firewall",
    ]
    if purge_atlas:
        username = str(state.get("sql_username") or config.sql_username)
        role = str(state.get("schema_role") or config.schema_role)
        cluster = str(state.get("atlas_cluster_name") or config.atlas_cluster_name)
        client.delete_database_user(username)
        client.delete_schema_role(role)
        client.disable_sql_interface(cluster)
        removed += [f"Database user {username}", f"Custom role {role}", "SQL Interface (turned OFF)"]
    else:
        kept += [
            "SQL Interface and the demo database user (use --purge-atlas to remove them)",
        ]

    banner("Destroy finished")
    print(flush=True)
    print("  Removed", flush=True)
    for item in removed or ["Nothing to remove"]:
        print(f"    ✓ {item}", flush=True)
    print(flush=True)
    print("  Kept", flush=True)
    for item in kept:
        print(f"    • {item}", flush=True)
    print(flush=True)


def _prepare_runtime_config(config: Config, output: Path) -> Config:
    sql_password = resolve_password(config.sql_password, output, "sql-password")
    vm_password = resolve_password(config.vm_admin_password, output, "vm-password")
    rdp_source = config.rdp_source_cidr
    if not config.skip_vm and not rdp_source:
        rdp_source = f"{_public_ip()}/32"
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
