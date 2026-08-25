# Architecture

## Status

This document defines the initial Opatchy contract. The repository currently
contains no `manifest.json`, QML, helper runtime, or installer.

## Intended shape

Opatchy targets Omarchy 4/schema v1 as one plugin with a service and bar
widget. `Service.qml` will be the sole scheduler, helper-operation queue,
snapshot owner, and notification coordinator. `BarWidget.qml` will own the
panel presentation, and panel instances will consume the shared service rather
than launch collectors themselves.

A Python 3 standard-library helper will own read-mostly collection, durable
state, and a versioned JSON protocol. It will have no runtime telemetry. The
future UI will keep six discoverable surfaces: Security, Omarchy, System, AUR,
Flatpak, and mise; unavailable sources will explain their status instead of
silently disappearing.

## Update boundary

Opatchy opens native update workflows. It does not itself perform privileged,
partial, unattended, or package-specific updates. Collection, policy, state,
and presentation must remain separate so the shell-facing UI does not become a
generic command executor.
