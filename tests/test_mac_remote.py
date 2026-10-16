from pathlib import Path

from sql_demo.mac_remote import (
    ensure_mac_remote_desktop,
    open_windows_connection,
    remove_windows_connection,
)


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


def test_open_connection_saves_the_bookmark_without_printing_the_password(capsys) -> None:
    calls: list[list[str]] = []
    app = Path("/Applications/Windows App.app")
    open_windows_connection(
        host="203.0.113.20",
        username="sqlInterfaceDemo",
        password="windows-secret",
        platform="darwin",
        app_path=app,
        run=lambda command: calls.append(command) or 0,
    )
    assert calls[0][:6] == [
        str(app / "Contents" / "MacOS" / "Windows App"),
        "--script",
        "bookmark",
        "write",
        "88442216",
        "--hostname",
    ]
    assert "203.0.113.20" in calls[0]
    assert "sqlInterfaceDemo" in calls[0]
    assert "windows-secret" in calls[0]
    assert calls[1] == ["open", "rdp://full%20address=s:203.0.113.20&username=s:sqlInterfaceDemo"]
    assert "windows-secret" not in capsys.readouterr().out


def test_remove_connection_deletes_the_saved_pc() -> None:
    calls: list[list[str]] = []
    app = Path("/Applications/Windows App.app")
    removed = remove_windows_connection(
        platform="darwin",
        app_path=app,
        run=lambda command: calls.append(command) or 0,
    )
    assert removed
    assert calls == [
        [
            str(app / "Contents" / "MacOS" / "Windows App"),
            "--script",
            "bookmark",
            "delete",
            "88442216",
        ]
    ]


def test_remove_connection_is_skipped_off_mac() -> None:
    calls: list[list[str]] = []
    removed = remove_windows_connection(
        platform="linux",
        run=lambda command: calls.append(command) or 0,
    )
    assert not removed
    assert calls == []


def test_open_connection_is_skipped_off_mac() -> None:
    calls: list[list[str]] = []
    open_windows_connection(
        host="203.0.113.20",
        username="sqlInterfaceDemo",
        password="windows-secret",
        platform="linux",
        run=lambda command: calls.append(command) or 0,
    )
    assert calls == []


def test_missing_homebrew_does_not_stop_setup(capsys) -> None:
    ensure_mac_remote_desktop(
        platform="darwin",
        which=lambda _name: None,
        installed=lambda: False,
    )
    assert "Mac App Store" in capsys.readouterr().out
