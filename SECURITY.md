# Security policy

## Scope

Opatchy is an unsandboxed plugin loaded by `omarchy-shell`. Its source includes
local command collection, public-feed requests, local state, and fixed update
handoffs. It is not a privilege boundary and does not perform package mutation.

## Report a suspected issue

Use GitHub's private security-advisory reporting for this repository when it is
available. If that path is unavailable, contact the maintainer through the
repository profile at https://github.com/tomge/opatchy and request a private
channel before sending details.

Include the affected revision, Omarchy version, clear reproduction steps,
observed impact, and minimal relevant logs. Don't publish a proof of concept,
token, private package inventory, or local state file before coordinating with
the maintainer.

## What to expect

Reports are reviewed on a best-effort basis. Acknowledgement, fix timing, CVE
assignment, and disclosure coordination depend on the report and maintainer
availability. No response promise is implied by this document.

## Limits

Security-feed matching, stale markers, and native update handoffs do not prove
that a machine is safe or that a vulnerability is exploitable. Review the
[threat model](docs/threat-model.md) before relying on Opatchy output.
