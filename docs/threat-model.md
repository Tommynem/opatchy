# Threat model

## Context

Opatchy is planned as unsandboxed code inside `omarchy-shell`. A future helper
will consume local command output and selected remote advisory feeds, retain
watch and notification state, and hand users to native update workflows.

## Threats and boundaries

| Concern | Required boundary |
| --- | --- |
| Local command injection | Future subprocess calls use fixed allowlisted argv tokens; no shell-composed external data. |
| Remote advisory content | Future fetches use allowlisted HTTPS endpoints, bounded responses, and plain-text presentation. |
| Misleading update state | Current, stale, missing, and invalid evidence remain distinct; opening a terminal does not prove an update occurred. |
| Package mutation | Opatchy does not itself perform privileged, partial, unattended, or package-specific updates. |
| Privacy | No installed inventory, watch state, or scan result is sent as Opatchy telemetry. |

## Non-goals

Opatchy does not claim a machine is safe, secure, or not exploitable. It does
not provide a local-exploitability verdict, AUR vulnerability inference,
automatic remediation, dependency installation, or telemetry.

## Residual risk

Users remain responsible for reviewing plugin source, release changes, native
update workflows, and the source-specific data they rely on. Later tasks must
test hostile local and remote strings, stale evidence, and malformed protocol
data before adding runtime behavior.
