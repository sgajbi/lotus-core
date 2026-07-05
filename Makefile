.PHONY: install install-ci verify-dependencies compile-runtime-lock quality-ruff-gate quality-ruff-format-gate quality-import-boundary-gate quality-bandit-gate quality-vulture-source-gate quality-deptry-source-gate quality-maintainability-gate quality-complexity-gate quality-unit-collection-gate quality-integration-lite-collection-gate quality-workflow-governance-gate quality-openapi-spectral-gate quality-wiki-docs-gate docs-evidence-pack lint typecheck architecture-guard monetary-float-guard structured-log-guard qcp-problem-details-guard metric-vocabulary-guard repository-output-shape-guard security-control-coverage-guard supported-features-guard incident-playbook-guard domain-layer-guard testability-architecture-guard runtime-boundary-decision-guard in-process-modularity-guard in-process-boundary-guard proof-builder-pattern-guard api-mapper-pattern-guard api-example-catalog-guard architecture-docs-catalog-guard image-provenance-guard mapping-anti-corruption-guard runtime-provider-port-guard application-layer-contract-guard application-port-catalog-guard application-dependency-inversion-guard application-workflow-policy-guard application-error-taxonomy-guard application-command-result-guard ingestion-service-framework-guard upload-component-boundary-guard transaction-replay-boundary-guard aggregation-scheduler-boundary-guard position-reducer-boundary-guard infrastructure-adapter-layer-guard repository-transaction-boundary-guard ingestion-store-port-guard event-publisher-port-guard repository-port-guard ingestion-contract-gate ingestion-rate-limit-scope-guard config-access-guard temporal-vocabulary-guard route-contract-family-guard source-data-product-contract-guard endpoint-consolidation-watchlist-guard domain-product-validate analytics-input-consumer-contract-guard event-runtime-contract-guard rfc0083-closure-guard no-alias-gate openapi-gate api-vocabulary-gate warning-gate migration-smoke migration-apply test test-fast test-medium test-heavy test-unit test-unit-db test-integration-lite test-integration-all test-ops-contract test-boundary-mapping-conformance test-transaction-buy-contract test-transaction-sell-contract test-transaction-dividend-contract test-transaction-interest-contract test-transaction-fx-contract test-transaction-portfolio-flow-bundle-contract test-e2e-smoke test-e2e-all test-docker-smoke test-latency-gate test-performance-load-gate test-performance-load-gate-full test-failure-recovery-gate test-institutional-completion-gate test-institutional-signoff-pack lotus-core-validate test-pr-suites test-pr-runtime-gates test-release-gates security-audit check coverage-gate ci ci-main ci-local docker-build docker-prebuild-ci live-dpm-source-validate clean
.PHONY: ingestion-gateway-rate-limit-policy-guard

LATENCY_SEED_COMPLETION_TIMEOUT_SECONDS ?= 900
OPENAPI_ARTIFACT_DIR ?= output/openapi

install:
	python scripts/bootstrap_dev.py

install-ci:
	python scripts/bootstrap_dev.py

verify-dependencies:
	python scripts/dependency_health_check.py --skip-audit

compile-runtime-lock:
	python scripts/update_shared_runtime_lock.py

quality-ruff-gate:
	python -m ruff check . --statistics

quality-ruff-format-gate:
	python -m ruff format --check .

quality-import-boundary-gate:
	python scripts/import_boundary_gate.py

quality-bandit-gate:
	python -m bandit -r src -c pyproject.toml

quality-vulture-source-gate:
	python -m vulture src --exclude "*/tests/*" --min-confidence 80

quality-deptry-source-gate:
	python -m deptry src --extend-exclude "src/services/query_service/build" --extend-exclude ".*/tests/"

quality-maintainability-gate:
	python scripts/maintainability_gate.py src

quality-complexity-gate:
	python -m xenon --max-absolute E --max-modules C --max-average A src

quality-unit-collection-gate:
	python scripts/test_manifest.py --suite unit --collect-only --quiet

quality-integration-lite-collection-gate:
	python scripts/test_manifest.py --suite integration-lite --collect-only --quiet

