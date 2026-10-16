import pytest

from sql_demo.atlas import AtlasError
from sql_demo.atlas_install import ensure_atlas_cli, install_commands


def test_install_uses_homebrew_on_macos() -> None:
    assert install_commands("darwin", lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None) == [
        ["brew", "install", "mongodb-atlas-cli"]
    ]


def test_existing_cli_starts_login_when_signed_out() -> None:
    calls: list[list[str]] = []
    signed = {"value": False}

    def run(command: list[str]) -> int:
        calls.append(command)
        if command == ["atlas", "auth", "login"]:
            signed["value"] = True
        return 0

    ensure_atlas_cli(
        which=lambda name: "/opt/homebrew/bin/atlas" if name == "atlas" else None,
        run=run,
        logged_in=lambda: signed["value"],
    )
    assert calls == [["atlas", "auth", "login"]]


def test_missing_cli_is_installed_before_login() -> None:
    present = {"atlas": False}
    calls: list[list[str]] = []

    def which(name: str) -> str | None:
        if name == "brew":
            return "/opt/homebrew/bin/brew"
        if name == "atlas" and present["atlas"]:
            return "/opt/homebrew/bin/atlas"
        return None

    def run(command: list[str]) -> int:
        calls.append(command)
        if command[0] == "brew":
            present["atlas"] = True
        return 0

    ensure_atlas_cli(
        platform="darwin",
        which=which,
        run=run,
        logged_in=lambda: calls[-1:] == [["atlas", "auth", "login"]],
    )
    assert calls == [["brew", "install", "mongodb-atlas-cli"], ["atlas", "auth", "login"]]


def test_missing_installer_is_reported() -> None:
    with pytest.raises(AtlasError, match="Homebrew"):
        install_commands("darwin", lambda _name: None)
