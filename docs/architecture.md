# Architecture

## Components and trust boundary

`omarchy-shell` loads Opatchy as one unsandboxed third-party plugin with a
singleton `service` entry point and a `bar-widget` entry point. `Service.qml`
owns scheduling, the single helper-operation queue, accepted snapshots, and
handoff coordination. `BarWidget.qml` and `Panel.qml` consume that service and
do not create collectors. The panel is presentation only.

`helper/opatchy.py` is the Python boundary. It writes a versioned JSON response
to standard output and exits `0` for a response or `2` for an error response.
The UI can request only scan, snapshot, inventory, and set-star operations.
Inputs are parsed before collection and a malformed response is rejected by the
QML protocol validator.

## Runtime contract

| Area | Canonical behavior | Source of truth |
| --- | --- | --- |
| Scheduler | The service serializes helper work, loads a cached snapshot, scans after 30 seconds, then every six hours with jitter, with freshness retry and post-handoff scheduling. | `Service.qml`, `qml/models/ServiceController.js` |
| Local collection | Fixed executable paths and fixed argv collect local status. No shell-composed input is accepted. | `helper/opatchy_helper/runner_registry.py` |
| Remote collection | Only two allowlisted HTTPS endpoints are fetched, with redirect host and path validation. | `helper/opatchy_helper/runner_registry.py` |
| State | Watches and notification ledger are validated, locked, and atomically written. | `helper/opatchy_helper/storage.py` |
| Cache | Snapshots, inventories, endpoint transport bytes, validators, and last-good feed bytes are separate cache records. | `helper/opatchy_helper/storage.py` |
| Presentation | Current, stale, unavailable, invalid, and not-applicable evidence stay distinct. | `qml/models/ProtocolValidator.js`, panel models |
| Handoff | Only fixed Omarchy or Flatpak update argv can be launched after current-evidence eligibility checks. | `qml/models/ActionPolicy.js` |

## XDG paths and retention

Opatchy uses `XDG_STATE_HOME` or `~/.local/state` as a fallback. Its validated
state file is `$XDG_STATE_HOME/opatchy/state.json`. It uses `XDG_CACHE_HOME` or
`~/.cache` as a fallback, with cache content under `$XDG_CACHE_HOME/opatchy/`.
Relative XDG values are rejected. State writes use a lock and atomic replacement.
Invalid or incompatible retained state is unavailable rather than trusted.
The storage writer sets its directories to `0700` and its files, including
`state.json` and `state.lock`, to `0600`. The remote transport-cache writer
uses the process umask while creating its cache path before the storage writer
subsequently normalizes that directory; do not treat cache-path permissions as
a secrecy guarantee beyond the current user account.

The state contains watches and the notification ledger. The cache contains the
latest validated snapshot, source inventories, a generation record, remote
transport validators and bodies, and parser-validated last-good security feed
bytes. Transport and semantic feed records are deliberately separate. Retained
data can be presented as last-known evidence but is not promoted to current
evidence merely because it exists.

Watches have no time-based expiry. Inactive notification-ledger entries are
retained for at most 180 days and the newest 5,000 entries; active entries are
not age-pruned. Snapshots, inventories, and feed caches have no time-based
retention limit. Invalid retained records are discarded or quarantined rather
than used.

There is no cloud account, analytics queue, or Opatchy telemetry retention path.

## Failure semantics

Collection is source-scoped. Missing commands, malformed output, command time
limits, offline endpoints, invalid responses, and inapplicable sources are
reported as distinct source health. A successful cache read is not a scan.
Cached and fallback provenance can be current only where the specific policy
allows it. Last-good provenance is retained evidence, not fresh evidence.

The UI can request browse inventory for Arch, AUR, Flatpak, and mise. Omarchy
does not expose a helper inventory endpoint. Query text is limited to 128
characters, pages are limited to 100 rows, and offset is limited to 100000.

## Notification and settings limitation

The helper dispatches notification policy only after `commit_generation` accepts
a validated generation. The shared ledger claims and completes each dispatch,
so delivery deduplicates across restart and command-missing, nonzero, timed-out,
or output-limited notification commands remain retryable without rolling back
scan, cache, or watch state. Each scan request carries typed permanent-watch,
security, and minimum-severity notification settings to the coordinator. A conditional
temporary security watch retains only canonical `arch:PACKAGE`, advisory/CVE,
and fixed-version evidence. It is eligible only when fresh live Arch and
Security evidence matches that condition, its Arch candidate is live, and native
`/usr/bin/vercmp` confirms the installable candidate is at least the fixed
version. The matching condition owns that finding's alert, while unrelated
findings retain their generic security alerts. Notification delivery does not
clear a watch; the normal fresh installed-fingerprint/removal state machine does.
Opatchy does not inspect Do Not Disturb state or replay a notification history.

## Operating limits

Each registered local command has a fixed timeout and bounded standard-output
and standard-error capture. Remote endpoint requests have fixed redirect limits,
body limits, and timeouts. The implementation is intentionally closed over its
command and endpoint registries, so documentation should not imply support for
arbitrary commands, feeds, or package managers.
