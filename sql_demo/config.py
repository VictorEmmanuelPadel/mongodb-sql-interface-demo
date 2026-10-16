"""Environment configuration for the demo."""

from __future__ import annotations

import os
import re
import secrets
import string
from collections.abc import Mapping
from dataclasses import dataclass


class ConfigError(ValueError):
    """The env file is missing a value or contains an invalid one."""


def parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def generate_password(length: int = 24) -> str:
    if length < 12:
        raise ValueError("length must be at least 12")
    required = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
    ]
    pool = string.ascii_letters + string.digits
    chars = required + [secrets.choice(pool) for _ in range(length - len(required))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def resolve_password(supplied: str) -> str:
    """Use the supplied password, otherwise generate one."""
    return supplied or generate_password()


def validate_vm_password(password: str) -> None:
    if len(password) < 12 or len(password) > 123:
        raise ConfigError("VM_ADMIN_PASSWORD must be 12 to 123 characters.")
    categories = (
        any(char.islower() for char in password),
        any(char.isupper() for char in password),
        any(char.isdigit() for char in password),
        any(not char.isalnum() for char in password),
    )
    if sum(categories) < 3:
        raise ConfigError(
            "VM_ADMIN_PASSWORD must include at least three of: "
            "lowercase, uppercase, digit, symbol."
        )


_RESERVED_WINDOWS_USERS = {
    "admin",
    "administrator",
    "guest",
    "root",
    "user",
    "azure",
    "defaultaccount",
}


@dataclass(frozen=True)
class Config:
    atlas_project_id: str
    atlas_cluster_name: str
    databases: tuple[str, ...]
    sql_username: str = "sql-demo"
    sql_password: str = ""
    azure_subscription_id: str = ""
    azure_location: str = "eastus"
    vm_admin_username: str = "sqlInterfaceDemo"
    vm_admin_password: str = ""
    rdp_source_cidr: str = ""
    skip_vm: bool = False
    skip_schema: bool = False

    @property
    def primary_database(self) -> str:
        return self.databases[0]

    @property
    def schema_role(self) -> str:
        return "sqlSchemaWriter"

    @property
    def schema_ns_include(self) -> tuple[str, ...]:
        return tuple(f"{database}.*" for database in self.databases)

    @classmethod
    def from_env(cls) -> Config:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, env: Mapping[str, str]) -> Config:
        def get(name: str, default: str = "") -> str:
            value = env.get(name, default)
            return "" if value is None else str(value).strip()

        def require(name: str) -> str:
            value = get(name)
            if not value:
                raise ConfigError(f"{name} is required.")
            return value

        project_id = require("ATLAS_PROJECT_ID")
        if not re.fullmatch(r"[a-fA-F0-9]{24}", project_id):
            raise ConfigError("ATLAS_PROJECT_ID must be a 24-character hex project id.")

        databases = parse_csv(require("ATLAS_DATABASE"))
        if any(not re.fullmatch(r"[A-Za-z0-9_\-.]{1,64}", db) for db in databases):
            raise ConfigError(
                "ATLAS_DATABASE entries must be 1-64 letters, numbers, dots, "
                "underscores, or hyphens."
            )

        sql_username = get("SQL_USERNAME", "sql-demo") or "sql-demo"
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._\-]{0,62}", sql_username):
            raise ConfigError(
                "SQL_USERNAME must start with a letter and contain only letters, "
                "numbers, dots, underscores, or hyphens."
            )
        vm_username = get("VM_ADMIN_USERNAME", "sqlInterfaceDemo") or "sqlInterfaceDemo"
        if vm_username.lower() in _RESERVED_WINDOWS_USERS:
            raise ConfigError(f"VM_ADMIN_USERNAME {vm_username!r} is reserved by Windows.")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{2,19}", vm_username):
            raise ConfigError(
                "VM_ADMIN_USERNAME must be 3-20 letters and digits and start with a letter."
            )

        sql_password = get("SQL_PASSWORD")
        vm_password = get("VM_ADMIN_PASSWORD")
        if vm_password:
            validate_vm_password(vm_password)
        location = get("AZURE_LOCATION", "eastus") or "eastus"
        if not re.fullmatch(r"[a-z0-9]{1,32}", location):
            raise ConfigError(
                "AZURE_LOCATION must be an Azure region name such as eastus or westus2."
            )

        return cls(
            atlas_project_id=project_id,
            atlas_cluster_name=require("ATLAS_CLUSTER_NAME"),
            databases=databases,
            sql_username=sql_username,
            sql_password=sql_password,
            azure_location=location,
            vm_admin_username=vm_username,
            vm_admin_password=vm_password,
        )
