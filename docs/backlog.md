# Opatchy Roadmap

This committed roadmap is the sole source for deferred-feature GitHub issues.
Each entry preserves Opatchy's read-mostly boundary: no unattended, partial,
privileged, package-specific, or automatic update action is in scope.

<!-- opatchy-roadmap: fwupd-firmware-inventory -->
## fwupd firmware inventory and handoff

## Value
Expose available firmware context without hiding firmware risk behind package updates.

## Scope
Read fwupd inventory and surface a user-triggered native firmware workflow handoff.

## Safety constraints
No flashing, privilege escalation, unattended firmware action, or completion claim.

## Dependencies
fwupd, an approved host presentation workflow, and documented firmware capability states.

## Acceptance criteria
Validated inventory names source health; absent capability is explicit; handoff argv is fixed.

## Non-goals
Firmware mutation, rollback, scheduling, automatic remediation, or device-health guarantees.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: podman-container-digests -->
## Podman container digest inventory

## Value
Show local container image digest drift with clear provenance.

## Scope
Read-only Podman image and container inventory with digest comparison presentation.

## Safety constraints
No pull, prune, restart, deploy, registry credential access, or container mutation.

## Dependencies
Podman JSON contracts, bounded command output, and an exact digest identity model.

## Acceptance criteria
Malformed or unavailable Podman evidence degrades independently and retains no secrets.

## Non-goals
Image updates, vulnerability claims, orchestration, deployment, or automatic cleanup.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: lockfile-sbom-osv-adapters -->
## Exact lockfile SBOM and OSV adapters

## Value
Enable dependency evidence only where a lockfile establishes exact package identity.

## Scope
Parse supported exact lockfiles into bounded SBOM identities and query compatible OSV records.

## Safety constraints
No guessed CPE or PURL mapping, dependency mutation, source upload, or security assurance.

## Dependencies
Per-ecosystem lockfile schemas, exact PURL construction, and privacy-reviewed OSV transport.

## Acceptance criteria
Only validated locked identities query OSV; unknown or stale results remain explicit.

## Non-goals
Generic filesystem scanning, AUR vulnerability claims, automatic upgrades, or remediation.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: arch-news-release-note-gates -->
## Arch News and Omarchy release-note gates

## Value
Present relevant upstream notices before a user chooses an update workflow.

## Scope
Fetch and validate official Arch News and Omarchy release-note evidence for visible gates.

## Safety constraints
No automatic blocking override, update launch, package mutation, or trust claim from prose.

## Dependencies
Official source contracts, bounded parsing, and deterministic relevance rules.

## Acceptance criteria
Current, stale, malformed, and unavailable notices are distinguishable and link safely.

## Non-goals
Automated decisions, unattended updates, scraping arbitrary feeds, or release verification.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: maintenance-windows-reminders -->
## Maintenance windows and reminders

## Value
Help users remember a deliberately chosen maintenance time without executing updates.

## Scope
Local reminder preferences and visible scheduled-window context.

## Safety constraints
No update scheduling, unattended action, wake-up, privilege escalation, or DND bypass.

## Dependencies
Typed local preference storage and host notification behavior that respects user controls.

## Acceptance criteria
Reminders are opt-in, locally stored, dismissible, and never imply update completion.

## Non-goals
Automatic maintenance, calendar synchronization, package mutation, or background tasks.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: post-update-analysis -->
## Post-update reboot and pacnew analysis

## Value
Explain observable post-update follow-up signals after a user-controlled update.

## Scope
Read-only reboot, pacnew, and selected post-update log evidence with provenance.

## Safety constraints
No reboot, configuration merge, log upload, rollback, or inference that an update succeeded.

## Dependencies
Documented local evidence sources, privacy review, and bounded parser contracts.

## Acceptance criteria
Signals distinguish missing, stale, and current evidence and expose no private log bodies.

## Non-goals
Automatic reboot, pacnew resolution, remediation, or terminal-completion inference.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: deterministic-impact-labels -->
## Deterministic impact labels

## Value
Give update rows stable, explainable impact categories instead of vague urgency.

## Scope
Pure deterministic labels derived from validated source metadata and documented rules.

## Safety constraints
No security assurance, opaque scoring, package mutation, or source-data guessing.

## Dependencies
Stable source metadata contracts and exhaustive model tests.

## Acceptance criteria
Every label has a documented deterministic rule and unknown evidence remains unknown.

## Non-goals
Machine safety scores, exploitability verdicts, automatic prioritization, or remediation.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: aur-local-trust-context -->
## AUR and local-package trust context

