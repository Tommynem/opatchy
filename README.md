# Opatchy

Opatchy is a planned read-mostly update and security-intelligence plugin for
Omarchy. Its permanent plugin ID is `io.github.tomge.opatchy`; the initial
version is `0.1.0`; and its intended public repository is
https://github.com/tomge/opatchy. Opatchy is licensed under MIT.

## Product boundary

Opatchy targets Omarchy 4 and manifest schema v1. It opens native update
workflows and does not perform privileged, partial, unattended, or
package-specific updates. Opatchy has no runtime telemetry and will not
install dependencies or mutate packages.

Opatchy is an unsandboxed Omarchy plugin. Review its source and release
changes before enabling it. Future security views will distinguish current,
stale, and unavailable evidence rather than make claims about a machine's
protection or exploitability.

## Repository status

This initial repository contract intentionally contains no manifest, runtime
helper, QML implementation, installer, or release. Those pieces arrive in
later development tasks and must preserve the boundaries above.

## Local checks

The current dependency-free contract check is:

```sh
python3 -m unittest discover -s tests/contract -p 'test_*.py'
```

Later tasks will add the development environment and aggregate validation
entry point. The planned commands are:

```sh
uv sync --group dev
make validate
```

See [architecture](docs/architecture.md), [threat model](docs/threat-model.md),
and [compatibility](docs/compatibility.md) for the contract that later work
must retain.
