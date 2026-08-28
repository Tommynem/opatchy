# Opatchy

Opatchy is a read-mostly update and security-intelligence plugin for Omarchy.
Its permanent plugin ID is `io.github.tomge.opatchy`, and this release is
`0.1.0`. It is MIT licensed.

Opatchy collects update status, keeps local watch choices, shows current or
last-known evidence, and opens native update workflows through the host. It does
not perform privileged, partial, unattended, or package-specific updates. It
has no runtime telemetry.

## Install, enable, disable, remove

Opatchy targets Omarchy 4 with plugin manifest schema v1. Install it from a
reviewed Git remote, not a curl-to-shell command. This checkout has no published
Opatchy remote, so there is no supported `omarchy plugin add` command to run
today. The previously planned `https://github.com/tomge/opatchy` URL is not a
published repository. Do not replace the missing remote with a guessed URL.

When a reviewed Opatchy Git remote is published, install it with the URL shown
by that release:

```sh
omarchy plugin add <reviewed-git-url> --enable
omarchy plugin list
```

If you install without `--enable`, review the checkout first, then enable it:

```sh
omarchy plugin enable io.github.tomge.opatchy
```

Disable or remove it with Omarchy's plugin lifecycle commands:

```sh
omarchy plugin disable io.github.tomge.opatchy
omarchy plugin remove io.github.tomge.opatchy
```

Omarchy stores third-party plugins in `~/.config/omarchy/plugins/` and their
enabled state in `~/.config/omarchy/shell.json`. The official
[Shell Plugins manual](https://omarchy.org/manual/shell-plugins/) describes
the lifecycle, validation, and unsandboxed-code warning. Opatchy does not run
an install hook, ask for sudo, or install dependencies.

## Use

Click the bar widget to open its panel. The panel has Security, Omarchy,
System, AUR, Flatpak, and mise tabs. Refresh starts a scan through the shared
service. A source can be current, stale, unavailable, invalid, offline, timed
out, missing a dependency, or not applicable. A stale row is last-known data,
not a current result. An unknown result is not a clean result.

The helper accepts only these operations from the UI:

```text
scan [--force]
snapshot
inventory --source {arch|aur|flatpak|mise} --query TEXT --limit 1..100 --offset 0..100000
set-star --item-id ID --mode {off|temporary|permanent}
```

Stars are local watches. A temporary watch is armed for the next matching
update and clears when a later fresh scan observes a changed installed version
or a confirmed removal; it does not verify that a particular candidate update
completed. A permanent watch stays recorded until it is turned off. Notification
policy exists for eligible permanent watches and fresh, fixed high or critical
Arch findings, but this release does not wire notification dispatch into the production scan path. It does not inspect Do Not Disturb state or replay notifications.

The manifest exposes refresh interval, watch notifications, reduced motion,
security notifications, minimum security severity, CISA KEV inclusion, and last
selected tab. The current service schedules with a fixed 21600-second default;
not every declared setting is connected to helper collection or notification
delivery yet.

## Update handoffs

Opatchy never runs a generic command from update data. When current eligible
evidence exists, it may open one fixed native workflow in Omarchy's presentation
terminal: `omarchy-update`, `flatpak --user update`, or
`flatpak --system update`. Opening a terminal only starts that workflow. It does
not prove that an update completed. Opatchy intentionally does not recommend direct `pacman -Syu`.

## Dependencies and troubleshooting

At runtime Opatchy reads available host commands and only marks a source
current when its evidence validates. The supported collectors are documented in
[data sources](docs/data-sources.md). Missing `checkupdates`, `yay` or `paru`,
`flatpak`, `mise`, or `arch-audit` is shown as source-specific status rather
than prompting an installation. `yay` is preferred for AUR status and `paru`
is used only when `yay` is missing.

If the widget says unavailable, run `omarchy plugin list`, then disable and
enable the plugin after checking the manifest and shell logs. If a source is
stale or unknown, refresh it and inspect the source status before acting. See
[compatibility](docs/compatibility.md) for host limits and
[architecture](docs/architecture.md) for paths and retention behavior.

## Privacy and security boundary

Opatchy sends no installed inventory, watches, scan results, or notification
ledger as Opatchy telemetry. It does fetch the public Arch security and optional
CISA KEV feeds, and it runs the local commands listed in the data-source
contract. It is an unsandboxed plugin inside `omarchy-shell`, so read the source
and release changes before enabling it. See [privacy](docs/privacy.md) and the
[threat model](docs/threat-model.md).

## Development

Use the locked development environment and full validation gate:

```sh
uv sync --group dev
make validate
```

Run the smaller documentation contract suite with:

```sh
python3 -m unittest discover -s tests/contract -p 'test_*.py'
```

Contributions are welcome through [CONTRIBUTING.md](CONTRIBUTING.md). Report
suspected security issues using [SECURITY.md](SECURITY.md).

## Non-goals

Opatchy is not a package manager, installer, privilege boundary, security
assurance, local-exploitability verdict, AUR vulnerability scanner, or automatic
remediation tool. Screenshot and preview artifacts are maintained separately;
this README makes no claim that such artifacts are current.