quality-workflow-governance-gate:
	python -m pytest tests/unit/test_ci_workflow_action_versions.py -q

quality-openapi-spectral-gate:
	python scripts/openapi_spectral_gate.py --output-dir $(OPENAPI_ARTIFACT_DIR)

quality-wiki-docs-gate:
	python scripts/wiki_validation_guard.py
	python scripts/architecture_documentation_catalog_guard.py
	python scripts/supported_features_guard.py
	python scripts/incident_playbook_guard.py

docs-evidence-pack:
	python scripts/generate_documentation_evidence_pack.py

lint:
	python -m ruff check src/services/query_service/app src/services/query_control_plane_service/app/enterprise_readiness.py src/services/ingestion_service/app/main.py src/libs/portfolio-common/portfolio_common/enterprise_readiness.py src/libs/portfolio-common/portfolio_common/openapi_enrichment.py src/libs/portfolio-common/portfolio_common/reconstruction_identity.py src/libs/portfolio-common/portfolio_common/ingestion_evidence.py src/libs/portfolio-common/portfolio_common/reconciliation_quality.py src/libs/portfolio-common/portfolio_common/source_data_products.py src/libs/portfolio-common/portfolio_common/market_reference_quality.py src/libs/portfolio-common/portfolio_common/source_data_security.py src/libs/portfolio-common/portfolio_common/observability_contracts.py src/libs/portfolio-common/portfolio_common/event_supportability.py src/libs/portfolio-common/portfolio_common/events.py src/libs/portfolio-common/portfolio_common/outbox_repository.py tests/unit/services/query_service tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py tests/unit/libs/portfolio-common/test_openapi_enrichment.py tests/unit/libs/portfolio-common/test_reconstruction_identity.py tests/unit/libs/portfolio-common/test_ingestion_evidence.py tests/unit/libs/portfolio-common/test_reconciliation_quality.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_market_reference_quality.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/libs/portfolio-common/test_event_supportability.py tests/unit/libs/portfolio-common/test_outbox_repository.py tests/test_support tests/unit/test_support tests/unit/test_domain_data_product_contracts.py tests/unit/scripts/test_ingestion_rate_limit_scope_guard.py tests/unit/scripts/test_metric_vocabulary_guard.py tests/unit/scripts/test_structured_log_guard.py tests/unit/scripts/test_temporal_vocabulary_guard.py tests/unit/scripts/test_route_contract_family_guard.py tests/unit/scripts/test_qcp_problem_details_guard.py tests/unit/scripts/test_source_data_product_contract_guard.py tests/unit/scripts/test_analytics_input_consumer_contract_guard.py tests/unit/scripts/test_event_runtime_contract_guard.py tests/unit/scripts/test_rfc0083_closure_guard.py tests/unit/scripts/test_certify_lotus_core_app.py scripts/test_manifest.py scripts/coverage_gate.py scripts/openapi_quality_gate.py scripts/warning_budget_gate.py scripts/api_vocabulary_inventory.py scripts/no_alias_contract_guard.py scripts/ingestion_endpoint_contract_gate.py scripts/ingestion_rate_limit_scope_guard.py scripts/metric_vocabulary_guard.py scripts/structured_log_guard.py scripts/qcp_problem_details_guard.py scripts/temporal_vocabulary_guard.py scripts/route_contract_family_guard.py scripts/source_data_product_contract_guard.py scripts/validate_domain_data_product_contracts.py scripts/analytics_input_consumer_contract_guard.py scripts/event_runtime_contract_guard.py scripts/rfc0083_closure_guard.py scripts/certify_lotus_core_app.py --ignore E501,I001
	python -m ruff check scripts/ingestion_gateway_rate_limit_policy_guard.py tests/unit/scripts/test_ingestion_gateway_rate_limit_policy_guard.py --ignore E501,I001
	python -m ruff check scripts/repository_output_shape_guard.py tests/unit/scripts/test_repository_output_shape_guard.py --ignore E501,I001
	python -m ruff check scripts/security_control_coverage_guard.py tests/unit/scripts/test_security_control_coverage_guard.py --ignore E501,I001
	python -m ruff check scripts/clean_generated_artifacts.py tests/unit/scripts/test_clean_generated_artifacts.py --ignore E501,I001
	python -m ruff check scripts/endpoint_consolidation_watchlist_guard.py tests/unit/scripts/test_endpoint_consolidation_watchlist_guard.py --ignore E501,I001
	python -m ruff check src/libs/portfolio-common/portfolio_common/proof_builders.py scripts/proof_builder_pattern_guard.py tests/unit/libs/portfolio-common/test_proof_builders.py tests/unit/scripts/test_proof_builder_pattern_guard.py --ignore E501,I001
	python -m ruff check src/services/query_service/app/routers/http_errors.py src/services/query_service/app/routers/lookup_mappers.py src/services/query_service/app/routers/lookups.py src/services/query_service/app/routers/buy_state.py src/services/query_service/app/routers/cash_accounts.py src/services/query_service/app/routers/cash_movements.py src/services/query_service/app/routers/portfolios.py src/services/query_service/app/routers/positions.py src/services/query_service/app/routers/reporting.py src/services/query_service/app/routers/sell_state.py src/services/query_service/app/routers/transactions.py src/services/financial_reconciliation_service/app/routers/reconciliation_mappers.py src/services/financial_reconciliation_service/app/routers/reconciliation.py src/services/event_replay_service/app/routers/replay_mappers.py src/services/event_replay_service/app/routers/ingestion_operations.py scripts/api_mapper_pattern_guard.py tests/unit/services/query_service/routers/test_lookups_router.py tests/unit/services/query_service/routers/test_http_errors.py tests/unit/services/query_service/routers/test_cash_movements_router.py tests/unit/services/financial_reconciliation_service/test_reconciliation_mappers.py tests/unit/services/event_replay_service/test_replay_mappers.py tests/unit/scripts/test_api_mapper_pattern_guard.py --ignore E501,I001
	python -m ruff check scripts/mapping_anti_corruption_guard.py tests/unit/scripts/test_mapping_anti_corruption_guard.py --ignore E501,I001
	python -m ruff check src/libs/portfolio-common/portfolio_common/runtime_providers.py src/services/financial_reconciliation_service/app/services/runtime_providers.py src/services/financial_reconciliation_service/app/services/reconciliation_service.py src/services/query_service/app/services/core_snapshot_service.py src/services/query_service/app/services/simulation_service.py scripts/runtime_provider_port_guard.py tests/unit/libs/portfolio-common/test_runtime_providers.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py tests/unit/services/query_service/services/test_core_snapshot_service.py tests/unit/services/query_service/services/test_simulation_service.py tests/unit/scripts/test_runtime_provider_port_guard.py --ignore E501,I001
	python -m ruff check src/libs/portfolio-common/portfolio_common/build_metadata.py src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py tests/unit/libs/portfolio-common/test_build_metadata.py tests/unit/libs/portfolio-common/test_http_app_bootstrap.py tests/test_support/http_middleware_contract.py tests/unit/test_http_middleware_chain_contract.py --ignore E501,I001
	python -m ruff check scripts/image_provenance_guard.py tests/unit/scripts/test_image_provenance_guard.py --ignore E501,I001
	python -m ruff check scripts/write_image_release_manifest.py tests/unit/scripts/test_write_image_release_manifest.py --ignore E501,I001
	python -m ruff check scripts/architecture_documentation_catalog_guard.py tests/unit/scripts/test_architecture_documentation_catalog_guard.py --ignore E501,I001
	python -m ruff check scripts/supported_features_guard.py tests/unit/scripts/test_supported_features_guard.py --ignore E501,I001
	python -m ruff check scripts/incident_playbook_guard.py tests/unit/scripts/test_incident_playbook_guard.py --ignore E501,I001
	python -m ruff check src/services/pipeline_orchestrator_service/app/adapters/__init__.py src/services/pipeline_orchestrator_service/app/adapters/outbox_event_mapper.py src/services/pipeline_orchestrator_service/app/services/pipeline_orchestrator_service.py tests/unit/services/pipeline_orchestrator_service/adapters/test_outbox_event_mapper.py tests/unit/services/pipeline_orchestrator_service/services/test_pipeline_orchestrator_service.py --ignore E501,I001
	python -m ruff check scripts/docker_endpoint_smoke.py scripts/latency_profile.py scripts/performance_load_gate.py scripts/config_access_guard.py --ignore E501,I001
	python -m ruff format --check src/services/query_service/app/main.py src/services/query_control_plane_service/app/enterprise_readiness.py src/services/ingestion_service/app/main.py src/libs/portfolio-common/portfolio_common/enterprise_readiness.py src/libs/portfolio-common/portfolio_common/openapi_enrichment.py src/libs/portfolio-common/portfolio_common/reconstruction_identity.py src/libs/portfolio-common/portfolio_common/ingestion_evidence.py src/libs/portfolio-common/portfolio_common/reconciliation_quality.py src/libs/portfolio-common/portfolio_common/source_data_products.py src/libs/portfolio-common/portfolio_common/market_reference_quality.py src/libs/portfolio-common/portfolio_common/source_data_security.py src/libs/portfolio-common/portfolio_common/observability_contracts.py src/libs/portfolio-common/portfolio_common/event_supportability.py src/libs/portfolio-common/portfolio_common/events.py src/libs/portfolio-common/portfolio_common/outbox_repository.py tests/unit/services/query_service/test_openapi_quality_gate.py tests/unit/services/query_service/test_api_vocabulary_inventory.py tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py tests/unit/libs/portfolio-common/test_openapi_enrichment.py tests/unit/libs/portfolio-common/test_reconstruction_identity.py tests/unit/libs/portfolio-common/test_ingestion_evidence.py tests/unit/libs/portfolio-common/test_reconciliation_quality.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_market_reference_quality.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/libs/portfolio-common/test_event_supportability.py tests/unit/libs/portfolio-common/test_outbox_repository.py tests/unit/test_domain_data_product_contracts.py tests/unit/scripts/test_ingestion_rate_limit_scope_guard.py tests/unit/scripts/test_metric_vocabulary_guard.py tests/unit/scripts/test_structured_log_guard.py tests/unit/scripts/test_temporal_vocabulary_guard.py tests/unit/scripts/test_route_contract_family_guard.py tests/unit/scripts/test_qcp_problem_details_guard.py tests/unit/scripts/test_source_data_product_contract_guard.py tests/unit/scripts/test_analytics_input_consumer_contract_guard.py tests/unit/scripts/test_event_runtime_contract_guard.py tests/unit/scripts/test_rfc0083_closure_guard.py tests/unit/scripts/test_certify_lotus_core_app.py scripts/test_manifest.py scripts/coverage_gate.py scripts/openapi_quality_gate.py scripts/warning_budget_gate.py scripts/api_vocabulary_inventory.py scripts/no_alias_contract_guard.py scripts/docker_endpoint_smoke.py scripts/latency_profile.py scripts/performance_load_gate.py scripts/ingestion_endpoint_contract_gate.py scripts/ingestion_rate_limit_scope_guard.py scripts/metric_vocabulary_guard.py scripts/structured_log_guard.py scripts/config_access_guard.py scripts/qcp_problem_details_guard.py scripts/temporal_vocabulary_guard.py scripts/route_contract_family_guard.py scripts/source_data_product_contract_guard.py scripts/validate_domain_data_product_contracts.py scripts/analytics_input_consumer_contract_guard.py scripts/event_runtime_contract_guard.py scripts/rfc0083_closure_guard.py scripts/certify_lotus_core_app.py
	python -m ruff format --check scripts/ingestion_gateway_rate_limit_policy_guard.py tests/unit/scripts/test_ingestion_gateway_rate_limit_policy_guard.py
	python -m ruff format --check scripts/repository_output_shape_guard.py tests/unit/scripts/test_repository_output_shape_guard.py
	python -m ruff format --check scripts/security_control_coverage_guard.py tests/unit/scripts/test_security_control_coverage_guard.py
	python -m ruff format --check scripts/clean_generated_artifacts.py tests/unit/scripts/test_clean_generated_artifacts.py
	python -m ruff format --check scripts/endpoint_consolidation_watchlist_guard.py tests/unit/scripts/test_endpoint_consolidation_watchlist_guard.py
	python -m ruff format --check src/libs/portfolio-common/portfolio_common/proof_builders.py scripts/proof_builder_pattern_guard.py tests/unit/libs/portfolio-common/test_proof_builders.py tests/unit/scripts/test_proof_builder_pattern_guard.py
	python -m ruff format --check src/services/query_service/app/routers/http_errors.py src/services/query_service/app/routers/lookup_mappers.py src/services/query_service/app/routers/lookups.py src/services/query_service/app/routers/buy_state.py src/services/query_service/app/routers/cash_accounts.py src/services/query_service/app/routers/cash_movements.py src/services/query_service/app/routers/portfolios.py src/services/query_service/app/routers/positions.py src/services/query_service/app/routers/reporting.py src/services/query_service/app/routers/sell_state.py src/services/query_service/app/routers/transactions.py src/services/financial_reconciliation_service/app/routers/reconciliation_mappers.py src/services/financial_reconciliation_service/app/routers/reconciliation.py src/services/event_replay_service/app/routers/replay_mappers.py src/services/event_replay_service/app/routers/ingestion_operations.py scripts/api_mapper_pattern_guard.py tests/unit/services/query_service/routers/test_lookups_router.py tests/unit/services/query_service/routers/test_http_errors.py tests/unit/services/query_service/routers/test_cash_movements_router.py tests/unit/services/financial_reconciliation_service/test_reconciliation_mappers.py tests/unit/services/event_replay_service/test_replay_mappers.py tests/unit/scripts/test_api_mapper_pattern_guard.py
	python -m ruff format --check scripts/mapping_anti_corruption_guard.py tests/unit/scripts/test_mapping_anti_corruption_guard.py
	python -m ruff format --check src/libs/portfolio-common/portfolio_common/runtime_providers.py src/services/financial_reconciliation_service/app/services/runtime_providers.py src/services/financial_reconciliation_service/app/services/reconciliation_service.py src/services/query_service/app/services/core_snapshot_service.py src/services/query_service/app/services/simulation_service.py scripts/runtime_provider_port_guard.py tests/unit/libs/portfolio-common/test_runtime_providers.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py tests/unit/services/query_service/services/test_core_snapshot_service.py tests/unit/services/query_service/services/test_simulation_service.py tests/unit/scripts/test_runtime_provider_port_guard.py
	python -m ruff format --check src/libs/portfolio-common/portfolio_common/build_metadata.py src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py tests/unit/libs/portfolio-common/test_build_metadata.py tests/unit/libs/portfolio-common/test_http_app_bootstrap.py tests/test_support/http_middleware_contract.py tests/unit/test_http_middleware_chain_contract.py
	python -m ruff format --check scripts/image_provenance_guard.py tests/unit/scripts/test_image_provenance_guard.py
	python -m ruff format --check scripts/write_image_release_manifest.py tests/unit/scripts/test_write_image_release_manifest.py
	python -m ruff format --check scripts/architecture_documentation_catalog_guard.py tests/unit/scripts/test_architecture_documentation_catalog_guard.py
	python -m ruff format --check scripts/supported_features_guard.py tests/unit/scripts/test_supported_features_guard.py
	python -m ruff format --check scripts/incident_playbook_guard.py tests/unit/scripts/test_incident_playbook_guard.py
	python -m ruff format --check src/services/pipeline_orchestrator_service/app/adapters/__init__.py src/services/pipeline_orchestrator_service/app/adapters/outbox_event_mapper.py src/services/pipeline_orchestrator_service/app/services/pipeline_orchestrator_service.py tests/unit/services/pipeline_orchestrator_service/adapters/test_outbox_event_mapper.py tests/unit/services/pipeline_orchestrator_service/services/test_pipeline_orchestrator_service.py
	$(MAKE) monetary-float-guard
	$(MAKE) ingestion-contract-gate
	$(MAKE) ingestion-rate-limit-scope-guard
	$(MAKE) ingestion-gateway-rate-limit-policy-guard
	$(MAKE) config-access-guard
	$(MAKE) metric-vocabulary-guard
	$(MAKE) repository-output-shape-guard
	$(MAKE) security-control-coverage-guard
	$(MAKE) structured-log-guard
	$(MAKE) qcp-problem-details-guard
	$(MAKE) temporal-vocabulary-guard
	$(MAKE) route-contract-family-guard
	$(MAKE) source-data-product-contract-guard
	$(MAKE) endpoint-consolidation-watchlist-guard
	$(MAKE) analytics-input-consumer-contract-guard
	$(MAKE) event-runtime-contract-guard
	$(MAKE) rfc0083-closure-guard

