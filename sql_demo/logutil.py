"""Terminal output for the setup and destroy commands."""

from __future__ import annotations

import os
import sys

_WIDTH = 72
_COLORS = {"atlas": "32", "azure": "34", "schema": "35", "setup": "36"}


def _styled(text: str, code: str) -> str:
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def _tag(component: str) -> str:
    return _styled(f"{component:<6}", _COLORS.get(component, "37"))


def log(component: str, message: str) -> None:
    print(f"  {_tag(component)}  {message}", flush=True)


def show_command(component: str, text: str) -> None:
    print(f"  {_tag(component)}  {_styled('$ ' + text, '2')}", flush=True)


def ok(component: str, message: str) -> None:
    print(f"  {_tag(component)}  {_styled('✓', '32;1')} {message}", flush=True)


def warn(component: str, message: str) -> None:
    print(f"  {_tag(component)}  {_styled('! ' + message, '33;1')}", flush=True)


def banner(title: str) -> None:
    rule = "═" * _WIDTH
    print(flush=True)
    print(_styled(rule, "1"), flush=True)
    print(_styled(f"  {title}", "1"), flush=True)
    print(_styled(rule, "1"), flush=True)


class Steps:
    """Numbered section headers, such as `[2/5] Prepare this computer`."""

    def __init__(self, titles: list[str]) -> None:
        self._titles = titles
        self._index = 0

    def next(self) -> None:
        self._index += 1
        title = self._titles[self._index - 1]
        label = f"[{self._index}/{len(self._titles)}] {title} "
        print(flush=True)
        print(_styled(label + "─" * max(4, _WIDTH - len(label)), "1;36"), flush=True)


def details(title: str, rows: list[tuple[str, str]]) -> None:
    """Print an indented block of labelled values."""
    print(flush=True)
    print(f"  {_styled(title, '1')}", flush=True)
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"    {_styled(label.ljust(width), '2')}   {value}", flush=True)


def note(message: str) -> None:
    print(f"  {_styled(message, '2')}", flush=True)


def error(message: str) -> None:
    print(file=sys.stderr, flush=True)
    text = f"✗ {message}"
    if not os.environ.get("NO_COLOR") and sys.stderr.isatty():
        text = f"\033[31;1m{text}\033[0m"
    print(text, file=sys.stderr, flush=True)
