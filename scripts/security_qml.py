from __future__ import annotations

import codecs
import re
from typing import Final

_CONSTANT_PATTERN: Final = re.compile(
    r"\b(?:var|const|let)\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"
)
_TOKEN_PATTERN: Final = re.compile(
    r"(?P<string>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')|(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)|(?P<comma>,)|(?P<space>\s+)"
)
_STRING_PATTERN: Final = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'")
_NAME_PATTERN: Final = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_APPROVED_HANDOFFS: Final = frozenset(
    {
        (
            "/usr/bin/omarchy-launch-floating-terminal-with-presentation",
            "/usr/bin/omarchy-update",
        ),
        (
            "/usr/bin/omarchy-launch-floating-terminal-with-presentation",
            "/usr/bin/flatpak",
            "--user",
            "update",
        ),
        (
            "/usr/bin/omarchy-launch-floating-terminal-with-presentation",
            "/usr/bin/flatpak",
            "--system",
            "update",
        ),
    }
)
_PACKAGE_MANAGERS: Final = frozenset(
    {"/usr/bin/pacman", "/usr/bin/yay", "/usr/bin/paru", "/usr/bin/flatpak"}
)


def mutation_array_lines(text: str) -> tuple[int, ...]:
    constants = {
        match.group("name"): _unquote(match.group("value"))
        for match in _CONSTANT_PATTERN.finditer(text)
    }
    return tuple(
        text.count("\n", 0, offset) + 1
        for offset, content in _array_contents(text)
        if _is_package_manager_bearing(content, constants)
        and (
            (argv := _literal_argv(content, constants)) is None
            or _is_unapproved_mutation(argv)
        )
    )


def _array_contents(text: str) -> tuple[tuple[int, str], ...]:
    arrays: list[tuple[int, str]] = []
    starts: list[int] = []
    quote: str | None = None
    escaped = False
    depth = 0
    for index, character in enumerate(text):
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "[":
            starts.append(index)
            depth += 1
        elif character == "]" and depth > 0:
            depth -= 1
            start = starts.pop()
            arrays.append((start, text[start + 1 : index]))
    return tuple(arrays)


def _literal_argv(content: str, constants: dict[str, str]) -> tuple[str, ...] | None:
    values: list[str] = []
    position = 0
    needs_value = True
    for match in _TOKEN_PATTERN.finditer(content):
        if match.start() != position:
            return None
        position = match.end()
        if match.group("space") is not None:
            continue
        if match.group("comma") is not None:
            if needs_value:
                return None
            needs_value = True
            continue
        if not needs_value:
            return None
        token = match.group("string")
        values.append(
            _unquote(token)
            if token is not None
            else constants.get(match.group("name"), "")
        )
        needs_value = False
    if position != len(content) or needs_value:
        return None
    return tuple(values)


def _is_package_manager_bearing(content: str, constants: dict[str, str]) -> bool:
    entries = _top_level_entries(content)
    if not entries:
        return False
    executable = _entry_value(entries[0], constants)
    command = (
        entries[1] if executable == _launcher() and len(entries) > 1 else entries[0]
    )
    return _contains_package_manager(command, constants)


def _top_level_entries(content: str) -> list[str]:
    entries: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    depth = 0
    for index, character in enumerate(content):
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
        elif character == "," and depth == 0:
            entries.append(content[start:index])
            start = index + 1
    entries.append(content[start:])
    return entries


def _entry_value(entry: str, constants: dict[str, str]) -> str | None:
    argv = _literal_argv(entry.strip(), constants)
    if argv is None or len(argv) != 1:
        return None
    return argv[0]


def _contains_package_manager(entry: str, constants: dict[str, str]) -> bool:
    return any(
        _unquote(match.group()) in _PACKAGE_MANAGERS
        for match in _STRING_PATTERN.finditer(entry)
    ) or any(
        constants.get(match.group()) in _PACKAGE_MANAGERS
        for match in _NAME_PATTERN.finditer(entry)
    )


def _is_unapproved_mutation(argv: tuple[str, ...]) -> bool:
    executable = argv[0] if argv else ""
    if executable == _launcher():
        executable = argv[1] if len(argv) > 1 else ""
    return executable in _PACKAGE_MANAGERS and argv not in _APPROVED_HANDOFFS


def _launcher() -> str:
    return "/usr/bin/omarchy-launch-floating-terminal-with-presentation"


def _unquote(token: str) -> str:
    return codecs.decode(token[1:-1], "unicode_escape")