monetary-float-guard:
	python scripts/check_monetary_float_usage.py

qcp-problem-details-guard:
	python scripts/qcp_problem_details_guard.py

metric-vocabulary-guard:
	python scripts/metric_vocabulary_guard.py

repository-output-shape-guard:
	python scripts/repository_output_shape_guard.py

domain-layer-guard:
	python scripts/domain_layer_guard.py

testability-architecture-guard:
	python scripts/testability_architecture_guard.py

runtime-boundary-decision-guard:
	python scripts/runtime_boundary_decision_guard.py

in-process-modularity-guard:
	python scripts/in_process_modularity_guard.py

in-process-boundary-guard:
	python scripts/in_process_boundary_guard.py

proof-builder-pattern-guard:
	python scripts/proof_builder_pattern_guard.py

api-mapper-pattern-guard:
	python scripts/api_mapper_pattern_guard.py

api-example-catalog-guard:
	python scripts/api_example_catalog_guard.py

architecture-docs-catalog-guard:
	python scripts/architecture_documentation_catalog_guard.py

image-provenance-guard:
	python scripts/image_provenance_guard.py

mapping-anti-corruption-guard:
	python scripts/mapping_anti_corruption_guard.py

runtime-provider-port-guard:
	python scripts/runtime_provider_port_guard.py

