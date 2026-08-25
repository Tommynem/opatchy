from pathlib import Path
import re
import tempfile
from typing import Final
import unittest


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
REQUIRED_FILES: Final = (
    "LICENSE",
    ".gitignore",
    "README.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "docs/architecture.md",
    "docs/threat-model.md",
    "docs/compatibility.md",
)
PLUGIN_ID: Final = "io.github.tomge.opatchy"
VERSION: Final = "0.1.0"
PUBLIC_URL: Final = "https://github.com/tomge/opatchy"
PROHIBITED_ASSURANCE_PHRASES: Final = (
    "machine is safe",
    "machine is secure",
    "system is safe",
    "system is secure",
    "safe system",
    "secure system",
    "not exploitable",
    "fully protected",
)


class RepositoryContractTests(unittest.TestCase):
    def assert_manifest_identity(self, manifest_path: Path) -> None:
        manifest = manifest_path.read_text(encoding="utf-8")
        schema_version = re.search(
            r'"schemaVersion"\s*:\s*(true|false|-?[0-9]+)',
            manifest,
        )

        self.assertIsNotNone(schema_version)
        assert schema_version is not None
        self.assertEqual(schema_version.group(1), "1")
        for field, value in (
            ("id", PLUGIN_ID),
            ("name", "Opatchy"),
            ("version", VERSION),
        ):
            with self.subTest(field=field):
                self.assertRegex(
                    manifest,
                    rf'"{field}"\s*:\s*"{re.escape(value)}"',
                )

    def test_repository_foundation_exists_when_checkout_is_inspected(self) -> None:
        missing_files = [
            path for path in REQUIRED_FILES if not (REPOSITORY_ROOT / path).is_file()
        ]

        self.assertEqual(missing_files, [])

    def test_readme_declares_central_contract_when_read(self) -> None:
        readme_path = REPOSITORY_ROOT / "README.md"
        self.assertTrue(readme_path.is_file())
        readme = readme_path.read_text(encoding="utf-8")
        normalized_readme = " ".join(readme.split())

        for required_claim in (
            "Opatchy",
            PLUGIN_ID,
            VERSION,
            "MIT",
            PUBLIC_URL,
            "Omarchy 4",
            "schema v1",
            "no runtime telemetry",
            "does not perform privileged, partial, unattended, or package-specific updates",
            "opens native update workflows",
            "uv sync --group dev",
            "make validate",
        ):
            with self.subTest(required_claim=required_claim):
                self.assertIn(required_claim, normalized_readme)

        lowered_readme = readme.lower()
        for prohibited_phrase in PROHIBITED_ASSURANCE_PHRASES:
            with self.subTest(prohibited_phrase=prohibited_phrase):
                self.assertNotIn(prohibited_phrase, lowered_readme)

    def test_manifest_identity_is_consistent_when_manifest_arrives(self) -> None:
        manifest_path = REPOSITORY_ROOT / "manifest.json"

        if manifest_path.exists():
            self.assert_manifest_identity(manifest_path)

    def test_manifest_identity_rejects_boolean_schema_when_manifest_is_present(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest_path = Path(temporary_directory) / "manifest.json"
            _ = manifest_path.write_text(
                '{"schemaVersion": true, "id": "io.github.tomge.opatchy", "name": "Opatchy", "version": "0.1.0"}',
                encoding="utf-8",
            )

            with self.assertRaises(AssertionError):
                self.assert_manifest_identity(manifest_path)


if __name__ == "__main__":
    _ = unittest.main()
