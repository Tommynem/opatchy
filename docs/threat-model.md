# Threat model

## Scope

Opatchy runs as unsandboxed code inside the user's long-lived `omarchy-shell`
process. It can read the same user-visible local command output that its
collectors request, persist local state, make the documented HTTPS requests,
and ask Omarchy to open fixed update workflows. This document states boundaries,
not assurance or exploitability conclusions.

## Boundaries

| Concern | Boundary and residual risk |
| --- | --- |
| Plugin trust | The plugin is arbitrary code in the user session. Read the repository and revisions before enabling it. |
| Local commands | The runner uses an allowlisted executable and argument registry, bounded output, time limits, and no shell-composed external input. A compromised local executable or user session remains outside Opatchy's control. |
| Remote feeds | Requests are limited to allowlisted HTTPS hosts and paths with bounded redirects and bodies. Feed content can be unavailable, delayed, wrong, or incomplete despite transport checks. |
| Stored data | State and cache records are locked, validated, and atomically replaced. Anyone able to alter the user's files or process can still affect their environment. |
| Presentation | Stale, unavailable, invalid, and not-applicable evidence is labeled rather than treated as clean. Displayed data can still be incomplete or become outdated. |
| Update actions | The UI launches only fixed native Omarchy or Flatpak update argv after eligibility checks. A handoff does not confirm package mutation or update success. |
| Notifications | The helper's notification content is bounded and escaped for `notify-send`, but production dispatch is not wired in this release. Desktop notification privacy is controlled by the host session if dispatch is added. |

## Explicit non-goals

Opatchy does not make a machine-safe, machine-secure, fully-protected, or
not-exploitable claim. It does not provide an exploitability verdict, automatic
remediation, package installation, privilege escalation, telemetry, or an AUR
vulnerability conclusion. Security findings are source-derived matching data,
not a complete inventory of risk.

## Reporting

Report suspected issues under [SECURITY.md](../SECURITY.md). Avoid including
private inventories, tokens, or personal state files in a public report.
