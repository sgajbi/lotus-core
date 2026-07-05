from pathlib import Path

from scripts.api_mapper_pattern_guard import find_api_mapper_pattern_findings


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_artifacts(root: Path) -> None:
    _write(root / "docs/standards/api-mapper-pattern-standard.md", "standard")
    _write(
        root / "src/services/query_service/app/routers/lookup_mappers.py",
        "def lookup_response_from_result(): pass\nLookupCatalogResult\nLookupResponse\n",
    )
    _write(
        root / "src/services/query_service/app/routers/lookups.py",
        "from .lookup_mappers import lookup_response_from_result\n",
    )
    _write(
        root
        / "src/services/financial_reconciliation_service/app/routers/reconciliation_mappers.py",
        "def reconciliation_run_command_from_request(): pass\n"
        "def reconciliation_run_not_found(): pass\n"
        "ReconciliationRunCommand\n",
    )
    _write(
        root / "src/services/financial_reconciliation_service/app/routers/reconciliation.py",
        "reconciliation_run_command_from_request\nreconciliation_run_not_found\n",
    )
    _write(
        root / "src/services/event_replay_service/app/routers/replay_mappers.py",
        "def command_error_to_http(): pass\nHTTPException\n",
    )
    _write(
        root / "src/services/event_replay_service/app/routers/ingestion_operations.py",
        "from .replay_mappers import command_error_to_http\n",
    )
    _write(
        root / "src/services/query_service/app/routers/http_errors.py",
        "def lookup_error_to_http(): pass\n"
        "def value_error_to_http(): pass\n"
        "def value_error_as_resolution_http(): pass\n",
    )
    for path in (
        "src/services/query_service/app/routers/buy_state.py",
        "src/services/query_service/app/routers/cash_accounts.py",
        "src/services/query_service/app/routers/cash_movements.py",
        "src/services/query_service/app/routers/positions.py",
        "src/services/query_service/app/routers/reporting.py",
        "src/services/query_service/app/routers/sell_state.py",
        "src/services/query_service/app/routers/transactions.py",
    ):
        _write(root / path, "from .http_errors import lookup_error_to_http\n")


def test_api_mapper_pattern_guard_accepts_required_artifacts(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)

    assert find_api_mapper_pattern_findings(tmp_path) == []


def test_api_mapper_pattern_guard_rejects_missing_mapper(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)
    (tmp_path / "src/services/query_service/app/routers/lookup_mappers.py").unlink()

    findings = find_api_mapper_pattern_findings(tmp_path)

    assert any(finding.rule == "missing-api-mapper-artifact" for finding in findings)


def test_api_mapper_pattern_guard_rejects_router_local_lookup_mapper(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)
    _write(
        tmp_path / "src/services/query_service/app/routers/lookups.py",
        "from .lookup_mappers import lookup_response_from_result\n"
        "def lookup_response_from_result(): pass\n",
    )

    findings = find_api_mapper_pattern_findings(tmp_path)

    assert any(finding.rule == "forbidden-router-mapping-snippet" for finding in findings)


def test_api_mapper_pattern_guard_rejects_inline_reconciliation_command(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)
    _write(
        tmp_path / "src/services/financial_reconciliation_service/app/routers/reconciliation.py",
        "reconciliation_run_command_from_request\n"
        "reconciliation_run_not_found\n"
        "command = ReconciliationRunCommand(portfolio_id='PF-1')\n",
    )

    findings = find_api_mapper_pattern_findings(tmp_path)

    assert any(finding.rule == "forbidden-router-mapping-snippet" for finding in findings)


def test_api_mapper_pattern_guard_rejects_inline_command_error_mapping(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)
    _write(
        tmp_path / "src/services/event_replay_service/app/routers/ingestion_operations.py",
        "from .replay_mappers import command_error_to_http\n"
        "raise HTTPException(status_code=exc.status_code, detail=exc.detail)\n",
    )

    findings = find_api_mapper_pattern_findings(tmp_path)

    assert any(finding.rule == "forbidden-router-mapping-snippet" for finding in findings)


def test_api_mapper_pattern_guard_rejects_inline_query_error_mapping(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)
    _write(
        tmp_path / "src/services/query_service/app/routers/transactions.py",
        "from .http_errors import lookup_error_to_http\n"
        "raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))\n",
    )

    findings = find_api_mapper_pattern_findings(tmp_path)

    assert any(finding.rule == "forbidden-router-mapping-snippet" for finding in findings)