application-layer-contract-guard:
	python scripts/application_layer_contract_guard.py

application-port-catalog-guard:
	python scripts/application_port_catalog_guard.py

application-dependency-inversion-guard:
	python scripts/application_dependency_inversion_guard.py

application-workflow-policy-guard:
	python scripts/application_workflow_policy_guard.py

application-error-taxonomy-guard:
	python scripts/application_error_taxonomy_guard.py

application-command-result-guard:
	python scripts/application_command_result_guard.py

ingestion-service-framework-guard:
	python scripts/ingestion_service_framework_guard.py

upload-component-boundary-guard:
	python scripts/upload_component_boundary_guard.py

transaction-replay-boundary-guard:
	python scripts/transaction_replay_boundary_guard.py

aggregation-scheduler-boundary-guard:
	python scripts/aggregation_scheduler_boundary_guard.py

position-reducer-boundary-guard:
	python scripts/position_reducer_boundary_guard.py

infrastructure-adapter-layer-guard:
	python scripts/infrastructure_adapter_layer_guard.py

repository-transaction-boundary-guard:
	python scripts/repository_transaction_boundary_guard.py

ingestion-store-port-guard:
	python scripts/ingestion_store_port_guard.py

event-publisher-port-guard:
	python scripts/event_publisher_port_guard.py

