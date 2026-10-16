from sql_demo.mac_remote import ensure_mac_remote_desktop


def test_non_mac_does_nothing() -> None:
    calls: list[list[str]] = []
    ensure_mac_remote_desktop(platform="linux", run=lambda command: calls.append(command) or 0)
    assert calls == []


def test_installed_app_is_left_alone() -> None:
    calls: list[list[str]] = []
    ensure_mac_remote_desktop(
        platform="darwin",
        run=lambda command: calls.append(command) or 0,
        installed=lambda: True,
    )
    assert calls == []


def test_missing_app_is_installed_with_homebrew() -> None:
    calls: list[list[str]] = []
    present = {"installed": False}

    def run(command: list[str]) -> int:
        calls.append(command)
        present["installed"] = True
        return 0

    ensure_mac_remote_desktop(
        platform="darwin",
        which=lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None,
        run=run,
        installed=lambda: present["installed"],
    )
    assert calls == [["brew", "install", "--cask", "windows-app"]]


def test_missing_homebrew_does_not_stop_setup(capsys) -> None:
    ensure_mac_remote_desktop(
        platform="darwin",
        which=lambda _name: None,
        installed=lambda: False,
    )
    assert "Mac App Store" in capsys.readouterr().out
