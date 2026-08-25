# Contributing to Opatchy

## Before contributing

Opatchy is planned for Omarchy 4/schema v1 under the permanent ID
`io.github.tomge.opatchy`. Keep changes compatible with the MIT license, the
public product boundary, and the dependency-free runtime requirement.

Do not add installers, package mutation, privilege escalation, telemetry,
curl-to-shell instructions, or security assurances that exceed available
evidence. Runtime work must keep native update workflows separate from package
management.

## Checks

Run the current repository contract before sending a change:

```sh
python3 -m unittest discover -s tests/contract -p 'test_*.py'
```

Later tasks will provide the full development checks:

```sh
uv sync --group dev
make validate
```

Keep public documentation concise, record behavior changes in
`CHANGELOG.md`, and include focused tests with implementation changes.
