"""Guard migrated derived-state integration tests against retired repository facades."""

from pathlib import Path

INTEGRATION_ROOT = Path("tests/integration/services/portfolio_derived_state_service")
RETIRED_REPOSITORY_CALLS = (
    "find_and_claim_eligible_jobs(",
    "find_and_reset_stale_jobs(",
)


def test_integration_contracts_use_active_lease_repository_api() -> None:
    """Reject collectable tests that silently follow removed repository methods."""

    stale_calls = {
        str(path): retired_call
        for path in INTEGRATION_ROOT.rglob("test_*.py")
        for retired_call in RETIRED_REPOSITORY_CALLS
        if retired_call in path.read_text(encoding="utf-8")
    }

    assert stale_calls == {}
