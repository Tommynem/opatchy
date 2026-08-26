import socket
import tempfile
from pathlib import Path

from tests.fixtures.factories import temporary_repository


def test_temporary_repository_skips_local_codegraph_socket_when_copying() -> None:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source"
        (source / "tests" / "tooling").mkdir(parents=True)
        _ = (source / "product.txt").write_text("product input", encoding="utf-8")
        _ = (source / ".omo" / "draft.txt").parent.mkdir()
        _ = (source / ".omo" / "draft.txt").write_text("kept", encoding="utf-8")
        socket_path = source / ".codegraph" / "daemon.sock"
        socket_path.parent.mkdir()

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(socket_path))
            with temporary_repository(source) as repository:
                assert (
                    repository.path("product.txt").read_text(encoding="utf-8")
                    == "product input"
                )
                assert (
                    repository.path(".omo/draft.txt").read_text(encoding="utf-8")
                    == "kept"
                )
                assert not repository.path(".codegraph").exists()
