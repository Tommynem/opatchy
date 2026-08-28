from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PYTHON_ROOTS: Final = (
    ROOT / "helper" / "opatchy.py",
    ROOT / "helper" / "opatchy_helper",
)
QML_ROOTS: Final = (ROOT / "qml",)
PROCESS_ALLOWLIST: Final = frozenset(
    {
        ROOT / "helper" / "opatchy_helper" / "runner_process.py",
        ROOT / "helper" / "opatchy_helper" / "command_supervisor.py",
    }
)
QML_PROCESS_ALLOWLIST: Final = frozenset(
    {
        ROOT / "qml" / "models" / "HelperTransport.qml",
        ROOT / "qml" / "models" / "TerminalHandoff.qml",
    }
)
URL_ALLOWLIST: Final = (
    "https://security.archlinux.org/all.json",
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
    "https://security.archlinux.org/",
    "https://www.cve.org/CVERecord?id=",
)
QML_IMPORTS: Final = frozenset(
    {"QtQml", "QtQuick", "Quickshell.Io", "qs.Commons", "qs.Ui"}
)
OVERSIZED_ALLOWLIST: Final = frozenset(
    {ROOT / "helper" / "opatchy_helper" / "payload_parser.py"}
)
MUTATION_PATTERN: Final = re.compile(
    r"(?:pacman|yay|paru|flatpak)[^\n]{0,160}(?:-(?:S|R|U)[A-Za-z]*|--(?:sync|remove|install|uninstall|upgrade)|\b(?:install|uninstall|remove|upgrade)\b)"
)
SHELL_PATTERN: Final = re.compile(
    r"shell\s*=\s*True|\bos\.(?:system|popen)\(|\b(?:eval|exec)\("
)
RICH_TEXT_PATTERN: Final = re.compile(
    r"Text\.RichText|textFormat\s*:\s*[^\n]*RichText|<(?:a|b|br|em|font|i|img|p|span|strong)\b",
    re.IGNORECASE,
)
URL_PATTERN: Final = re.compile(r"https?://[^\s\"']+")
PALETTE_PATTERN: Final = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|(?:Qt\.)?(?:rgb|rgba|hsl|hsla|hsv|hsva)\s*\("
)


@dataclass(frozen=True, slots=True)
class Violation:
    rule: str
    path: Path
    line: int


def _product_files() -> tuple[Path, ...]:
    python_files = (PYTHON_ROOTS[0], *sorted(PYTHON_ROOTS[1].rglob("*.py")))
    qml_files = (
        *sorted(ROOT.glob("*.qml")),
        *sorted(
            path for path in QML_ROOTS[0].rglob("*") if path.suffix in {".js", ".qml"}
        ),
    )
    return tuple(path for path in (*python_files, *qml_files) if path.exists())


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _scan_text(path: Path, text: str) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    if path.suffix == ".py":
        violations.extend(_python_violations(path, text))
    else:
        violations.extend(_qml_violations(path, text))
    return tuple(violations)


def _python_violations(path: Path, text: str) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    for pattern, rule in (
        (MUTATION_PATTERN, "mutation-command"),
        (SHELL_PATTERN, "shell-api"),
    ):
        for match in pattern.finditer(text):
            violations.append(Violation(rule, path, _line_number(text, match.start())))
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as error:
        return (*violations, Violation("invalid-python", path, error.lineno or 1))
    for node in ast.walk(tree):
        match node:
            case ast.Import(names=names):
                violations.extend(_import_violations(path, names, node.lineno))
            case ast.ImportFrom(level=0, module=module, names=names):
                violations.extend(
                    _from_import_violations(path, module, names, node.lineno)
                )
            case ast.Call(func=ast.Name(id="__import__"), args=args):
                violations.extend(_dynamic_import_violations(path, args, node.lineno))
            case ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="importlib"), attr="import_module"
                ),
                args=args,
            ):
                violations.extend(_dynamic_import_violations(path, args, node.lineno))
            case ast.Call(
                func=ast.Attribute(value=ast.Name(id="subprocess"), attr=method)
            ):
                if path not in PROCESS_ALLOWLIST or method != "Popen":
                    violations.append(Violation("shell-api", path, node.lineno))
            case _:
                continue
    return tuple(violations)


def _dynamic_import_violations(
    path: Path, args: list[ast.expr], line: int
) -> tuple[Violation, ...]:
    if (
        not args
        or not isinstance(args[0], ast.Constant)
        or not isinstance(args[0].value, str)
    ):
        return (Violation("runtime-dependency", path, line),)
    module = args[0].value.partition(".")[0]
    if module in sys.stdlib_module_names or module == "opatchy_helper":
        return ()
    return (Violation("runtime-dependency", path, line),)


def _import_violations(
    path: Path, names: list[ast.alias], line: int
) -> tuple[Violation, ...]:
    return tuple(
        Violation("runtime-dependency", path, line)
        for name in names
        if name.name.partition(".")[0] not in sys.stdlib_module_names
        and name.name.partition(".")[0] != "opatchy_helper"
    )


def _from_import_violations(
    path: Path, module: str | None, names: list[ast.alias], line: int
) -> tuple[Violation, ...]:
    _ = names
    if module is None or module.partition(".")[0] in sys.stdlib_module_names:
        return ()
    if module.partition(".")[0] == "opatchy_helper":
        return ()
    return (Violation("runtime-dependency", path, line),)


def _qml_violations(path: Path, text: str) -> tuple[Violation, ...]:
    from scripts.security_qml import mutation_array_lines

    violations: list[Violation] = []
    for pattern, rule in (
        (RICH_TEXT_PATTERN, "rich-text"),
        (PALETTE_PATTERN, "hardcoded-palette"),
    ):
        for match in pattern.finditer(text):
            violations.append(Violation(rule, path, _line_number(text, match.start())))
    violations.extend(
        Violation("mutation-command", path, line) for line in mutation_array_lines(text)
    )
    for match in URL_PATTERN.finditer(text):
        if not match.group().startswith(URL_ALLOWLIST):
            violations.append(
                Violation("unsafe-url", path, _line_number(text, match.start()))
            )
    if path not in QML_PROCESS_ALLOWLIST:
        for match in re.finditer(r"\bProcess\s*{", text):
            violations.append(
                Violation("shell-api", path, _line_number(text, match.start()))
            )
    if path != ROOT / "qml" / "components" / "SafeExternalLink.qml":
        for match in re.finditer(r"\bQt\.openUrlExternally\(", text):
            violations.append(
                Violation("unsafe-url", path, _line_number(text, match.start()))
            )
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"\s*import\s+([^\s]+)", line)
        if match is not None and not _allowed_qml_import(match.group(1)):
            violations.append(Violation("runtime-dependency", path, line_number))
    return tuple(violations)


def _allowed_qml_import(module: str) -> bool:
    return module.startswith('"') or module in QML_IMPORTS


def _size_violations(path: Path, text: str) -> tuple[Violation, ...]:
    lines = tuple(
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "//"))
    )
    if len(lines) > 250 and path not in OVERSIZED_ALLOWLIST:
        return (Violation("oversized-module", path, 251),)
    return ()


def main() -> int:
    violations = tuple(
        violation
        for path in _product_files()
        for text in (path.read_text(encoding="utf-8"),)
        for violation in (*_scan_text(path, text), *_size_violations(path, text))
    )
    if violations:
        for violation in violations:
            print(
                f"SECURITY POLICY VIOLATION({violation.rule}): {violation.path.relative_to(ROOT)}:{violation.line}",
                file=sys.stderr,
            )
        return 1
    print("PASS(security-policy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
