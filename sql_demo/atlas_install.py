"""Install the Atlas CLI and start `atlas auth login` when needed."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from sql_demo.atlas import AtlasError
from sql_demo.logutil import log

_INSTALL_DOCS = "https://www.mongodb.com/docs/atlas/cli/current/install-atlas-cli/"


def ensure_atlas_cli(
    *,
    platform: str | None = None,
    which: Callable[[str], str | None] | None = None,
    run: Callable[[list[str]], int] | None = None,
    logged_in: Callable[[], bool] | None = None,
) -> None:
    """Install `atlas` when it is missing, then make sure an account is signed in."""
    finder = which or shutil.which
    system = platform or sys.platform
    if finder("atlas") is None:
        log("atlas", "Atlas CLI is not installed. Installing it. This can take a few minutes.")
        for command in install_commands(system, finder):
            code = _run(command, run)
            if code != 0:
                raise AtlasError(
                    f"{' '.join(command)} exited {code}. "
                    f"Install the Atlas CLI from {_INSTALL_DOCS} and run setup again."
                )
        if finder("atlas") is None and _known_atlas_binary() is None:
            raise AtlasError(
                "The Atlas CLI install finished, but `atlas` is not on PATH. "
                "Open a new terminal and run setup again."
            )
    if not _is_logged_in(logged_in):
        log("atlas", "Atlas CLI is not signed in. Starting atlas auth login.")
        code = _run(["atlas", "auth", "login"], run)
        if code != 0 or not _is_logged_in(logged_in):
            raise AtlasError("atlas auth login did not complete. Run `atlas auth login` and try again.")


def install_commands(platform: str, which: Callable[[str], str | None]) -> list[list[str]]:
    if platform == "darwin" or (platform.startswith("linux") and which("brew")):
        if which("brew") is None:
            raise AtlasError(
                "The Atlas CLI is not installed, and Homebrew is not available. "
                f"Install Homebrew from https://brew.sh, or install the Atlas CLI from {_INSTALL_DOCS}."
            )
        return [["brew", "install", "mongodb-atlas-cli"]]
    if platform == "win32" and which("winget"):
        return [
            [
                "winget",
                "install",
                "-e",
                "--id",
                "MongoDB.MongoDBAtlasCLI",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ]
        ]
    raise AtlasError(
        "The Atlas CLI is not installed, and this system has no supported installer. "
        f"Install it from {_INSTALL_DOCS} and run setup again."
    )


def _is_logged_in(logged_in: Callable[[], bool] | None) -> bool:
    if logged_in is not None:
        return logged_in()
    completed = subprocess.run(
        ["atlas", "auth", "whoami"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _run(command: list[str], run: Callable[[list[str]], int] | None) -> int:
    log("atlas", " ".join(command))
    if run is not None:
        return run(command)
    return subprocess.run(command, check=False).returncode


def _known_atlas_binary() -> str | None:
    for candidate in ("/opt/homebrew/bin/atlas", "/usr/local/bin/atlas", "/usr/bin/atlas"):
        if Path(candidate).is_file():
            return candidate
    return None
