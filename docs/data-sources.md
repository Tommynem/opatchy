# Data sources

This table is the public inventory of runtime process and network capability.
Each row maps to one closed registry entry or endpoint. Opatchy does not accept
user-supplied commands or source URLs.

| Source | Process or endpoint | Purpose | When unavailable |
| --- | --- | --- | --- |
| Omarchy | `/usr/bin/omarchy-update-available` | Omarchy update availability | Source status explains failure or absence. |
| System | `/usr/bin/pacman -Qn`, `/usr/bin/checkupdates --nocolor`, `/usr/bin/vercmp` | Native installed inventory and update comparison | No direct package update is performed. |
| AUR | `/usr/bin/pacman -Qm`, `/usr/bin/yay -Qua --color never`, fallback `/usr/bin/paru -Qua --color never` | Foreign-package inventory and AUR updates | Missing helper is source-specific. |
| Flatpak | `/usr/bin/flatpak` fixed user and system list and update queries | User and system application and runtime updates | User and system scopes remain distinct. |
| mise | `/usr/bin/mise outdated --json` | Managed tool update status | Empty or unavailable evidence is not an update claim. |
| Arch security | `/usr/bin/arch-audit --json` and `https://security.archlinux.org/all.json` | Local package matching and Arch advisory enrichment | Findings can be stale, unknown, or unavailable. |
| CISA KEV | `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json` | Optional priority enrichment for matching CVEs | Disabled or unavailable coverage is visible separately. |
| Notifications | `/usr/bin/notify-send -a Opatchy -u normal` | Local desktop notification delivery | Delivery failure is retained as local notification state. |
| Update handoff | `/usr/bin/omarchy-launch-floating-terminal-with-presentation` plus fixed Omarchy or Flatpak argv | Open host-managed update workflow | A launch attempt is not an update result. |

The remote endpoints are HTTPS-only, with allowlisted host and path checks,
redirect limits, body limits, and timeouts. Parser-valid last-good feed bytes
may be retained locally, but retention does not turn old evidence into fresh
evidence. Opatchy does not fetch AUR package metadata from an external service.
