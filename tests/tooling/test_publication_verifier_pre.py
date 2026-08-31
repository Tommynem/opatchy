import pytest

from scripts.publication_verifier_model import APPROVED_PLUGIN_ID, VerifierError
from scripts.publication_verifier_service import CommandResult, PublicationVerifier
from tests.tooling.publication_verifier_fixtures import (
    FakeRunner,
    marketplace,
    registry,
    result,
    target,
)


@pytest.mark.parametrize("method", ("verify_pre_publication", "verify_published"))
def test_wrong_plugin_id_stops_before_any_command(method: str) -> None:
    runner = FakeRunner(())
    verifier = PublicationVerifier(runner)

    with pytest.raises(VerifierError, match="plugin ID"):
        if method == "verify_pre_publication":
            _ = verifier.verify_pre_publication("wrong.plugin")
        else:
            _ = verifier.verify_published((), "wrong.plugin")

    assert runner.calls == []


def test_wrong_owner_stops_after_owner_lookup() -> None:
    runner = FakeRunner((result("other\n"),))

    with pytest.raises(VerifierError, match="owner"):
        _ = PublicationVerifier(runner).verify_pre_publication(APPROVED_PLUGIN_ID)

    assert runner.calls == [("gh", "api", "user", "--jq", ".login")]


@pytest.mark.parametrize("response", (target(False), target(True, "READ")))
def test_target_rejections_stop_before_marketplace(response: str) -> None:
    runner = FakeRunner((result("Tommynem\n"), result(response)))

    with pytest.raises(VerifierError, match="target repository"):
        _ = PublicationVerifier(runner).verify_pre_publication(APPROVED_PLUGIN_ID)

    assert len(runner.calls) == 2


@pytest.mark.parametrize(
    "document",
    (registry(APPROVED_PLUGIN_ID), registry(retired=f'["{APPROVED_PLUGIN_ID}"]')),
)
def test_active_or_retired_collision_stops_after_pinned_registry(document: str) -> None:
    runner = FakeRunner(
        (result("Tommynem\n"), result(target(True)), *marketplace(document))
    )

    with pytest.raises(VerifierError, match="marketplace collision"):
        _ = PublicationVerifier(runner).verify_pre_publication(APPROVED_PLUGIN_ID)

    assert len(runner.calls) == 5
    assert runner.calls[-1][-2:] == ("-H", "Accept: application/vnd.github.raw+json")


@pytest.mark.parametrize(
    "document",
    (
        '{"sources":[{"plugins":[]}],"retiredPluginIds":[]}',
        '{"sources":[],"retiredPluginIds":["x","x"]}',
    ),
)
def test_malformed_registry_stops_after_pinned_read(document: str) -> None:
    runner = FakeRunner(
        (result("Tommynem\n"), result(target(True)), *marketplace(document))
    )

    with pytest.raises(VerifierError, match="marketplace registry"):
        _ = PublicationVerifier(runner).verify_pre_publication(APPROVED_PLUGIN_ID)

    assert len(runner.calls) == 5


def test_nonzero_command_stops_immediately() -> None:
    runner = FakeRunner((CommandResult(1, "", "denied"),))

    with pytest.raises(VerifierError, match="owner lookup failed"):
        _ = PublicationVerifier(runner).verify_pre_publication(APPROVED_PLUGIN_ID)

    assert len(runner.calls) == 1
