import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Final
import unittest


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
MANIFEST_PATH: Final = REPOSITORY_ROOT / "manifest.json"
PLUGIN_ID: Final = "io.github.tomge.opatchy"
REQUIRED_PRODUCT_FILES: Final = (
    "manifest.json",
    "Service.qml",
    "LifecycleState.qml",
    "BarWidget.qml",
    "Panel.qml",
)


class PluginLifecycleContractTests(unittest.TestCase):
    def require_product_files(self) -> None:
        missing_files = [
            name
            for name in REQUIRED_PRODUCT_FILES
            if not (REPOSITORY_ROOT / name).is_file()
        ]
        self.assertEqual(missing_files, [])

    def test_product_lifecycle_files_exist_when_checkout_is_loaded(self) -> None:
        self.require_product_files()

    def test_manifest_uses_the_supported_combined_lifecycle_shape(self) -> None:
        self.require_product_files()
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        self.assertIs(type(manifest["schemaVersion"]), int)
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["id"], PLUGIN_ID)
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertEqual(manifest["kinds"], ["service", "bar-widget"])
        self.assertEqual(
            manifest["entryPoints"],
            {"service": "Service.qml", "barWidget": "BarWidget.qml"},
        )

        widget = manifest["barWidget"]
        self.assertEqual(widget["defaultSection"], "right")
        self.assertIs(widget["allowMultiple"], False)
        self.assertEqual(
            widget["defaults"],
            {
                "refreshIntervalSec": 21600,
                "notifyPermanent": True,
                "notifySecurity": True,
                "securityMinimumSeverity": "high",
                "enableCisaKev": True,
                "lastSelectedTab": "Security",
            },
        )
        schema = {entry["key"]: entry for entry in widget["schema"]}
        self.assertEqual(
            set(schema),
            {
                "refreshIntervalSec",
                "notifyPermanent",
                "notifySecurity",
                "securityMinimumSeverity",
                "enableCisaKev",
                "lastSelectedTab",
            },
        )
        self.assertEqual(schema["refreshIntervalSec"]["type"], "integer")
        self.assertEqual(schema["refreshIntervalSec"]["min"], 900)
        self.assertEqual(schema["refreshIntervalSec"]["max"], 86400)
        self.assertEqual(
            schema["securityMinimumSeverity"]["options"], ["high", "critical"]
        )
        self.assertEqual(
            schema["lastSelectedTab"]["options"],
            ["Security", "Omarchy", "System", "AUR", "Flatpak", "mise"],
        )

    def test_manifest_rejects_hostile_json_shapes_when_parsed(self) -> None:
        self.require_product_files()
        base_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        unsafe_entry_points = ("../Service.qml", "/tmp/Service.qml")

        for entry_point in unsafe_entry_points:
            with self.subTest(entry_point=entry_point):
                manifest = base_manifest | {
                    "entryPoints": {
                        "service": entry_point,
                        "barWidget": "BarWidget.qml",
                    }
                }
                self.assertFalse(self.is_safe_manifest(manifest))

        for manifest in (
            base_manifest | {"schemaVersion": True},
            base_manifest | {"schemaVersion": 2},
            base_manifest | {"id": "omarchy.opatchy"},
            [base_manifest],
        ):
            with self.subTest(manifest=manifest):
                self.assertFalse(self.is_safe_manifest(manifest))

    def test_host_validator_rejects_hostile_fixture_copies(self) -> None:
        self.require_product_files()
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = Path(temporary_directory) / "plugin"
            shutil.copytree(
                REPOSITORY_ROOT,
                fixture_root,
                ignore=shutil.ignore_patterns(".git"),
            )

            cases = (
                (
                    "traversal",
                    {
                        "entryPoints": {
                            "service": "../Service.qml",
                            "barWidget": "BarWidget.qml",
                        }
                    },
                ),
                (
                    "absolute",
                    {
                        "entryPoints": {
                            "service": "/tmp/Service.qml",
                            "barWidget": "BarWidget.qml",
                        }
                    },
                ),
                ("schema", {"schemaVersion": 2}),
                ("boolean-schema", {"schemaVersion": True}),
                ("reserved-id", {"id": "omarchy.opatchy"}),
            )
            original = json.loads(
                (fixture_root / "manifest.json").read_text(encoding="utf-8")
            )

            for name, changes in cases:
                with self.subTest(name=name):
                    (fixture_root / "manifest.json").write_text(
                        json.dumps(original | changes), encoding="utf-8"
                    )
                    result = subprocess.run(
                        ["omarchy", "plugin", "validate", "."],
                        cwd=fixture_root,
                        check=False,
                        text=True,
                        capture_output=True,
                    )
                    self.assertNotEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )

            (fixture_root / "manifest.json").write_text(
                json.dumps(original), encoding="utf-8"
            )
            (fixture_root / "linked.qml").symlink_to(fixture_root / "Service.qml")
            result = subprocess.run(
                ["omarchy", "plugin", "validate", "."],
                cwd=fixture_root,
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_qml_facades_use_one_injected_service_and_visible_unavailable_state(
        self,
    ) -> None:
        self.require_product_files()
        service_source = (REPOSITORY_ROOT / "Service.qml").read_text(encoding="utf-8")
        lifecycle_source = (REPOSITORY_ROOT / "LifecycleState.qml").read_text(
            encoding="utf-8"
        )
        widget_source = (REPOSITORY_ROOT / "BarWidget.qml").read_text(encoding="utf-8")
        panel_source = (REPOSITORY_ROOT / "Panel.qml").read_text(encoding="utf-8")

        self.assertIn("Item {", service_source)
        self.assertIn("property var manifest: null", service_source)
        self.assertIn("manifest.__sourceDir", service_source)
        self.assertIn('localPath(sourceDir) + "/helper/opatchy.py"', service_source)
        self.assertEqual(service_source.count("Timer {"), 1)
        self.assertNotIn("Process {", service_source)
        self.assertNotIn("Qt.createComponent", service_source)
        self.assertNotIn("ensureService", service_source)
        self.assertIn("QtObject {", lifecycle_source)
        self.assertIn('typeof shell.serviceFor === "function"', lifecycle_source)
        self.assertIn("Service unavailable", lifecycle_source)
        self.assertIn("BarWidget {", widget_source)
        self.assertIn("LifecycleState {", widget_source)
        self.assertIn("LifecycleState {", panel_source)
        self.assertIn("lifecycleState.service", widget_source)
        self.assertIn("lifecycleState.service", panel_source)
        self.assertNotIn("Qt.createComponent", widget_source + panel_source)
        self.assertNotIn("Process {", widget_source + panel_source)
        self.assertNotIn("Timer {", widget_source + panel_source)

    def is_safe_manifest(self, manifest: dict[str, object] | list[object]) -> bool:
        if not isinstance(manifest, dict):
            return False
        if (
            type(manifest.get("schemaVersion")) is not int
            or manifest["schemaVersion"] != 1
        ):
            return False
        plugin_id = manifest.get("id")
        if not isinstance(plugin_id, str) or plugin_id.startswith("omarchy."):
            return False
        entry_points = manifest.get("entryPoints")
        if not isinstance(entry_points, dict):
            return False
        return all(
            isinstance(value, str)
            and value != ""
            and not value.startswith("/")
            and ".." not in value
            for value in entry_points.values()
        )


if __name__ == "__main__":
    unittest.main()
