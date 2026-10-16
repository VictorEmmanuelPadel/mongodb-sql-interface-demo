"""Install Windows App on a Mac so the operator can open the demo VM."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from sql_demo.logutil import log, ok, show_command, warn

_APP_STORE = "https://apps.apple.com/app/windows-app/id1295203466"
_APP_NAMES = ("Windows App.app", "Microsoft Remote Desktop.app")


def ensure_mac_remote_desktop(
    *,
    platform: str | None = None,
    which: Callable[[str], str | None] | None = None,
    run: Callable[[list[str]], int] | None = None,
    installed: Callable[[], bool] | None = None,
) -> None:
    """Install Windows App on macOS. Other systems already have a Remote Desktop client."""
    if (platform or sys.platform) != "darwin":
        return
    if (installed or _app_installed)():
        ok("setup", "Windows App is already installed.")
        return
    finder = which or shutil.which
    if finder("brew") is None:
        warn("setup", f"Install Windows App from the Mac App Store to open the VM: {_APP_STORE}")
        return
    log("setup", "Installing Windows App so you can open the VM. macOS may ask for your password.")
    code = _run(["brew", "install", "--cask", "windows-app"], run)
    if code != 0 or not (installed or _app_installed)():
        warn(
            "setup",
            "Could not install Windows App automatically. "
            f"Install it from the Mac App Store: {_APP_STORE}",
        )
        return
    ok("setup", "Windows App is installed. Add the VM address there after setup finishes.")


def _app_installed() -> bool:
    folders = [Path("/Applications"), Path.home() / "Applications"]
    return any((folder / name).exists() for folder in folders for name in _APP_NAMES)


def _run(command: list[str], run: Callable[[list[str]], int] | None) -> int:
    show_command("setup", " ".join(command))
    if run is not None:
        return run(command)
    return subprocess.run(command, check=False).returncode
