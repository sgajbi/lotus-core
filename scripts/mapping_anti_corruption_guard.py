from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CONTRACT_PATH = Path("docs/architecture/mapping-anti-corruption-boundary.md")

REQUIRED_SNIPPETS = {
    CONTRACT_PATH: (
        "API DTOs",
        "Event payloads",
        "Persistence repositories",
        "Source-data response envelopes",
        "make test-boundary-mapping-conformance",
        "#661",
        "#640",
        "#648",
    ),
    Path("docs/standards/api-mapper-pattern-standard.md"): (
        "build application commands",
        "map application results",
    ),
    Path("scripts/api_mapper_pattern_guard.py"): ("find_api_mapper_pattern_findings",),
    Path("scripts/repository_output_shape_guard.py"): ("evaluate_repository_output_shapes",),
    Path("src/services/ingestion_service/app/services/ingestion_event_payloads.py"): (
        "def business_date_event_payload",
        "def portfolio_event_payload",
        "def transaction_event_payload",
        "def instrument_event_payload",
        "def market_price_event_payload",
        "def fx_rate_event_payload",
    ),
    Path("src/services/ingestion_service/app/services/ingestion_service.py"): (
        "business_date_event_payload",
        "portfolio_event_payload",
        "transaction_event_payload",
        "instrument_event_payload",
        "market_price_event_payload",
        "fx_rate_event_payload",
    ),
    Path("src/libs/portfolio-common/portfolio_common/event_mapping.py"): (
        "def decode_kafka_event_payload",
        "def validate_kafka_event_payload",
        "def outbox_event_payload",
    ),
    Path("src/libs/portfolio-common/portfolio_common/events.py"): ("def event_business_payload",),
    Path("src/services/persistence_service/app/adapters/persistence_event_adapter.py"): (
        "def decode_persistence_message_payload",
        "def validate_persistence_event_payload",
        "PersistenceEventEnvelope",
    ),
    Path("src/services/persistence_service/app/adapters/event_record_mapper.py"): (
        "def event_business_record_values",
        "def transaction_event_to_record_values",
    ),
    Path("src/services/persistence_service/app/repositories/transaction_db_repo.py"): (
        "transaction_event_to_record_values",
    ),
    Path("src/services/pipeline_orchestrator_service/app/adapters/outbox_event_mapper.py"): (
        "def pipeline_outbox_event_payload",
        "outbox_event_payload",
    ),
    Path(
        "src/services/pipeline_orchestrator_service/app/services/pipeline_orchestrator_service.py"
    ): ("pipeline_outbox_event_payload",),
    Path("src/services/query_service/app/read_models.py"): (
        "class PortfolioTaxLotReadRecord",
        "class PerformanceEconomicsTransactionReadRecord",
        "class PerformanceEconomicsCashflowReadRecord",
        "class PerformanceEconomicsCostReadRecord",
    ),
    Path("src/services/query_service/app/services/performance_component_economics_rows.py"): (
        "def build_performance_component_economics_rows",
        "PerformanceEconomicsTransactionReadRecord",
    ),
    Path("src/services/query_service/app/services/performance_component_economics_policy.py"): (
        "performance_component_economics_source_lineage",
        "performance_component_economics_supportability_state",
    ),
    Path("src/services/query_service/app/services/performance_component_economics_response.py"): (
        "def build_performance_component_economics_response",
        "PerformanceComponentEconomicsResponse",
    ),
    Path("tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py"): (
        "test_transaction_mapping_chain_preserves_event_and_record_invariants",
        "test_persistence_message_adapter_preserves_event_identity_and_lineage",
        "test_source_data_tax_lot_mapping_preserves_lineage_and_envelope_identity",
        "test_performance_economics_mapping_uses_typed_read_records_for_optional_joins",
    ),
}

FORBIDDEN_SNIPPETS = {
    Path("src/services/ingestion_service/app/services/ingestion_service.py"): (
        "transaction.model_dump(",
        "portfolio.model_dump(",
        "business_date.model_dump(",
        "instrument.model_dump(",
        "price.model_dump(",
        "rate.model_dump(",
    ),
    Path("src/services/persistence_service/app/repositories/transaction_db_repo.py"): (
        "_TRANSACTION_EVENT_ONLY_FIELDS",
        "event_business_payload(",
    ),
    Path(
        "src/services/pipeline_orchestrator_service/app/services/pipeline_orchestrator_service.py"
    ): (
        "payload=outbox_event_payload(",
        "payload = outbox_event_payload(",
        '.model_dump(mode="json")',
    ),
}


@dataclass(frozen=True, slots=True)
class MappingAntiCorruptionFinding:
    path: str
    rule: str
    detail: str

    def as_text(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


def find_mapping_anti_corruption_findings(root: Path) -> list[MappingAntiCorruptionFinding]:
    findings: list[MappingAntiCorruptionFinding] = []
    for relative_path, snippets in REQUIRED_SNIPPETS.items():
        path = root / relative_path
        if not path.exists():
            findings.append(
                MappingAntiCorruptionFinding(
                    path=relative_path.as_posix(),
                    rule="missing-mapping-boundary-artifact",
                    detail="required mapping or anti-corruption artifact is missing",
                )
            )
            continue
        source = path.read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in source:
                findings.append(
                    MappingAntiCorruptionFinding(
                        path=relative_path.as_posix(),
                        rule="missing-mapping-boundary-snippet",
                        detail=f"missing required snippet: {snippet}",
                    )
                )

    for relative_path, snippets in FORBIDDEN_SNIPPETS.items():
        path = root / relative_path
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet in source:
                findings.append(
                    MappingAntiCorruptionFinding(
                        path=relative_path.as_posix(),
                        rule="forbidden-inline-boundary-mapping",
                        detail=f"forbidden inline mapping snippet remains: {snippet}",
                    )
                )
    return findings


def main() -> int:
    findings = find_mapping_anti_corruption_findings(Path.cwd())
    if findings:
        print("Mapping anti-corruption guard failed:")
        for finding in findings:
            print(f"  - {finding.as_text()}")
        return 1
    print("Mapping anti-corruption guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
