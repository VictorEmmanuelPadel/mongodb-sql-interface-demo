import pytest

from sql_demo.azure_cli import AzureCliError, ensure_azure_cli, install_commands


def test_install_uses_homebrew_on_macos() -> None:
    assert install_commands("darwin", lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None) == [
        ["brew", "install", "azure-cli"]
    ]


def test_install_uses_the_microsoft_script_on_debian() -> None:
    commands = install_commands("linux", lambda name: "/usr/bin/apt-get" if name == "apt-get" else None)
    assert commands == [["bash", "-c", "curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash"]]


def test_existing_cli_is_left_alone() -> None:
    calls: list[list[str]] = []
    ensure_azure_cli(
        require_login=True,
        which=lambda name: "/usr/bin/az" if name == "az" else None,
        run=lambda command: calls.append(command) or 0,
        signed_in=lambda: True,
    )
    assert calls == []


def test_missing_cli_is_installed_and_then_signs_in() -> None:
    present = {"az": False}
    calls: list[list[str]] = []

    def which(name: str) -> str | None:
        if name == "brew":
            return "/opt/homebrew/bin/brew"
        if name == "az" and present["az"]:
            return "/opt/homebrew/bin/az"
        return None

    def run(command: list[str]) -> int:
        calls.append(command)
        if command[0] == "brew":
            present["az"] = True
        return 0

    signed = {"value": False}

    def signed_in() -> bool:
        if calls and calls[-1] == ["az", "login"]:
            signed["value"] = True
        return signed["value"]

    ensure_azure_cli(
        require_login=True,
        platform="darwin",
        which=which,
        run=run,
        signed_in=signed_in,
    )
    assert calls == [["brew", "install", "azure-cli"], ["az", "login"]]


def test_missing_installer_is_reported() -> None:
    with pytest.raises(AzureCliError, match="Homebrew"):
        install_commands("darwin", lambda _name: None)
