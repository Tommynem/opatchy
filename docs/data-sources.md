# Data sources

This table is the canonical inventory of runtime processes and network
capability. Every closed helper registry entry has one identifier row; UI
processes and user-triggered external links have their own rows. Opatchy does
not accept user-supplied commands or source URLs.

| Kind | Canonical identifier | Process or endpoint | Purpose and limit |
| --- | --- | --- | --- |
| Local command | `omarchy-update-available` | `/usr/bin/omarchy-update-available` | Read Omarchy update availability. |
| Local command | `pacman-native` | `/usr/bin/pacman -Qn` | Read the native installed-package inventory. |
| Local command | `checkupdates` | `/usr/bin/checkupdates --nocolor` | Read native available updates. |
| Local command | `vercmp` | `/usr/bin/vercmp <installed> <candidate>` | Compare two validated opaque Arch version strings. |
| Local command | `pacman-foreign` | `/usr/bin/pacman -Qm` | Read the foreign-package inventory for AUR matching. |
| Local command | `yay-updates` | `/usr/bin/yay -Qua --color never` | Read AUR update status when `yay` is available. |
| Local command | `paru-updates` | `/usr/bin/paru -Qua --color never` | Read AUR update status only when `yay` is missing. |
| Local command | `flatpak-user-app-list` | `/usr/bin/flatpak --user list --app --columns=application,arch,branch,version,origin` | Read user-scope Flatpak applications. |
| Local command | `flatpak-user-runtime-list` | `/usr/bin/flatpak --user list --runtime --columns=application,arch,branch,version,origin` | Read user-scope Flatpak runtimes. |
| Local command | `flatpak-system-app-list` | `/usr/bin/flatpak --system list --app --columns=application,arch,branch,version,origin` | Read system-scope Flatpak applications. |
| Local command | `flatpak-system-runtime-list` | `/usr/bin/flatpak --system list --runtime --columns=application,arch,branch,version,origin` | Read system-scope Flatpak runtimes. |
| Local command | `flatpak-user-updates` | `/usr/bin/flatpak --user remote-ls --updates --columns=ref,version,origin` | Read user-scope Flatpak updates. |
| Local command | `flatpak-system-updates` | `/usr/bin/flatpak --system remote-ls --updates --columns=ref,version,origin` | Read system-scope Flatpak updates. |
| Local command | `mise-outdated` | `/usr/bin/mise outdated --json` in the user's home directory | Read global/home-managed tool updates, never project data. |
| Local command | `arch-audit` | `/usr/bin/arch-audit --json` | Read local Arch advisory matches. |
| Local command | `notify` | `/usr/bin/notify-send -a Opatchy -u normal <title> <body>` | Adapter only: it is not dispatched by the production scan path, so no delivery or retained delivery result is promised. |
| Remote endpoint | `arch-security` | `https://security.archlinux.org/all.json` | Fetch Arch advisory enrichment over HTTPS. |
| Remote endpoint | `cisa-kev` | `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json` | Fetch CISA KEV enrichment over HTTPS; the declared setting does not currently disable collection. |
| UI helper | `helper-process` | `/usr/bin/python3 helper/opatchy.py` plus the validated UI operations in the README | Produce versioned helper responses; no arbitrary helper argv is accepted. |
| Handoff probe | `terminal-probe` | `/usr/bin/test -x` for the fixed handoff executables listed below | Check fixed handoff prerequisites only. |
| Update handoff | `omarchy-handoff` | `/usr/bin/omarchy-launch-floating-terminal-with-presentation /usr/bin/omarchy-update` | Open the fixed native Omarchy workflow only for current eligible evidence. |
| Update handoff | `flatpak-user-handoff` | `/usr/bin/omarchy-launch-floating-terminal-with-presentation /usr/bin/flatpak --user update` | Open the fixed user Flatpak workflow only for current eligible evidence. |
| Update handoff | `flatpak-system-handoff` | `/usr/bin/omarchy-launch-floating-terminal-with-presentation /usr/bin/flatpak --system update` | Open the fixed system Flatpak workflow only for current eligible evidence. |
| External link | `arch-advisory-link` | `https://security.archlinux.org/AVG-...` | Open only a canonical Arch advisory selected from displayed evidence. |
| External link | `cve-link` | `https://www.cve.org/CVERecord?id=CVE-...` | Open only a canonical displayed CVE record. |

The remote endpoints are HTTPS-only, with allowlisted host and path checks,
redirect limits, body limits, and timeouts. Parser-valid last-good feed bytes
may be retained locally, but retention does not turn old evidence into fresh
evidence. Opatchy does not fetch AUR package metadata from an external service.
