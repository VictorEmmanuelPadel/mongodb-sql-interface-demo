"""Install Windows App on a Mac and open the demo VM."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from sql_demo.logutil import log, ok, show_command, warn

_APP_STORE = "https://apps.apple.com/app/windows-app/id1295203466"
_APP_NAMES = ("Windows App.app", "Microsoft Remote Desktop.app")
_BOOKMARK_ID = "88442216"


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
    ok("setup", "Windows App is installed. Setup will open the VM in it when the VM is ready.")


def open_windows_connection(
    *,
    host: str,
    username: str,
    password: str,
    platform: str | None = None,
    run: Callable[[list[str]], int] | None = None,
    app_path: Path | None = None,
) -> None:
    """Save the VM in Windows App and open the connection. Other systems use their own client."""
    if (platform or sys.platform) != "darwin":
        return
    app = app_path if app_path is not None else _app_path()
    if app is None:
        warn("setup", f"Windows App is not installed. Install it from {_APP_STORE} and add {host}.")
        return
    binary = app / "Contents" / "MacOS" / app.stem
    log("setup", f"Opening {host} in Windows App.")
    saved = _run(
        [
            str(binary),
            "--script",
            "bookmark",
            "write",
            _BOOKMARK_ID,
            "--hostname",
            host,
            "--username",
            username,
            "--password",
            password,
            "--friendlyname",
            "SQL Interface Demo",
            "--group",
            "SQL Interface Demo",
            "--fullscreen",
            "false",
        ],
        run,
    )
    if saved != 0:
        warn("setup", "Could not save the VM in Windows App. Add it with the details printed above.")
        return
    address = quote(host, safe=".:")
    user = quote(username, safe="")
    opened = _run(["open", f"rdp://full%20address=s:{address}&username=s:{user}"], run)
    if opened != 0:
        warn("setup", "Saved the VM in Windows App, but could not open the connection.")
        return
    ok("setup", "Windows App is opening the VM. Accept the certificate warning if this is the first connection.")


def remove_windows_connection(
    *,
    platform: str | None = None,
    run: Callable[[list[str]], int] | None = None,
    app_path: Path | None = None,
) -> bool:
    """Delete the demo PC from Windows App. Missing bookmarks count as already removed."""
    if (platform or sys.platform) != "darwin":
        return False
    app = app_path if app_path is not None else _app_path()
    if app is None:
        return False
    binary = app / "Contents" / "MacOS" / app.stem
    log("setup", "Removing the SQL Interface Demo PC from Windows App.")
    command = [str(binary), "--script", "bookmark", "delete", _BOOKMARK_ID]
    if run is not None:
        if _run(command, run) != 0:
            warn("setup", "Could not remove the SQL Interface Demo PC from Windows App.")
            return False
        ok("setup", "Removed the SQL Interface Demo PC from Windows App.")
        return True
    show_command("setup", " ".join(command))
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    output = f"{completed.stdout}\n{completed.stderr}".lower()
    if completed.returncode == 0:
        ok("setup", "Removed the SQL Interface Demo PC from Windows App.")
        return True
    if "does not exist" in output or "not found" in output:
        return False
    warn("setup", "Could not remove the SQL Interface Demo PC from Windows App.")
    return False


def _app_path() -> Path | None:
    folders = [Path("/Applications"), Path.home() / "Applications"]
    for folder in folders:
        for name in _APP_NAMES:
            path = folder / name
            if path.exists():
                return path
    return None


def _app_installed() -> bool:
    return _app_path() is not None


def _run(command: list[str], run: Callable[[list[str]], int] | None) -> int:
    show_command("setup", " ".join(_redact(command)))
    if run is not None:
        return run(command)
    return subprocess.run(command, check=False).returncode


def _redact(command: list[str]) -> list[str]:
    redacted: list[str] = []
    hide_next = False
    for part in command:
        if hide_next:
            redacted.append("***")
            hide_next = False
            continue
        redacted.append(part)
        hide_next = part == "--password"
    return redacted
