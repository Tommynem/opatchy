# Todo 27 Real-Shell QA Packet

## Status

Stage A preparation only. This packet does not authorize a real-host action and
does not claim Omarchy compatibility. `tomarchy` and `gomarchy` are separate,
user-approved, scheduled windows.

## Before Requesting A Window

- Purpose: verify one local copy/enable/restore cycle, the right-side bar
  widget, one shared service/helper, and read-only panel behavior.
- Duration: 20 minutes per host, plus time to restore if a stop condition is
  reached.
- Privacy: keep the record directory outside this checkout. Do not commit host
  screenshots, inventory, usernames, paths, package lists, or hostnames.
- Stop and let the EXIT trap restore if shell ping fails, a retained plugin is
  missing, validation fails, a reload loops, more than one helper is observed,
  or any restoration comparison fails. The public shell health command is
  `omarchy shell shell ping`; the runner records helper counts before, during,
  and after restoration and fails if the final count differs from the initial one.
- Do not use SSH, `omarchy dev link`, symlinks, `omarchy update`, Flatpak
  update commands, an update-terminal button, `omarchy refresh`, or an update
  handoff. The runner has no handoff command and records this prohibition.

## User-Approved Command For Each Separate Window

Run this command locally on the named host only after the user supplies an
scheduled UTC window identifier and a private, empty record directory. The
approval value must be exactly `todo27:<host>:<window-id>`:

```sh
bash scripts/qa/todo27-real-shell-window.sh \
  --host tomarchy \
  --window-id '<YYYYMMDDTHHMMZ>' \
  --approval 'todo27:tomarchy:<YYYYMMDDTHHMMZ>' \
  --plugin-source "$PWD" \
  --record-dir '/absolute/private/path/opatchy-todo27-tomarchy' \
  --execute
```

For the separate `gomarchy` window, change `--host`, the host-bound approval
identifier, exact host-bound approval, and `--record-dir`. The selected host must
match the trusted system `/usr/bin/hostname` result with no arguments.
Do not run either command during Stage A. The runner refuses missing approval,
missing `--execute`, invalid source, failed shell ping, failed validator,
missing retained IDs, symlinks, or a nonempty record directory. It backs up
`shell.json` and the target plugin directory before mutation; its EXIT trap
restores both and compares semantic JSON/plugin digests before returning.

## Read-Only Checks During The Open Window

1. Confirm the runner reports `READY` and the bar shows exactly one Opatchy
   widget in the right section. Do not drag or reorder any other widget.
2. Open and close the Opatchy panel by pointer. Use visible focus, tab strip,
   native Enter/Space controls, and Escape to check keyboard/pointer reachability.
3. Trigger one manual source refresh and wait for completion. Inspect each tab
   only; do not activate any control labelled `Open update terminal`.
4. Observe the Opatchy helper while the read-only scan is active. Record the
   runner's `helper-count.during.txt`; it must never exceed one. Confirm the
   single service remains available to both bar and panel.
5. Record only a user-scrubbed real current-state capture if the user chooses.
   It must not be substituted for the fixture screenshots below.
6. Let the runner exit normally. Confirm `restoration.status` is zero,
   `omarchy shell shell ping` is `ok`, `helper-count.before.txt` equals
   `helper-count.after.txt` (zero for an absent/disabled target), the target
   plugin is absent or exactly restored, and retained plugin IDs/order/settings
   match the pre-window semantic snapshot.

When the checks are complete, return to the runner terminal and type `RESTORE`.
The runner monitors the helper count until that confirmation, then restores.

## Fixture-Only Preview Workflow

Run only from the isolated repository worktree. It never opens a shell plugin,
touches `~/.config`, or reads a real host:

```sh
bash scripts/qa/capture_todo27_fixture_preview.sh
```

This renders the existing offscreen QtQuick fixture harness and writes the
sanitized, clearly labelled `preview.png` plus four `docs/screenshots/` images.
They illustrate clear, update, security/stale, and transparent/stale states;
they are not compositor or real-host captures.
