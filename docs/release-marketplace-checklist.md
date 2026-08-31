# Release And Marketplace Checklist

## Local Release Readiness

1. Start from a clean committed tree and provide the prospective tag explicitly:
   `make release-dry-run`.
2. Confirm the generated `dist/release/opatchy-0.1.0.release.json` names the exact
   40-character commit and SHA256 for the deterministic tar archive.
3. Treat any missing command, Qt 6/QML capability, Omarchy validator failure,
   symlink, dirty tree, version disagreement, or failing local gate as a release
   blocker. The dry-run never tags, publishes, pushes, installs, or submits.

## Marketplace Submission Checklist

Before an owner submits Opatchy, confirm all required public root artifacts are
present: `README.md`, `LICENSE`, `CHANGELOG.md`, `SECURITY.md`, and
`manifest.json`. Confirm the dependency disclosure in [data sources](data-sources.md),
the manifest category and discovery tags, and obtain explicit owner approval for the
submission text and reviewed commit.

Do not open a marketplace issue as part of release preparation. Marketplace review,
owner approval, and any submission are separate future actions.

## Evidence Boundary

When its commands pass, the truthful pre-marketplace statement is: `Commit <SHA>
passed repository CI gates and omarchy plugin validate .` This is exact-commit
compatibility and static evidence only. It is not a security audit, warranty,
endorsement, safety guarantee, marketplace-verified state, or install-time SHA pin.
The marketplace's static baseline does not provide general data-flow analysis.
