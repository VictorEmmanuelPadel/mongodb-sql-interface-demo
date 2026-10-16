"""Command line entry point.

    python -m sql_demo check
    python -m sql_demo setup
    python -m sql_demo destroy
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

import requests
from dotenv import load_dotenv

from sql_demo.atlas import AtlasError
from sql_demo.azure_cli import AzureCliError
from sql_demo.config import Config, ConfigError
from sql_demo.orchestrator import check, destroy, setup
from sql_demo.terraform_runner import TerraformError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Configure a MongoDB Atlas SQL Interface demo for a dedicated cluster and Power BI."
    )
    parser.add_argument("--env", default=".env", help="Path to the env file. Defaults to .env.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="Verify Atlas credentials and whether the cluster supports SQL.")

    setup_parser = subparsers.add_parser("setup", help="Enable SQL, create the database user, and build the VM.")
    setup_parser.add_argument("--skip-vm", action="store_true", help="Configure Atlas only.")
    setup_parser.add_argument("--skip-schema", action="store_true", help="Do not run the schema builder.")

    destroy_parser = subparsers.add_parser("destroy", help="Delete the Azure VM and its cluster firewall entry.")
    destroy_parser.add_argument(
        "--purge-atlas",
        action="store_true",
        help="Also delete the demo database user and turn the SQL Interface off.",
    )

    args = parser.parse_args(argv)
    try:
        root = Path.cwd()
        if not (root / "terraform").is_dir():
            raise ConfigError("Run this command from the repository root.")
        _load_environment(Path(args.env))
        skip_vm = bool(getattr(args, "skip_vm", False))
        config = Config.from_env()
        if args.command == "check":
            check(config)
        elif args.command == "setup":
            updates = {}
            if skip_vm:
                updates["skip_vm"] = True
            if args.skip_schema:
                updates["skip_schema"] = True
            if updates:
                config = replace(config, **updates)
            setup(config, root)
        else:
            destroy(config, root, purge_atlas=args.purge_atlas)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    except (AtlasError, AzureCliError, TerraformError, TimeoutError, RuntimeError, requests.RequestException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def _load_environment(path: Path) -> None:
    if path.exists():
        load_dotenv(path, override=False)
        return
    if not os.environ.get("ATLAS_CLUSTER_NAME"):
        raise ConfigError(f"Missing {path}. Copy .env.example to .env and fill in the values.")


if __name__ == "__main__":
    raise SystemExit(main())
