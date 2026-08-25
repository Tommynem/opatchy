import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class HarnessContractTests(unittest.TestCase):
    def test_quality_harness_files_exist_when_checkout_is_inspected(self) -> None:
        required_files = (
            "pyproject.toml",
            "Makefile",
            "scripts/validate.sh",
            "scripts/qml_offscreen.sh",
            "tests/fixtures/factories.py",
        )

        missing_files = [
            path for path in required_files if not (REPOSITORY_ROOT / path).is_file()
        ]

        assert missing_files == []
