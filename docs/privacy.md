# Privacy

Opatchy has no runtime telemetry. It does not send installed package inventory,
watch choices, scan snapshots, notification ledger entries, or panel settings to
an Opatchy service.

## Data read locally

Opatchy reads local command output for Omarchy, native Arch packages, AUR
helpers, Flatpak, mise, and Arch security matching. It stores watches and
notification deduplication state in `$XDG_STATE_HOME/opatchy/state.json`, or
`~/.local/state/opatchy/state.json` when `XDG_STATE_HOME` is unset. It stores
validated snapshots, inventories, and feed caches under `$XDG_CACHE_HOME/opatchy/`,
or `~/.cache/opatchy/` when `XDG_CACHE_HOME` is unset.

Those files are local to the user account. Opatchy does not upload them. They
can contain package labels, versions, watch IDs, notification fingerprints, and
feed cache bytes. Remove the plugin through Omarchy, then remove those paths
yourself if you also want to discard its retained local data.

## Network requests

Opatchy fetches only the public Arch security feed and, when enabled, the CISA
Known Exploited Vulnerabilities feed. Requests reveal ordinary network metadata
to those services, such as the user's network address, request timing, and the
`Opatchy/1` User-Agent. See [data sources](data-sources.md) for exact endpoints.

## Notifications

The helper contains a local notification adapter, but the production scan path
does not currently dispatch it. Opatchy does not inspect Do Not Disturb state or
replay notifications. If notification dispatch is wired in a future release,
notification content and history will be subject to the desktop environment's
own behavior and settings.