repository-port-guard:
	python scripts/repository_port_guard.py

security-control-coverage-guard:
	python scripts/security_control_coverage_guard.py

supported-features-guard:
	python scripts/supported_features_guard.py

incident-playbook-guard:
	python scripts/incident_playbook_guard.py

structured-log-guard:
	python scripts/structured_log_guard.py

no-alias-gate:
	python scripts/no_alias_contract_guard.py

ingestion-contract-gate:
	python scripts/ingestion_endpoint_contract_gate.py

ingestion-rate-limit-scope-guard:
	python scripts/ingestion_rate_limit_scope_guard.py

ingestion-gateway-rate-limit-policy-guard:
	python scripts/ingestion_gateway_rate_limit_policy_guard.py

config-access-guard:
	python scripts/config_access_guard.py

temporal-vocabulary-guard:
	python scripts/temporal_vocabulary_guard.py

route-contract-family-guard:
	python scripts/route_contract_family_guard.py

source-data-product-contract-guard:
	python scripts/source_data_product_contract_guard.py

endpoint-consolidation-watchlist-guard:
	python scripts/endpoint_consolidation_watchlist_guard.py

domain-product-validate:
	python scripts/validate_domain_data_product_contracts.py

analytics-input-consumer-contract-guard:
	python scripts/analytics_input_consumer_contract_guard.py

