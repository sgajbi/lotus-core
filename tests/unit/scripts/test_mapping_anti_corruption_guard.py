from pathlib import Path

from scripts.mapping_anti_corruption_guard import find_mapping_anti_corruption_findings


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_artifacts(root: Path) -> None:
    _write(
        root / "docs/architecture/mapping-anti-corruption-boundary.md",
        "API DTOs\n"
        "Event payloads\n"
        "Persistence repositories\n"
        "Source-data response envelopes\n"
        "make test-boundary-mapping-conformance\n"
        "#661\n"
        "#640\n"
        "#648\n",
    )
    _write(
        root / "docs/standards/api-mapper-pattern-standard.md",
        "build application commands\nmap application results\n",
    )
    _write(root / "scripts/api_mapper_pattern_guard.py", "find_api_mapper_pattern_findings\n")
    _write(
        root / "scripts/repository_output_shape_guard.py",
        "evaluate_repository_output_shapes\n",
    )
    _write(
        root / "src/services/ingestion_service/app/services/ingestion_event_payloads.py",
        "def business_date_event_payload(): pass\n"
        "def portfolio_event_payload(): pass\n"
        "def transaction_event_payload(): pass\n"
        "def instrument_event_payload(): pass\n"
        "def market_price_event_payload(): pass\n"
        "def fx_rate_event_payload(): pass\n",
    )
    _write(
        root / "src/services/ingestion_service/app/services/ingestion_service.py",
        "business_date_event_payload\n"
        "portfolio_event_payload\n"
        "transaction_event_payload\n"
        "instrument_event_payload\n"
        "market_price_event_payload\n"
        "fx_rate_event_payload\n",
    )
    _write(
        root / "src/libs/portfolio-common/portfolio_common/event_mapping.py",
        "def decode_kafka_event_payload(): pass\n"
        "def validate_kafka_event_payload(): pass\n"
        "def outbox_event_payload(): pass\n",
    )
    _write(
        root / "src/libs/portfolio-common/portfolio_common/events.py",
        "def event_business_payload(): pass\n",
    )
    _write(
        root / "src/services/persistence_service/app/adapters/persistence_event_adapter.py",
        "def decode_persistence_message_payload(): pass\n"
        "def validate_persistence_event_payload(): pass\n"
        "class PersistenceEventEnvelope: pass\n",
    )
    _write(
        root / "src/services/persistence_service/app/adapters/event_record_mapper.py",
        "def event_business_record_values(): pass\n"
        "def transaction_event_to_record_values(): pass\n",
    )
    _write(
        root / "src/services/persistence_service/app/repositories/transaction_db_repo.py",
        "transaction_event_to_record_values\n",
    )
    _write(
        root / "src/services/pipeline_orchestrator_service/app/adapters/outbox_event_mapper.py",
        "def pipeline_outbox_event_payload(): pass\noutbox_event_payload\n",
    )
    _write(
        root
        / "src/services/pipeline_orchestrator_service/app/services/pipeline_orchestrator_service.py",
        "pipeline_outbox_event_payload\n",
    )
    _write(
        root / "src/services/query_service/app/read_models.py",
        "class PortfolioTaxLotReadRecord: pass\n"
        "class PerformanceEconomicsTransactionReadRecord: pass\n"
        "class PerformanceEconomicsCashflowReadRecord: pass\n"
        "class PerformanceEconomicsCostReadRecord: pass\n",
    )
    _write(
        root / "src/services/query_service/app/services/performance_component_economics_rows.py",
        "def build_performance_component_economics_rows(): pass\n"
        "PerformanceEconomicsTransactionReadRecord\n",
    )
    _write(
        root / "src/services/query_service/app/services/performance_component_economics_policy.py",
        "performance_component_economics_source_lineage\n"
        "performance_component_economics_supportability_state\n",
    )
    _write(
        root
        / "src/services/query_service/app/services/performance_component_economics_response.py",
        "def build_performance_component_economics_response(): pass\n"
        "PerformanceComponentEconomicsResponse\n",
    )
    _write(
        root / "tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py",
        "test_transaction_mapping_chain_preserves_event_and_record_invariants\n"
        "test_persistence_message_adapter_preserves_event_identity_and_lineage\n"
        "test_source_data_tax_lot_mapping_preserves_lineage_and_envelope_identity\n"
        "test_performance_economics_mapping_uses_typed_read_records_for_optional_joins\n",
    )


def test_mapping_anti_corruption_guard_accepts_required_artifacts(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)

    assert find_mapping_anti_corruption_findings(tmp_path) == []


def test_mapping_anti_corruption_guard_rejects_missing_contract(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)
    (tmp_path / "docs/architecture/mapping-anti-corruption-boundary.md").unlink()

    findings = find_mapping_anti_corruption_findings(tmp_path)

    assert any(finding.rule == "missing-mapping-boundary-artifact" for finding in findings)


def test_mapping_anti_corruption_guard_rejects_missing_issue_links(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)
    _write(
        tmp_path / "docs/architecture/mapping-anti-corruption-boundary.md",
        "API DTOs\n"
        "Event payloads\n"
        "Persistence repositories\n"
        "Source-data response envelopes\n"
        "make test-boundary-mapping-conformance\n",
    )

    findings = find_mapping_anti_corruption_findings(tmp_path)

    assert any(finding.detail == "missing required snippet: #661" for finding in findings)


def test_mapping_anti_corruption_guard_rejects_inline_ingestion_dto_dump(
    tmp_path: Path,
) -> None:
    _write_required_artifacts(tmp_path)
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_service.py",
        "business_date_event_payload\n"
        "portfolio_event_payload\n"
        "transaction_event_payload\n"
        "instrument_event_payload\n"
        "market_price_event_payload\n"
        "fx_rate_event_payload\n"
        "payload = transaction.model_dump()\n",
    )

    findings = find_mapping_anti_corruption_findings(tmp_path)

    assert any(finding.rule == "forbidden-inline-boundary-mapping" for finding in findings)


def test_mapping_anti_corruption_guard_rejects_inline_pipeline_outbox_dump(
    tmp_path: Path,
) -> None:
    _write_required_artifacts(tmp_path)
    _write(
        tmp_path
        / "src/services/pipeline_orchestrator_service/app/services/pipeline_orchestrator_service.py",
        "pipeline_outbox_event_payload\npayload = outbox_event_payload(event)\n",
    )

    findings = find_mapping_anti_corruption_findings(tmp_path)

    assert any(finding.rule == "forbidden-inline-boundary-mapping" for finding in findings)
