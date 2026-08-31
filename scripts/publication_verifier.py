from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.publication_model import BacklogError, parse_backlog
from scripts.publication_verifier_model import APPROVED_PLUGIN_ID, VerifierError
from scripts.publication_verifier_service import CommandResult, PublicationVerifier


@dataclass(frozen=True, slots=True)
class Arguments:
    mode: str
    plugin_id: str
    backlog: Path | None


class SubprocessRunner:
    def run(self, arguments: tuple[str, ...]) -> CommandResult:
        result = subprocess.run(  # noqa: S603
            arguments, capture_output=True, check=False, text=True
        )
        return CommandResult(result.returncode, result.stdout, result.stderr)


def parse_arguments(arguments: tuple[str, ...]) -> Arguments:
    if (
        len(arguments) not in (6, 8)
        or arguments[:1] != ("--mode",)
        or arguments[2:3] != ("--repository",)
        or arguments[3:4] != ("Tommynem/opatchy",)
        or arguments[4:5] != ("--plugin-id",)
        or (len(arguments) == 8 and arguments[6:7] != ("--backlog",))
    ):
        raise VerifierError("publication verifier arguments are invalid")
    mode, plugin_id = arguments[1], arguments[5]
    backlog = Path(arguments[7]) if len(arguments) == 8 else None
    if mode not in {"pre-publication", "published"} or plugin_id != APPROVED_PLUGIN_ID:
        raise VerifierError("approved mode or plugin ID is invalid")
    if (mode == "published") != (backlog is not None):
        raise VerifierError("published mode requires exactly one backlog path")
    return Arguments(mode, plugin_id, backlog)


def main() -> int:
    try:
        arguments = parse_arguments(tuple(sys.argv[1:]))
        verifier = PublicationVerifier(SubprocessRunner())
        if arguments.mode == "pre-publication":
            report = verifier.verify_pre_publication(arguments.plugin_id)
        else:
            if arguments.backlog is None:
                raise VerifierError("published mode requires a backlog")
            report = verifier.verify_published(
                parse_backlog(arguments.backlog.read_text(encoding="utf-8")),
                arguments.plugin_id,
            )
        print(
            "PASS(publication-verifier): "
            + " ".join(
                (
                    f"mode={report.mode}",
                    f"remoteSha={report.remote_sha}",
                    f"marketplaceSha={report.marketplace_sha}",
                )
            )
        )
    except (BacklogError, OSError, VerifierError) as error:
        print(f"ERROR(publication-verifier): {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