event-runtime-contract-guard:
	python scripts/event_runtime_contract_guard.py

rfc0083-closure-guard:
	python scripts/rfc0083_closure_guard.py

typecheck:
	python -m mypy --config-file mypy.ini

architecture-guard:
	python scripts/architecture_boundary_guard.py --strict
	$(MAKE) domain-layer-guard
	$(MAKE) testability-architecture-guard
	$(MAKE) runtime-boundary-decision-guard
	$(MAKE) in-process-modularity-guard
	$(MAKE) in-process-boundary-guard
	$(MAKE) proof-builder-pattern-guard
	$(MAKE) api-mapper-pattern-guard
	$(MAKE) api-example-catalog-guard
	$(MAKE) architecture-docs-catalog-guard
	$(MAKE) supported-features-guard
	$(MAKE) image-provenance-guard
	$(MAKE) mapping-anti-corruption-guard
	$(MAKE) runtime-provider-port-guard
	$(MAKE) application-layer-contract-guard
	$(MAKE) application-port-catalog-guard
	$(MAKE) application-dependency-inversion-guard
	$(MAKE) application-workflow-policy-guard
	$(MAKE) application-error-taxonomy-guard
	$(MAKE) application-command-result-guard
	$(MAKE) ingestion-service-framework-guard
	$(MAKE) upload-component-boundary-guard
	$(MAKE) transaction-replay-boundary-guard
	$(MAKE) aggregation-scheduler-boundary-guard
	$(MAKE) position-reducer-boundary-guard
	$(MAKE) infrastructure-adapter-layer-guard
	$(MAKE) repository-transaction-boundary-guard
	$(MAKE) ingestion-store-port-guard
	$(MAKE) event-publisher-port-guard
	$(MAKE) repository-port-guard