## Value
Clarify local package origin and trust boundaries without asserting package safety.

## Scope
Read-only context for foreign and local package provenance already visible to the system.

## Safety constraints
No AUR vulnerability claim, package installation, build execution, or remote credential access.

## Dependencies
Pacman foreign-package inventory, bounded metadata sources, and privacy documentation.

## Acceptance criteria
Context explicitly separates unavailable metadata from a safety conclusion.

## Non-goals
AUR scanning, automatic trust decisions, package mutation, or security certification.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: scan-history -->
## Change since last scan history

## Value
Show which validated update evidence changed between local scans.

## Scope
Bounded local history of normalized scan deltas and timestamps.

## Safety constraints
No inventory upload, unbounded retention, update inference, or hidden telemetry.

## Dependencies
Versioned local storage, retention policy, and deterministic delta identities.

## Acceptance criteria
History is bounded, restart-safe, source-qualified, and distinguishes stale from current scans.

## Non-goals
Cloud history, audit compliance claims, automatic notifications, or package mutation.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: battery-metered-scheduling -->
## Battery and metered scheduler awareness

## Value
Avoid unnecessary read-only scan work when a user indicates constrained power or network use.

## Scope
Optional host capability awareness that influences scheduling of collection only.

## Safety constraints
No network bypass, background update, hidden host control, or inference from unavailable signals.

## Dependencies
Documented host power and metered-network APIs plus explicit fallback behavior.

## Acceptance criteria
Unavailable capability remains visible; manual refresh semantics stay user-controlled.

## Non-goals
Automatic updates, policy enforcement, power management, or network reconfiguration.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: sanitized-support-bundle -->
## Sanitized support bundle

## Value
Let a user review a bounded diagnostic bundle before sharing support evidence.

## Scope
Locally generated, user-triggered sanitized state and capability summary.

## Safety constraints
No automatic upload, credentials, home paths, raw inventory, logs, or remote support channel.

## Dependencies
Explicit redaction policy, local preview, and reproducible fixture tests.

## Acceptance criteria
Every included field is allowlisted, redaction is tested, and the user chooses any sharing.

## Non-goals
Telemetry, crash reporting, background collection, automatic support tickets, or uploads.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: project-local-mise-discovery -->
## Project-local mise discovery

## Value
Expose project-specific mise update context only when a user deliberately selects a project.

## Scope
Bounded explicit project discovery using documented mise data contracts.

## Safety constraints
No recursive home traversal, arbitrary project execution, mutation, or automatic tool update.

## Dependencies
User-selected roots, mise JSON schema, and path containment validation.

## Acceptance criteria
Discovery stays inside the selected root and unavailable/malformed projects degrade safely.

## Non-goals
Background indexing, shell activation, tool installation, or project-wide mutation.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: named-flatpak-installations -->
## Named Flatpak installations

## Value
Show update evidence for explicitly selected non-default Flatpak installations.

## Scope
Read-only inventory and fixed handoff planning for named installations.

## Safety constraints
No implicit installation discovery, mutation, partial update, or automatic action.

## Dependencies
Flatpak installation APIs, exact scope identities, and user-approved installation selection.

## Acceptance criteria
Each installation is visibly named, independently healthy, and never conflated with defaults.

## Non-goals
Bulk update, installation creation, automatic remediation, or cross-installation inference.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: assistive-technology-research -->
## Assistive-technology and screen-reader conformance research

## Value
Establish evidence needed for credible accessibility and screen-reader support claims.

## Scope
Research, test-harness design, and documented conformance criteria for assistive technology.

## Safety constraints
No unsupported conformance claim, user-environment probing, telemetry, or desktop control.

## Dependencies
Host accessibility APIs, assistive-technology test environments, and user-reviewed criteria.

## Acceptance criteria
Published criteria name executable checks and leave unsupported behavior explicitly unclaimed.

## Non-goals
Certification claim, automatic desktop testing, accessibility data collection, or UI mutation by default.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->

<!-- opatchy-roadmap: verified-sha-installation-trust -->
## Installation to verified SHA trust improvement

## Value
Help users connect a reviewed installation checkout to a specific public commit.

## Scope
Documented and tool-supported local comparison of installation provenance to a verified SHA.

## Safety constraints
No marketplace verification claim, auto-install, remote code execution, or trust guarantee.

## Dependencies
Immutable Git commit identity, documented repository provenance, and local read-only verification.

## Acceptance criteria
The result distinguishes match, mismatch, and unavailable evidence without claiming security.

## Non-goals
Release creation, tag automation, marketplace submission, installer, or automatic repair.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->
