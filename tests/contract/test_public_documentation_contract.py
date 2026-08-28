from pathlib import Path
import re
import tempfile
from typing import Final
import unittest


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
DOCUMENTS: Final = (
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/architecture.md",
    "docs/compatibility.md",
    "docs/data-sources.md",
    "docs/privacy.md",
    "docs/threat-model.md",
)
REQUIRED_TEMPLATES: Final = (
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
)
FORBIDDEN_CLAIMS: Final = (
    "curl | sh",
    "curl|sh",
    "verified security",
    "universal compatibility",
    "machine is safe",
    "machine is secure",
    "not exploitable",
    "fully protected",
)
REQUIRED_RUNTIME_TOKENS: Final = (
    "https://security.archlinux.org/all.json",
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
    "/usr/bin/omarchy-update-available",
    "/usr/bin/pacman",
    "/usr/bin/checkupdates",
    "/usr/bin/yay",
    "/usr/bin/paru",
    "/usr/bin/flatpak",
    "/usr/bin/mise",
    "/usr/bin/arch-audit",
    "/usr/bin/notify-send",
)
HANDOFF_EXECUTABLE: Final = (
    "/usr/bin/omarchy-launch-floating-terminal-with-presentation"
)


class PublicDocumentationContractTests(unittest.TestCase):
    def test_public_contract_files_exist_when_checkout_is_inspected(self) -> None:
        missing = tuple(
            path
            for path in (*DOCUMENTS, *REQUIRED_TEMPLATES)
            if not (REPOSITORY_ROOT / path).is_file()
        )

        self.assertEqual(missing, ())

    def test_data_source_contract_matches_closed_runtime_registry(self) -> None:
        data_sources = self.read("docs/data-sources.md")
        registry = self.read("helper/opatchy_helper/runner_registry.py")
        handoff = self.read("qml/models/ActionPolicy.js")

        for token in REQUIRED_RUNTIME_TOKENS:
            with self.subTest(token=token):
                self.assertIn(token, registry)
                self.assertIn(token, data_sources)

        self.assertIn(HANDOFF_EXECUTABLE, handoff)
        self.assertIn(HANDOFF_EXECUTABLE, data_sources)

    def test_public_docs_keep_identity_paths_and_operating_limits(self) -> None:
        public_text = self.public_text()

        for required in (
            "io.github.tomge.opatchy",
            "0.1.0",
            "xdg_state_home",
            "xdg_cache_home",
            "no runtime telemetry",
            "do not disturb",
            "does not inspect do not disturb state",
            "last-known evidence",
            "not a current result",
            "unsandboxed",
            "omarchy plugin add",
            "omarchy plugin enable",
            "omarchy plugin disable",
            "omarchy plugin remove",
        ):
            with self.subTest(required=required):
                self.assertIn(required, public_text)

        self.assertIn(
            "does not wire notification dispatch into the production scan path",
            self.read("README.md"),
        )
        self.assertIn(
            "does not recommend direct `pacman -Syu`",
            " ".join(self.read("README.md").split()),
        )

    def test_internal_markdown_links_resolve_when_docs_are_published(self) -> None:
        links = (
            ("README.md", "CONTRIBUTING.md"),
            ("README.md", "SECURITY.md"),
            ("README.md", "docs/architecture.md"),
            ("README.md", "docs/privacy.md"),
            ("README.md", "docs/threat-model.md"),
            ("docs/privacy.md", "docs/data-sources.md"),
            ("docs/threat-model.md", "SECURITY.md"),
            ("SECURITY.md", "docs/threat-model.md"),
        )

        for source, target in links:
            with self.subTest(source=source, target=target):
                self.assertTrue((REPOSITORY_ROOT / target).is_file())
                self.assertIn(Path(target).name, self.read(source))

    def test_forbidden_claim_mutations_are_rejected(self) -> None:
        for forbidden in FORBIDDEN_CLAIMS:
            with self.subTest(forbidden=forbidden):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    candidate = Path(temporary_directory) / "README.md"
                    candidate.write_text(
                        self.read("README.md") + forbidden, encoding="utf-8"
                    )
                    self.assertNotEqual(
                        self.forbidden_claims(candidate.read_text()), ()
                    )

        unsafe_pacman = self.read("README.md") + "\n```sh\npacman -Syu\n```\n"
        self.assertTrue(self.has_direct_pacman_advice(unsafe_pacman))
        self.assertFalse(self.has_direct_pacman_advice(self.read("README.md")))

    def test_missing_endpoint_and_dependency_mutations_are_rejected(self) -> None:
        original = self.read("docs/data-sources.md")

        for token in REQUIRED_RUNTIME_TOKENS:
            with self.subTest(token=token):
                mutated = original.replace(token, "removed")
                self.assertNotEqual(self.missing_runtime_tokens(mutated), ())

        mutated_handoff = original.replace(HANDOFF_EXECUTABLE, "removed")
        self.assertNotIn(HANDOFF_EXECUTABLE, mutated_handoff)

    def read(self, relative_path: str) -> str:
        return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")

    def public_text(self) -> str:
        return "\n".join(self.read(path) for path in DOCUMENTS).lower()

    def forbidden_claims(self, text: str) -> tuple[str, ...]:
        lowered = text.lower()
        return tuple(claim for claim in FORBIDDEN_CLAIMS if claim in lowered)

    def missing_runtime_tokens(self, text: str) -> tuple[str, ...]:
        return tuple(token for token in REQUIRED_RUNTIME_TOKENS if token not in text)

    def has_direct_pacman_advice(self, text: str) -> bool:
        return re.search(r"```sh\s*pacman -Syu", text) is not None


if __name__ == "__main__":
    unittest.main()