openapi-gate:
	python scripts/openapi_quality_gate.py

api-vocabulary-gate:
	python scripts/api_vocabulary_inventory.py --validate-only

live-dpm-source-validate:
	python scripts/validate_live_dpm_source_products.py --control-base-url $${LOTUS_CORE_CONTROL_BASE_URL:-http://core-control.dev.lotus}

lotus-core-validate:
	python scripts/certify_lotus_core_app.py --runtime-build

migration-smoke:
	python scripts/migration_contract_check.py --mode alembic-sql

migration-apply:
	python -m alembic upgrade head

test:
	$(MAKE) test-unit

test-fast:
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) warning-gate
	$(MAKE) test-unit

test-medium:
	$(MAKE) test-unit-db
	$(MAKE) test-integration-lite
	$(MAKE) test-ops-contract
	$(MAKE) test-boundary-mapping-conformance
	$(MAKE) test-transaction-buy-contract
	$(MAKE) test-transaction-sell-contract
	$(MAKE) test-transaction-dividend-contract
	$(MAKE) test-transaction-interest-contract
	$(MAKE) test-transaction-fx-contract
	$(MAKE) test-transaction-portfolio-flow-bundle-contract

test-heavy:
	$(MAKE) test-e2e-smoke
	$(MAKE) test-docker-smoke
	$(MAKE) test-latency-gate
	$(MAKE) test-performance-load-gate
	$(MAKE) test-performance-load-gate-full
	$(MAKE) test-failure-recovery-gate

test-unit:
	python scripts/test_manifest.py --suite unit --quiet

warning-gate:
	python scripts/warning_budget_gate.py --suite unit --max-warnings 0 --quiet

