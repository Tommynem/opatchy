import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, assert_never

from opatchy_helper.models import (
    GenerationId,
    InventoryPayload,
    InventoryResponse,
    ItemId,
    ItemSource,
    NormalizedItem,
    Provenance,
    Response,
    ResponseKind,
    WatchMode,
)
from opatchy_helper.protocol import decode_response
from opatchy_helper.storage import Storage, SystemAtomicOperations

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
ENTRYPOINT: Final = REPOSITORY_ROOT / "helper" / "opatchy.py"
NOW: Final = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)


def item(
    item_id: str,
    source: ItemSource,
    label: str,
    installed: str | None = "1.0",
    candidate: str | None = "1.1",
) -> NormalizedItem:
    return NormalizedItem(
        ItemId(item_id),
        source,
        label,
        installed,
        candidate,
        WatchMode.OFF,
        True,
        Provenance.CACHE,
    )


def storage(tmp_path: Path) -> Storage:
    return Storage(
        tmp_path / "state" / "opatchy" / "state.json",
        tmp_path / "cache" / "opatchy",
        lambda: NOW,
        SystemAtomicOperations(),
    )


def write_inventory(store: Storage, source: ItemSource, *items: NormalizedItem) -> None:
    store.save_inventory(
        InventoryResponse(
            NOW,
            GenerationId("cached-generation"),
            InventoryPayload(source, len(items), items),
        )
    )


def environment(tmp_path: Path) -> dict[str, str]:
    value = os.environ.copy()
    value["XDG_STATE_HOME"] = str(tmp_path / "state")
    value["XDG_CACHE_HOME"] = str(tmp_path / "cache")
    _ = value.pop("PYTHONPATH", None)
    value["PYTHONNOUSERSITE"] = "1"
    return value


def run_cli(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/python3", str(ENTRYPOINT), *arguments],
        check=False,
        capture_output=True,
        cwd=REPOSITORY_ROOT,
        encoding="utf-8",
        env=environment(tmp_path),
    )


def inventory_cli(
    tmp_path: Path, source: str, query: str, limit: str, offset: str
) -> subprocess.CompletedProcess[str]:
    return run_cli(
        tmp_path,
        "inventory",
        "--source",
        source,
        "--query",
        query,
        "--limit",
        limit,
        "--offset",
        offset,
    )


def star_cli(
    tmp_path: Path, item_id: str, mode: str
) -> subprocess.CompletedProcess[str]:
    return run_cli(tmp_path, "set-star", "--item-id", item_id, "--mode", mode)


def concurrent_star(
    tmp_path: Path, first_id: str, second_id: str
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    first = subprocess.Popen(
        [
            "/usr/bin/python3",
            str(ENTRYPOINT),
            "set-star",
            "--item-id",
            first_id,
            "--mode",
            "temporary",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=REPOSITORY_ROOT,
        env=environment(tmp_path),
    )
    second = subprocess.Popen(
        [
            "/usr/bin/python3",
            str(ENTRYPOINT),
            "set-star",
            "--item-id",
            second_id,
            "--mode",
            "temporary",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=REPOSITORY_ROOT,
        env=environment(tmp_path),
    )
    first_stdout, first_stderr = first.communicate(timeout=5)
    second_stdout, second_stderr = second.communicate(timeout=5)
    return (
        subprocess.CompletedProcess((), first.returncode, first_stdout, first_stderr),
        subprocess.CompletedProcess(
            (), second.returncode, second_stdout, second_stderr
        ),
    )


def response(result: subprocess.CompletedProcess[str]) -> Response:
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1
    assert result.stdout.endswith("\n")
    return decode_response(result.stdout.encode())


def kind(value: Response) -> ResponseKind:
    from opatchy_helper.models import (
        ErrorResponse,
        InventoryResponse,
        SnapshotResponse,
        StarResultResponse,
    )

    match value:
        case SnapshotResponse():
            return ResponseKind.SNAPSHOT
        case InventoryResponse():
            return ResponseKind.INVENTORY
        case StarResultResponse():
            return ResponseKind.STAR_RESULT
        case ErrorResponse():
            return ResponseKind.ERROR
    assert_never(value)
