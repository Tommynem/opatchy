import os
import tempfile
from pathlib import Path
from typing import BinaryIO, Final, Protocol, final

PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600


class AtomicOperations(Protocol):
    def write(self, handle: BinaryIO, data: bytes) -> int: ...

    def fsync(self, descriptor: int) -> None: ...

    def replace(self, source: Path, destination: Path) -> None: ...


@final
class SystemAtomicOperations:
    def write(self, handle: BinaryIO, data: bytes) -> int:
        return handle.write(data)

    def fsync(self, descriptor: int) -> None:
        os.fsync(descriptor)

    def replace(self, source: Path, destination: Path) -> None:
        os.replace(source, destination)


def atomic_write(path: Path, data: bytes, operations: AtomicOperations) -> None:
    ensure_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    replaced = False
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "wb") as handle:
            written = operations.write(handle, data)
            if written != len(data):
                raise OSError("atomic write was partial")
            handle.flush()
            operations.fsync(handle.fileno())
        operations.replace(temporary_path, path)
        replaced = True
        os.chmod(path, PRIVATE_FILE_MODE)
        fsync_directory(path.parent, operations)
    except OSError:
        if not replaced:
            temporary_path.unlink(missing_ok=True)
        raise


def ensure_directory(path: Path) -> None:
    path.mkdir(mode=PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
    os.chmod(path, PRIVATE_DIRECTORY_MODE)


def fsync_directory(path: Path, operations: AtomicOperations) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        operations.fsync(descriptor)
    finally:
        os.close(descriptor)
