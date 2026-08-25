from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Final

from .runner_types import (
    ArgumentPolicy,
    CommandName,
    CommandSpec,
    EndpointName,
    EndpointSpec,
)

_MIB: Final[int] = 1024 * 1024
_DEFAULT_OUTPUT: Final[int] = 2 * _MIB

COMMAND_SPECS: Final = MappingProxyType(
    {
        CommandName.OMARCHY_UPDATE_AVAILABLE: CommandSpec(
            Path("/usr/bin/omarchy-update-available"),
            (),
            ArgumentPolicy.NONE,
            15,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.PACMAN_NATIVE: CommandSpec(
            Path("/usr/bin/pacman"),
            ("-Qn",),
            ArgumentPolicy.NONE,
            30,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.CHECKUPDATES: CommandSpec(
            Path("/usr/bin/checkupdates"),
            ("--nocolor",),
            ArgumentPolicy.NONE,
            120,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.VERCMP: CommandSpec(
            Path("/usr/bin/vercmp"),
            (),
            ArgumentPolicy.VERSION_PAIR,
            15,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.PACMAN_FOREIGN: CommandSpec(
            Path("/usr/bin/pacman"),
            ("-Qm",),
            ArgumentPolicy.NONE,
            30,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.YAY_UPDATES: CommandSpec(
            Path("/usr/bin/yay"),
            ("-Qua", "--color", "never"),
            ArgumentPolicy.NONE,
            60,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.PARU_UPDATES: CommandSpec(
            Path("/usr/bin/paru"),
            ("-Qua", "--color", "never"),
            ArgumentPolicy.NONE,
            60,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.FLATPAK_USER_APP_LIST: CommandSpec(
            Path("/usr/bin/flatpak"),
            (
                "--user",
                "list",
                "--app",
                "--columns=application,arch,branch,version,origin",
            ),
            ArgumentPolicy.NONE,
            60,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.FLATPAK_USER_RUNTIME_LIST: CommandSpec(
            Path("/usr/bin/flatpak"),
            (
                "--user",
                "list",
                "--runtime",
                "--columns=application,arch,branch,version,origin",
            ),
            ArgumentPolicy.NONE,
            60,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.FLATPAK_SYSTEM_APP_LIST: CommandSpec(
            Path("/usr/bin/flatpak"),
            (
                "--system",
                "list",
                "--app",
                "--columns=application,arch,branch,version,origin",
            ),
            ArgumentPolicy.NONE,
            60,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.FLATPAK_SYSTEM_RUNTIME_LIST: CommandSpec(
            Path("/usr/bin/flatpak"),
            (
                "--system",
                "list",
                "--runtime",
                "--columns=application,arch,branch,version,origin",
            ),
            ArgumentPolicy.NONE,
            60,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.FLATPAK_USER_UPDATES: CommandSpec(
            Path("/usr/bin/flatpak"),
            ("--user", "remote-ls", "--updates", "--columns=ref,version,origin"),
            ArgumentPolicy.NONE,
            60,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.FLATPAK_SYSTEM_UPDATES: CommandSpec(
            Path("/usr/bin/flatpak"),
            ("--system", "remote-ls", "--updates", "--columns=ref,version,origin"),
            ArgumentPolicy.NONE,
            60,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.MISE_OUTDATED: CommandSpec(
            Path("/usr/bin/mise"),
            ("outdated", "--json"),
            ArgumentPolicy.NONE,
            60,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
            Path.home(),
        ),
        CommandName.ARCH_AUDIT: CommandSpec(
            Path("/usr/bin/arch-audit"),
            ("--json",),
            ArgumentPolicy.NONE,
            30,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
        CommandName.NOTIFY: CommandSpec(
            Path("/usr/bin/notify-send"),
            ("-a", "Opatchy", "-u", "normal"),
            ArgumentPolicy.NOTIFICATION_TEXT,
            15,
            _DEFAULT_OUTPUT,
            _DEFAULT_OUTPUT,
        ),
    }
)

ENDPOINT_SPECS: Final = MappingProxyType(
    {
        EndpointName.ARCH_SECURITY: EndpointSpec(
            "https://security.archlinux.org/all.json",
            frozenset({"security.archlinux.org"}),
            frozenset({"/all.json"}),
            3,
            25 * _MIB,
            20,
        ),
        EndpointName.CISA_KEV: EndpointSpec(
            "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
            frozenset({"www.cisa.gov"}),
            frozenset(
                {"/sites/default/files/feeds/known_exploited_vulnerabilities.json"}
            ),
            3,
            10 * _MIB,
            20,
        ),
    }
)
