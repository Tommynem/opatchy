from pathlib import Path
from typing import Final

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
PLUGIN_ID: Final = "io.github.tommynem.opatchy"
PUBLIC_URL: Final = "https://github.com/Tommynem/opatchy"


def test_published_identity_is_consistent_when_release_files_are_read() -> None:
    # Given: the committed manifest and public install instructions.
    manifest = (REPOSITORY_ROOT / "manifest.json").read_text(encoding="utf-8")
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    bar_widget = (REPOSITORY_ROOT / "BarWidget.qml").read_text(encoding="utf-8")
    panel = (REPOSITORY_ROOT / "Panel.qml").read_text(encoding="utf-8")

    # When: their public identity is compared.
    # Then: every public entry point names the approved owner and installation URL.
    assert f'"id": "{PLUGIN_ID}"' in manifest
    assert PUBLIC_URL in readme
    assert f"omarchy plugin add {PUBLIC_URL} --enable" in readme
    assert PLUGIN_ID in bar_widget
    assert PLUGIN_ID in panel
