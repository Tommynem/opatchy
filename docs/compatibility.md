# Compatibility

Opatchy targets Omarchy 4 and plugin manifest schema v1. Its permanent plugin
ID is `io.github.tomge.opatchy` and its version is `0.1.0`. The manifest declares
a combined `service` and `bar-widget` plugin, with the widget placed in the
right section by default and only one instance allowed.

This is a compatibility target, not a promise that it works in every
environment. The host must provide Omarchy's plugin CLI and shell runtime. The
plugin is loaded by the long-lived `omarchy-shell` process and therefore
requires a compatible Quickshell environment supplied by Omarchy.

The plugin uses host-provided `/usr/bin` programs when their source is enabled:
`omarchy-update-available`, `pacman`, `checkupdates`, `vercmp`, `yay`, `paru`,
`flatpak`, `mise`, `arch-audit`, and `notify-send`. A missing optional collector
is a visible source condition. Opatchy does not install a missing dependency.

Validate a checkout with the host before enabling it:

```sh
omarchy plugin validate .
```

The official [Shell Plugins manual](https://omarchy.org/manual/shell-plugins/)
describes current host lifecycle semantics. Omarchy manages system updates
through its own workflow; Opatchy opens that workflow and does not replace it.
