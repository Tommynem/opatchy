# Contributing to Opatchy

Thanks for helping improve Opatchy. Small, focused changes are easiest to
review. Start by reading the README, [architecture](docs/architecture.md), and
[threat model](docs/threat-model.md).

## Before you start

Opatchy is an Omarchy 4/schema v1 plugin with permanent ID
`io.github.tomge.opatchy`. Preserve its read-mostly boundary. Don't add an
installer, curl-to-shell instruction, package mutation, privilege escalation,
telemetry, arbitrary-command execution, or security assurance.

Keep user-facing wording honest about current, stale, unavailable, invalid, and
not-applicable evidence. New source or endpoint behavior needs a matching row in
`docs/data-sources.md`, a privacy review, and focused tests.

## Development loop

```sh
uv sync --group dev
make validate
```

For a quick public-contract check:

```sh
python3 -m unittest discover -s tests/contract -p 'test_*.py'
```

Don't edit generated screenshots or preview artifacts as part of ordinary
runtime changes. Include tests with behavior changes and update `CHANGELOG.md`
when a user-visible behavior changes.

## Pull requests

Explain the user impact, source and privacy effects, validation run, and any
Omarchy version assumptions. Keep commits narrow. Never include local XDG state,
cache files, tokens, package inventories, or `.omo` planning material.
