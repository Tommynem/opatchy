import os
from pathlib import Path

from tests.e2e.offline_scenario_runner import resolve_node_path


def test_resolve_node_path_ignores_executable_inside_temporary_checkout(
    tmp_path: Path,
) -> None:
    # Given: a fixture-local fake node before a host-provided executable.
    repository_root = tmp_path / "checkout"
    fake_bin = repository_root / "fake-bin"
    host_bin = tmp_path / "host-bin"
    fake_bin.mkdir(parents=True)
    host_bin.mkdir()
    fake_node = fake_bin / "node"
    host_node = host_bin / "node"
    _ = fake_node.write_text("#!/usr/bin/env bash\nexit 7\n", encoding="utf-8")
    _ = host_node.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_node.chmod(0o755)
    host_node.chmod(0o755)

    # When: the presentation runner resolves Node from the inherited PATH.
    resolved = resolve_node_path(repository_root, f"{fake_bin}{os.pathsep}{host_bin}")

    # Then: only the host executable is eligible.
    assert resolved == str(host_node)
