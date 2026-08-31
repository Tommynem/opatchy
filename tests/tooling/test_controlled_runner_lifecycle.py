import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPER_ROOT = REPOSITORY_ROOT / "helper"
SMOKE_FIXTURE = REPOSITORY_ROOT / "tests/qml/controlled-runner-smoke.qml"

HOST_OWNERSHIP_FIXTURE = """import QtQuick
import Quickshell

ShellRoot {
  id: root
  property var service: null
  property var services: ({})

  function serviceFor(pluginId) {
    return services[pluginId] || null
  }

  Item {
    id: serviceHost
    visible: false
  }

  function fail(message) {
    console.error("host-service-ownership: " + message)
    Qt.exit(1)
  }

  Component.onCompleted: {
    const sourceDir = Quickshell.env("OPATCHY_HOST_CONTRACT_ROOT")
    const manifest = {
      "id": "io.github.tommynem.opatchy",
      "kinds": ["service", "bar-widget"],
      "entryPoints": { "service": "Service.qml", "barWidget": "BarWidget.qml" },
      "__sourceDir": sourceDir
    }
    const component = Qt.createComponent("file://" + sourceDir + "/Service.qml", Component.PreferSynchronous)
    if (component.status !== Component.Ready) {
      fail("component load failed: " + component.errorString())
      return
    }

    service = component.createObject(serviceHost)
    if (service === null) {
      fail("component create failed: " + component.errorString())
      return
    }
    if (service.lastError !== "trusted helper path is unavailable") {
      fail("service must expose an unavailable trusted helper path before manifest injection")
      return
    }
    service.shell = root
    service.manifest = manifest
    services[manifest.id] = service
    verifyTimer.start()
  }

  Timer {
    id: verifyTimer
    interval: 0
    repeat: false
    onTriggered: {
      const registeredService = root.serviceFor("io.github.tommynem.opatchy")
      if (registeredService === null || registeredService._controller === null) {
        root.fail("enabled combined manifest did not initialize its service after host-order injection")
        return
      }
      const controller = registeredService._controller
      registeredService.initializeController()
      if (registeredService._controller !== controller) {
        root.fail("repeated initialization created a second controller")
        return
      }
      console.log("host-service-ownership: registered ready service")
      root.service.destroy()
      Qt.exit(0)
    }
  }
}
"""


def _write_controlled_target(path: Path, pid_log: Path, sentinel: Path) -> None:
    child_source = (
        "import os, pathlib, time; "
        f"open({str(pid_log)!r}, 'a', encoding='utf-8').write(f'{{os.getpid()}}\\n'); "
        f"time.sleep(0.5); pathlib.Path({str(sentinel)!r}).touch()"
    )
    _ = path.write_text(
        "\n".join(
            (
                f"#!{sys.executable}",
                "import os, subprocess, sys, time",
                f"open({str(pid_log)!r}, 'a', encoding='utf-8').write(f'{{os.getpid()}}\\n')",
                f"subprocess.Popen([sys.executable, '-c', {child_source!r}])",
                "time.sleep(30)",
                "",
            )
        ),
        encoding="utf-8",
    )
    path.chmod(0o700)


def _write_outer_helper(path: Path, target: Path) -> None:
    _ = path.write_text(
        "\n".join(
            (
                f"#!{sys.executable}",
                "from pathlib import Path",
                "import sys",
                f"sys.path.insert(0, {str(HELPER_ROOT)!r})",
                "from opatchy_helper.runner_process import run_spec",
                "from opatchy_helper.runner_types import ArgumentPolicy, CommandSpec",
                f"run_spec(CommandSpec(Path({str(target)!r}), (), ArgumentPolicy.NONE, 30, 1024, 1024), ())",
                "",
            )
        ),
        encoding="utf-8",
    )
    path.chmod(0o700)


def _wait_for_dead(pid: int) -> bool:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.01)
    return False


def test_host_order_initializes_service_for_combined_manifest(tmp_path: Path) -> None:
    # Given: the installed host's create-then-inject service ownership order.
    fixture = tmp_path / "host-service-ownership.qml"
    _ = fixture.write_text(HOST_OWNERSHIP_FIXTURE, encoding="utf-8")
    environment = os.environ | {
        "OPATCHY_HOST_CONTRACT_ROOT": str(REPOSITORY_ROOT),
    }

    # When: Quickshell creates Service.qml before assigning its combined manifest.
    result = subprocess.run(
        ["/usr/bin/qs", "--path", str(fixture)],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=30,
    )

    # Then: the host-owned service is registered and ready to own one controller.
    assert result.returncode == 0, result.stdout + result.stderr
    assert "host-service-ownership: registered ready service" in result.stdout


@pytest.mark.parametrize(
    ("mode", "interruptions"),
    (("stop", 1), ("timeout", 1), ("destroy", 1), ("destroy", 20)),
)
def test_quickshell_controlled_runner_cleans_every_known_group_member(
    tmp_path: Path, mode: str, interruptions: int
) -> None:
    # Given: the actual Quickshell transport and a helper using the controlled runner.
    pid_log = tmp_path / "pids"
    sentinel = tmp_path / "descendant-survived"
    target = tmp_path / "controlled-target"
    outer_helper = tmp_path / "controlled-helper"
    _write_controlled_target(target, pid_log, sentinel)
    _write_outer_helper(outer_helper, target)
    environment = os.environ | {
        "OPATCHY_CONTROLLED_HELPER": str(outer_helper),
        "OPATCHY_CONTROLLED_MODE": mode,
        "OPATCHY_INTERRUPTION_COUNT": str(interruptions),
        "OPATCHY_TEST_ROOT": str(REPOSITORY_ROOT),
    }

    # When: the real QML Process stops, times out, or directly destroys each helper.
    result = subprocess.run(
        ["/usr/bin/qs", "--path", str(SMOKE_FIXTURE)],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=30,
    )

    # Then: every recorded target and same-group child is gone without test cleanup.
    assert result.returncode == 0, result.stdout + result.stderr
    pids = (
        [int(value) for value in pid_log.read_text(encoding="utf-8").splitlines()]
        if pid_log.exists()
        else []
    )
    if mode == "timeout":
        assert 0 <= len(pids) <= interruptions * 2
    else:
        assert len(pids) == interruptions * 2
    assert all(_wait_for_dead(pid) for pid in pids)
    assert not sentinel.exists()