test-unit-db:
	python scripts/test_manifest.py --suite unit-db --quiet

test-integration-lite:
	python scripts/test_manifest.py --suite integration-lite --quiet

test-integration-all:
	python scripts/test_manifest.py --suite integration-all --quiet

test-ops-contract:
	python scripts/test_manifest.py --suite ops-contract --quiet

test-boundary-mapping-conformance:
	python scripts/test_manifest.py --suite boundary-mapping-conformance --quiet

test-transaction-buy-contract:
	python scripts/test_manifest.py --suite transaction-buy-contract --quiet

test-transaction-sell-contract:
	python scripts/test_manifest.py --suite transaction-sell-contract --quiet

test-transaction-dividend-contract:
	python scripts/test_manifest.py --suite transaction-dividend-contract --quiet

test-transaction-interest-contract:
	python scripts/test_manifest.py --suite transaction-interest-contract --quiet

test-transaction-fx-contract:
	python scripts/test_manifest.py --suite transaction-fx-contract --quiet

test-transaction-portfolio-flow-bundle-contract:
	python scripts/test_manifest.py --suite transaction-portfolio-flow-bundle-contract --quiet

test-e2e-smoke:
	python scripts/test_manifest.py --suite e2e-smoke --quiet

test-e2e-all:
	python scripts/test_manifest.py --suite e2e-all --quiet

test-docker-smoke:
	python scripts/docker_endpoint_smoke.py --build

test-latency-gate:
	python scripts/latency_profile.py --build --enforce --seed-completion-timeout-seconds $(LATENCY_SEED_COMPLETION_TIMEOUT_SECONDS)

test-performance-load-gate:
	python scripts/performance_load_gate.py --build --profile-tier fast --enforce

test-performance-load-gate-full:
	python scripts/performance_load_gate.py --build --profile-tier full --enforce

test-failure-recovery-gate:
	python scripts/failure_recovery_gate.py --build --enforce

test-institutional-completion-gate:
	python scripts/institutional_completion_gate.py

test-institutional-signoff-pack:
	python scripts/institutional_signoff_pack.py --require-all --max-age-hours 24

test-pr-suites:
	$(MAKE) test-unit-db
	$(MAKE) test-integration-lite
	$(MAKE) test-ops-contract
	$(MAKE) test-boundary-mapping-conformance
	$(MAKE) test-transaction-buy-contract
	$(MAKE) test-transaction-sell-contract
	$(MAKE) test-transaction-dividend-contract
	$(MAKE) test-transaction-interest-contract
	$(MAKE) test-transaction-fx-contract
	$(MAKE) test-transaction-portfolio-flow-bundle-contract

test-pr-runtime-gates:
	$(MAKE) docker-build
	$(MAKE) test-e2e-smoke
	$(MAKE) test-docker-smoke
	$(MAKE) test-latency-gate
	$(MAKE) test-performance-load-gate

test-release-gates:
	$(MAKE) test-integration-all
	$(MAKE) test-e2e-all
	$(MAKE) test-performance-load-gate-full
	$(MAKE) test-failure-recovery-gate

test-institutional-release-gates:
	$(MAKE) test-institutional-completion-gate
	$(MAKE) test-institutional-signoff-pack

security-audit:
	python scripts/dependency_health_check.py

check: lint no-alias-gate typecheck architecture-guard openapi-gate api-vocabulary-gate warning-gate test

coverage-gate:
	python scripts/coverage_gate.py

ci: verify-dependencies lint no-alias-gate typecheck architecture-guard openapi-gate api-vocabulary-gate warning-gate migration-smoke test-pr-suites coverage-gate security-audit test-pr-runtime-gates

ci-main: ci test-release-gates

ci-local: verify-dependencies lint no-alias-gate typecheck architecture-guard openapi-gate api-vocabulary-gate warning-gate test-unit-db test-integration-lite coverage-gate

docker-build:
	docker build -f src/services/query_service/Dockerfile -t portfolio-analytics-query-service:ci .

docker-prebuild-ci:
	python scripts/prebuild_ci_images.py

clean:
	python scripts/clean_generated_artifacts.py
