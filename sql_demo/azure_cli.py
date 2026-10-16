"""Install the Azure CLI when a run needs `az login`."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from sql_demo.logutil import log, show_command

_INSTALL_DOCS = "https://learn.microsoft.com/cli/azure/install-azure-cli"
_DEB_INSTALL = "curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash"


class AzureCliError(RuntimeError):
    pass


def ensure_azure_cli(
    *,
    require_login: bool,
    platform: str | None = None,
    which: Callable[[str], str | None] | None = None,
    run: Callable[[list[str]], int] | None = None,
    signed_in: Callable[[], bool] | None = None,
) -> None:
    """Install `az` when it is missing, then make sure an account is signed in."""
    finder = which or shutil.which
    system = platform or sys.platform
    if finder("az") is None:
        log("azure", "Azure CLI is not installed. Installing it. This can take a few minutes.")
        for command in install_commands(system, finder):
            code = _run(command, run)
            if code != 0:
                raise AzureCliError(
                    f"{' '.join(command)} exited {code}. "
                    f"Install the Azure CLI from {_INSTALL_DOCS} and run setup again."
                )
        if finder("az") is None and _known_az_binary() is None:
            raise AzureCliError(
                "The Azure CLI install finished, but `az` is not on PATH. "
                "Open a new terminal and run setup again."
            )
    if require_login and not _is_signed_in(signed_in):
        log("azure", "Azure CLI is not signed in. Starting az login.")
        code = _run(["az", "login"], run)
        if code != 0 or not _is_signed_in(signed_in):
            raise AzureCliError("az login did not complete. Run `az login` and try again.")


def current_subscription_id() -> str:
    completed = subprocess.run(
        ["az", "account", "show", "--query", "id", "-o", "tsv"],
        check=False,
        capture_output=True,
        text=True,
    )
    subscription_id = completed.stdout.strip()
    if completed.returncode != 0 or not subscription_id:
        raise AzureCliError("Could not determine the active Azure subscription. Run `az login`.")
    return subscription_id


def install_commands(platform: str, which: Callable[[str], str | None]) -> list[list[str]]:
    if platform == "darwin" or (platform.startswith("linux") and which("brew")):
        if which("brew") is None:
            raise AzureCliError(
                "Azure CLI is not installed, and Homebrew is not available. "
                f"Install Homebrew from https://brew.sh, or install the Azure CLI from {_INSTALL_DOCS}."
            )
        return [["brew", "install", "azure-cli"]]
    if platform.startswith("linux") and which("apt-get"):
        return [["bash", "-c", _DEB_INSTALL]]
    if platform == "win32" and which("winget"):
        return [
            [
                "winget",
                "install",
                "-e",
                "--id",
                "Microsoft.AzureCLI",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ]
        ]
    raise AzureCliError(
        f"Azure CLI is not installed, and this system has no supported installer. "
        f"Install it from {_INSTALL_DOCS} and run setup again."
    )


def _is_signed_in(signed_in: Callable[[], bool] | None) -> bool:
    if signed_in is not None:
        return signed_in()
    completed = subprocess.run(
        ["az", "account", "show", "--query", "id", "-o", "tsv"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and bool(completed.stdout.strip())


def _run(command: list[str], run: Callable[[list[str]], int] | None) -> int:
    show_command("azure", " ".join(command))
    if run is not None:
        return run(command)
    return subprocess.run(command, check=False).returncode


def _known_az_binary() -> str | None:
    for candidate in ("/opt/homebrew/bin/az", "/usr/local/bin/az", "/usr/bin/az"):
        if Path(candidate).is_file():
            return candidate
    return None
