# Compatibility

## Target

Opatchy targets Omarchy 4 with plugin manifest schema v1 and the permanent
plugin ID `io.github.tomge.opatchy`. The intended initial version is `0.1.0`.
The local planning input is Omarchy `4.0.0.alpha`; exact release support will
be verified against the Omarchy version available at release time.

## Current limitation

This repository-contract stage contains no `manifest.json` or runtime, so it
makes no installation compatibility claim. Later work must validate the
manifest with `omarchy plugin validate .` and retain the contract test below.

```sh
python3 -m unittest discover -s tests/contract -p 'test_*.py'
```

## Runtime boundary

The planned runtime uses Python 3 standard library components only and has no
runtime telemetry. Opatchy will open native update workflows rather than
perform privileged, partial, unattended, or package-specific updates.
