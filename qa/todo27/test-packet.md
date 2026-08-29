# Todo 27 Real-Shell QA Packet

## Status

Stage A preparation only. This packet does not authorize a real-host action and
does not claim Omarchy compatibility. An explicit request to launch on
`tomarchy` authorizes one immediate launch on `tomarchy` only. `gomarchy`
remains out of scope unless the user later makes a separate explicit named-host
request.

## Immediate Local Command

After the user explicitly requests a `tomarchy` launch, run this local command
with a private, empty absolute record path. No additional approval metadata is
requested. The approval is exactly `todo27:tomarchy`.

```sh
bash scripts/qa/todo27-real-shell-window.sh \
  --host tomarchy \
  --approval 'todo27:tomarchy' \
  --plugin-source "$PWD" \
  --record-dir '/absolute/private/path/opatchy-todo27-tomarchy' \
  --execute
```

The selected host must exactly match trusted `/usr/bin/hostname` output invoked
with no arguments. The runner refuses a missing, malformed, or other-host
approval; missing `--execute`; invalid source; failed ping or validation;
missing retained IDs; symlinks; and a nonempty record path. It stages and
validates outside the watched plugin directory, records semantic JSON and byte
digests, plugin-tree digests, retained IDs, helper counts, ping, and no-handoff
evidence, then restores through its EXIT trap.

## User-Owned Read-Only Inspection

1. Confirm `READY` and one Opatchy widget in the right section without moving
   any other widget.
2. Open and close the panel with pointer, visible focus, the tab strip,
   Enter/Space, and Escape.
3. Trigger one manual source refresh, inspect the tabs, and do not activate any
   update-terminal or other update action.
4. Optionally keep only a user-scrubbed current-state capture; it does not
   replace fixture previews.
5. Return to the runner and type `RESTORE`. Confirm `restoration.status` is
   zero, `omarchy shell shell ping` is `ok`, before/after helper counts match,
   and the target plus retained plugin IDs/order/settings are restored.

Stop and allow restoration if ping fails, a retained plugin disappears,
validation fails, a reload loops, more than one helper appears, or a restoration
comparison fails. Do not use SSH, `omarchy dev link`, symlinks, `omarchy update`,
Flatpak update commands, `omarchy refresh`, or any update handoff.

## Fixture-Only Preview Workflow

Run only from the isolated repository worktree. It never opens a shell plugin,
touches `~/.config`, or reads a real host:

```sh
bash scripts/qa/capture_todo27_fixture_preview.sh
```

This renders the existing offscreen QtQuick fixture harness and writes the
sanitized, clearly labelled `preview.png` plus four `docs/screenshots/` images.
They illustrate clear, dense update, conditional-security, and stale/degraded
states;
they are not compositor or real-host captures.
