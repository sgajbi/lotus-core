.PHONY: install install-ci verify-dependencies verify-dependencies-clean compile-runtime-lock quality-ruff-gate quality-ruff-format-gate quality-import-boundary-gate quality-bandit-gate quality-vulture-source-gate quality-deptry-source-gate quality-maintainability-gate quality-complexity-gate quality-unit-collection-gate quality-integration-lite-collection-gate quality-workflow-governance-gate quality-openapi-spectral-gate quality-wiki-docs-gate docs-evidence-pack lint typecheck architecture-guard monetary-float-guard structured-log-guard qcp-problem-details-guard metric-vocabulary-guard repository-output-shape-guard security-control-coverage-guard critical-path-coverage-guard risk-based-test-coverage-matrix-guard synthetic-fixture-leakage-guard test-lane-governance-guard event-contract-test-pack-guard concurrency-duplicate-delivery-guard cross-product-golden-regression-guard command-api-behavior-certification-guard observability-contract-test-pack-guard supported-features-guard transaction-capability-catalog-guard incident-playbook-guard front-door-sync-guard domain-layer-guard testability-architecture-guard runtime-boundary-decision-guard in-process-modularity-guard in-process-boundary-guard proof-builder-pattern-guard api-mapper-pattern-guard api-example-catalog-guard api-route-catalog-guard architecture-docs-catalog-guard rfc-status-ledger-guard image-provenance-guard mapping-anti-corruption-guard runtime-provider-port-guard application-layer-contract-guard application-port-catalog-guard application-dependency-inversion-guard application-workflow-policy-guard application-error-taxonomy-guard application-command-result-guard ingestion-service-framework-guard upload-component-boundary-guard transaction-replay-boundary-guard aggregation-scheduler-boundary-guard position-reducer-boundary-guard infrastructure-adapter-layer-guard repository-transaction-boundary-guard ingestion-store-port-guard event-publisher-port-guard repository-port-guard ingestion-contract-gate ingestion-rate-limit-scope-guard config-access-guard temporal-vocabulary-guard route-contract-family-guard source-data-product-contract-guard endpoint-consolidation-watchlist-guard domain-product-validate analytics-input-consumer-contract-guard event-runtime-contract-guard rfc0083-closure-guard no-alias-gate openapi-gate api-vocabulary-gate warning-gate migration-smoke migration-apply audit-average-cost-pools reconcile-average-cost-pools test test-fast test-medium test-heavy test-unit test-unit-db test-integration-lite test-integration-all test-ops-contract test-boundary-mapping-conformance test-transaction-buy-contract test-transaction-sell-contract test-transaction-dividend-contract test-transaction-interest-contract test-transaction-fx-contract test-transaction-portfolio-flow-bundle-contract test-transaction-processing-contract test-e2e-smoke test-e2e-all test-docker-smoke test-latency-gate test-performance-load-gate test-performance-load-gate-full profile-cost-history-capacity profile-cost-processing-modes test-failure-recovery-gate test-derived-state-recovery-gate test-derived-state-poison-gate test-derived-state-workload-smoke profile-derived-state-daily profile-derived-state-fan-in profile-derived-state-price-burst test-institutional-completion-gate test-institutional-signoff-pack lotus-core-validate test-pr-suites test-pr-runtime-gates test-release-gates security-audit check coverage-gate ci ci-main ci-local docker-build docker-prebuild-ci live-dpm-source-validate clean
.PHONY: profile-derived-state-price-restatement profile-derived-state-fx-restatement
.PHONY: ingestion-gateway-rate-limit-policy-guard generated-artifact-tracking-guard

LATENCY_SEED_COMPLETION_TIMEOUT_SECONDS ?= 900
OPENAPI_ARTIFACT_DIR ?= output/openapi
RUNTIME_BUILD_ARGUMENT = $(if $(filter true,$(LOTUS_RUNTIME_IMAGE_SET_VERIFIED)),,--build)
CERTIFICATION_RUNTIME_BUILD_ARGUMENT = $(if $(filter true,$(LOTUS_RUNTIME_IMAGE_SET_VERIFIED)),,--runtime-build)

install:
	python scripts/development/bootstrap_dev.py

install-ci:
	python scripts/development/bootstrap_dev.py

verify-dependencies:
	python scripts/validation/dependency_health_check.py --skip-audit

verify-dependencies-clean:
	python scripts/validation/dependency_health_check.py --skip-audit --no-cache --report output/dependency-health/clean-install-report.json

compile-runtime-lock:
	python scripts/development/update_shared_runtime_lock.py

quality-ruff-gate:
	python -m ruff check . --statistics

quality-ruff-format-gate:
	python -m ruff format --check .

quality-import-boundary-gate:
	python scripts/quality/import_boundary_gate.py

quality-bandit-gate:
	python -m bandit -r src -c pyproject.toml

quality-vulture-source-gate:
	python -m vulture src --exclude "*/tests/*" --min-confidence 80

quality-deptry-source-gate:
	python -m deptry src --extend-exclude "src/services/query_service/build" --extend-exclude ".*/tests/"

quality-maintainability-gate:
	python scripts/quality/maintainability_gate.py src

quality-complexity-gate:
	python -m xenon --max-absolute E --max-modules C --max-average A src

quality-unit-collection-gate:
	python scripts/quality/test_manifest.py --suite unit --collect-only --quiet

quality-integration-lite-collection-gate:
	python scripts/quality/test_manifest.py --suite integration-lite --collect-only --quiet

quality-workflow-governance-gate:
	python -m pytest tests/unit/test_ci_workflow_action_versions.py -q

quality-openapi-spectral-gate:
	python scripts/quality/openapi_spectral_gate.py --output-dir $(OPENAPI_ARTIFACT_DIR)

quality-wiki-docs-gate:
	python scripts/quality/wiki_validation_guard.py
	python scripts/quality/front_door_sync_guard.py
	python scripts/quality/architecture_documentation_catalog_guard.py
	python scripts/quality/rfc_status_ledger_guard.py
	python scripts/quality/supported_features_guard.py
	python scripts/quality/incident_playbook_guard.py

docs-evidence-pack:
	python scripts/generators/generate_documentation_evidence_pack.py

lint: quality-ruff-gate quality-ruff-format-gate
	$(MAKE) monetary-float-guard
	$(MAKE) ingestion-contract-gate
	$(MAKE) ingestion-rate-limit-scope-guard
	$(MAKE) ingestion-gateway-rate-limit-policy-guard
	$(MAKE) config-access-guard
	$(MAKE) metric-vocabulary-guard
	$(MAKE) repository-output-shape-guard
	$(MAKE) security-control-coverage-guard
	$(MAKE) critical-path-coverage-guard
	$(MAKE) synthetic-fixture-leakage-guard
	$(MAKE) test-lane-governance-guard
	$(MAKE) concurrency-duplicate-delivery-guard
	$(MAKE) cross-product-golden-regression-guard
	$(MAKE) command-api-behavior-certification-guard
	$(MAKE) observability-contract-test-pack-guard
	$(MAKE) generated-artifact-tracking-guard
	$(MAKE) structured-log-guard
	$(MAKE) qcp-problem-details-guard
	$(MAKE) temporal-vocabulary-guard
	$(MAKE) route-contract-family-guard
	$(MAKE) source-data-product-contract-guard
	$(MAKE) endpoint-consolidation-watchlist-guard
	$(MAKE) analytics-input-consumer-contract-guard
	$(MAKE) event-runtime-contract-guard
	$(MAKE) event-contract-test-pack-guard
	$(MAKE) rfc0083-closure-guard

monetary-float-guard:
	python scripts/quality/check_monetary_float_usage.py

qcp-problem-details-guard:
	python scripts/quality/qcp_problem_details_guard.py

metric-vocabulary-guard:
	python scripts/quality/metric_vocabulary_guard.py

repository-output-shape-guard:
	python scripts/quality/repository_output_shape_guard.py

domain-layer-guard:
	python scripts/quality/domain_layer_guard.py

testability-architecture-guard:
	python scripts/quality/testability_architecture_guard.py

runtime-boundary-decision-guard:
	python scripts/quality/runtime_boundary_decision_guard.py

in-process-modularity-guard:
	python scripts/quality/in_process_modularity_guard.py

in-process-boundary-guard:
	python scripts/quality/in_process_boundary_guard.py

proof-builder-pattern-guard:
	python scripts/quality/proof_builder_pattern_guard.py

api-mapper-pattern-guard:
	python scripts/quality/api_mapper_pattern_guard.py

api-example-catalog-guard:
	python scripts/quality/api_example_catalog_guard.py

api-route-catalog-guard:
	python scripts/generators/generate_api_route_catalog.py --check

architecture-docs-catalog-guard:
	python scripts/quality/architecture_documentation_catalog_guard.py

rfc-status-ledger-guard:
	python scripts/quality/rfc_status_ledger_guard.py

image-provenance-guard:
	python scripts/quality/image_provenance_guard.py

mapping-anti-corruption-guard:
	python scripts/quality/mapping_anti_corruption_guard.py

runtime-provider-port-guard:
	python scripts/quality/runtime_provider_port_guard.py

application-layer-contract-guard:
	python scripts/quality/application_layer_contract_guard.py

application-port-catalog-guard:
	python scripts/quality/application_port_catalog_guard.py

application-dependency-inversion-guard:
	python scripts/quality/application_dependency_inversion_guard.py

application-workflow-policy-guard:
	python scripts/quality/application_workflow_policy_guard.py

application-error-taxonomy-guard:
	python scripts/quality/application_error_taxonomy_guard.py

application-command-result-guard:
	python scripts/quality/application_command_result_guard.py

ingestion-service-framework-guard:
	python scripts/quality/ingestion_service_framework_guard.py

upload-component-boundary-guard:
	python scripts/quality/upload_component_boundary_guard.py

transaction-replay-boundary-guard:
	python scripts/quality/transaction_replay_boundary_guard.py

aggregation-scheduler-boundary-guard:
	python scripts/quality/aggregation_scheduler_boundary_guard.py

position-reducer-boundary-guard:
	python scripts/quality/position_reducer_boundary_guard.py

infrastructure-adapter-layer-guard:
	python scripts/quality/infrastructure_adapter_layer_guard.py

repository-transaction-boundary-guard:
	python scripts/quality/repository_transaction_boundary_guard.py

ingestion-store-port-guard:
	python scripts/quality/ingestion_store_port_guard.py

event-publisher-port-guard:
	python scripts/quality/event_publisher_port_guard.py

repository-port-guard:
	python scripts/quality/repository_port_guard.py

security-control-coverage-guard:
	python scripts/quality/security_control_coverage_guard.py

critical-path-coverage-guard:
	python scripts/quality/critical_path_coverage_guard.py --contract-only

risk-based-test-coverage-matrix-guard:
	python scripts/quality/risk_based_test_coverage_matrix_guard.py

synthetic-fixture-leakage-guard:
	python scripts/quality/synthetic_fixture_leakage_guard.py

test-lane-governance-guard:
	python scripts/quality/test_lane_governance_guard.py

event-contract-test-pack-guard:
	python scripts/quality/event_contract_test_pack_guard.py

concurrency-duplicate-delivery-guard:
	python scripts/quality/concurrency_duplicate_delivery_guard.py

cross-product-golden-regression-guard:
	python scripts/quality/cross_product_golden_regression_guard.py

command-api-behavior-certification-guard:
	python scripts/quality/command_api_behavior_certification_guard.py

observability-contract-test-pack-guard:
	python scripts/quality/observability_contract_test_pack_guard.py

generated-artifact-tracking-guard:
	python scripts/quality/generated_artifact_tracking_guard.py

supported-features-guard:
	python scripts/quality/supported_features_guard.py

transaction-capability-catalog-guard:
	python scripts/transaction_processing/validate_capability_catalog.py

incident-playbook-guard:
	python scripts/quality/incident_playbook_guard.py

front-door-sync-guard:
	python scripts/quality/front_door_sync_guard.py

structured-log-guard:
	python scripts/quality/structured_log_guard.py

no-alias-gate:
	python scripts/quality/no_alias_contract_guard.py

ingestion-contract-gate:
	python scripts/quality/ingestion_endpoint_contract_gate.py

ingestion-rate-limit-scope-guard:
	python scripts/quality/ingestion_rate_limit_scope_guard.py

ingestion-gateway-rate-limit-policy-guard:
	python scripts/quality/ingestion_gateway_rate_limit_policy_guard.py

config-access-guard:
	python scripts/quality/config_access_guard.py

temporal-vocabulary-guard:
	python scripts/quality/temporal_vocabulary_guard.py

route-contract-family-guard:
	python scripts/quality/route_contract_family_guard.py

source-data-product-contract-guard:
	python scripts/quality/source_data_product_contract_guard.py

endpoint-consolidation-watchlist-guard:
	python scripts/quality/endpoint_consolidation_watchlist_guard.py

domain-product-validate:
	python scripts/validation/validate_domain_data_product_contracts.py

analytics-input-consumer-contract-guard:
	python scripts/quality/analytics_input_consumer_contract_guard.py

event-runtime-contract-guard:
	python scripts/quality/event_runtime_contract_guard.py

rfc0083-closure-guard:
	python scripts/quality/rfc0083_closure_guard.py

typecheck:
	python -m mypy --config-file mypy.ini

architecture-guard:
	python scripts/quality/architecture_boundary_guard.py --strict
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
	$(MAKE) transaction-capability-catalog-guard
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
	python scripts/quality/openapi_quality_gate.py

api-vocabulary-gate:
	python scripts/quality/api_vocabulary_inventory.py --validate-only
	python scripts/generators/generate_api_route_catalog.py --check

live-dpm-source-validate:
	python scripts/validation/validate_live_dpm_source_products.py --control-base-url $${LOTUS_CORE_CONTROL_BASE_URL:-http://core-control.dev.lotus}

lotus-core-validate:
	python scripts/validation/certify_lotus_core_app.py $(CERTIFICATION_RUNTIME_BUILD_ARGUMENT)

migration-smoke:
	python scripts/quality/migration_contract_check.py --mode alembic-sql

migration-apply:
	python -m alembic upgrade head

audit-average-cost-pools:
	python scripts/operations/reconcile_average_cost_pools.py $(AVCO_RECONCILIATION_ARGS)

reconcile-average-cost-pools:
	python scripts/operations/reconcile_average_cost_pools.py --apply $(AVCO_RECONCILIATION_ARGS)

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
	python scripts/quality/test_manifest.py --suite unit --quiet

warning-gate:
	python scripts/quality/warning_budget_gate.py --suite unit --max-warnings 0 --quiet

test-unit-db:
	python scripts/quality/test_manifest.py --suite unit-db --quiet

test-integration-lite:
	python scripts/quality/test_manifest.py --suite integration-lite --quiet

test-integration-all:
	python scripts/quality/test_manifest.py --suite integration-all --quiet

test-ops-contract:
	python scripts/quality/test_manifest.py --suite ops-contract --quiet

test-boundary-mapping-conformance:
	python scripts/quality/test_manifest.py --suite boundary-mapping-conformance --quiet

test-transaction-buy-contract:
	python scripts/quality/test_manifest.py --suite transaction-buy-contract --quiet

test-transaction-sell-contract:
	python scripts/quality/test_manifest.py --suite transaction-sell-contract --quiet

test-transaction-dividend-contract:
	python scripts/quality/test_manifest.py --suite transaction-dividend-contract --quiet

test-transaction-interest-contract:
	python scripts/quality/test_manifest.py --suite transaction-interest-contract --quiet

test-transaction-fx-contract:
	python scripts/quality/test_manifest.py --suite transaction-fx-contract --quiet

test-transaction-portfolio-flow-bundle-contract:
	python scripts/quality/test_manifest.py --suite transaction-portfolio-flow-bundle-contract --quiet

test-transaction-processing-contract:
	python scripts/quality/test_manifest.py --suite transaction-processing-contract --quiet

test-e2e-smoke:
	python scripts/quality/test_manifest.py --suite e2e-smoke --quiet

test-e2e-all:
	python scripts/quality/test_manifest.py --suite e2e-all --quiet

test-docker-smoke:
	python scripts/validation/docker_endpoint_smoke.py $(RUNTIME_BUILD_ARGUMENT)

test-latency-gate:
	python scripts/operations/latency_profile.py $(RUNTIME_BUILD_ARGUMENT) --enforce --seed-completion-timeout-seconds $(LATENCY_SEED_COMPLETION_TIMEOUT_SECONDS)

test-performance-load-gate:
	python scripts/operations/performance_load_gate.py $(RUNTIME_BUILD_ARGUMENT) --profile-tier fast --enforce

test-performance-load-gate-full:
	python scripts/operations/performance_load_gate.py $(RUNTIME_BUILD_ARGUMENT) --profile-tier full --enforce

profile-cost-history-capacity:
	python scripts/operations/cost_history_capacity_profile.py --output output/cost-history-capacity-profile.json

profile-cost-processing-modes:
	python scripts/operations/cost_processing_mode_capacity_profile.py --output output/cost-processing-mode-capacity-profile.json

test-failure-recovery-gate:
	python scripts/operations/failure_recovery_gate.py $(RUNTIME_BUILD_ARGUMENT) --enforce

test-derived-state-recovery-gate:
	python -m scripts.operations.recovery.derived_state_gate $(RUNTIME_BUILD_ARGUMENT) --enforce

test-derived-state-poison-gate:
	python -m scripts.operations.recovery.derived_state_poison_gate $(RUNTIME_BUILD_ARGUMENT) --enforce

test-derived-state-workload-smoke:
	python -m scripts.operations.performance.derived_state_workload_gate $(RUNTIME_BUILD_ARGUMENT) --diagnostic-smoke

profile-derived-state-daily:
	python -m scripts.operations.performance.derived_state_workload_gate $(RUNTIME_BUILD_ARGUMENT) --profile daily

profile-derived-state-fan-in:
	python -m scripts.operations.performance.derived_state_workload_gate $(RUNTIME_BUILD_ARGUMENT) --profile fan-in

profile-derived-state-price-burst:
	python -m scripts.operations.performance.derived_state_workload_gate $(RUNTIME_BUILD_ARGUMENT) --profile price-burst

profile-derived-state-price-restatement:
	python -m scripts.operations.performance.derived_state_workload_gate $(RUNTIME_BUILD_ARGUMENT) --profile price-restatement

profile-derived-state-fx-restatement:
	python -m scripts.operations.performance.derived_state_workload_gate $(RUNTIME_BUILD_ARGUMENT) --profile fx-restatement

test-institutional-completion-gate:
	python scripts/validation/institutional_completion_gate.py

test-institutional-signoff-pack:
	python scripts/validation/institutional_signoff_pack.py --require-all --max-age-hours 24

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
	$(MAKE) test-transaction-processing-contract

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
	python scripts/validation/dependency_health_check.py

check: lint no-alias-gate typecheck architecture-guard openapi-gate api-vocabulary-gate warning-gate test

coverage-gate:
	python scripts/quality/coverage_gate.py

CI_GATES := lint no-alias-gate typecheck architecture-guard openapi-gate api-vocabulary-gate warning-gate migration-smoke test-pr-suites coverage-gate security-audit test-pr-runtime-gates

ci: verify-dependencies $(CI_GATES)

ci-main: verify-dependencies-clean $(CI_GATES) test-release-gates

ci-local: verify-dependencies lint no-alias-gate typecheck architecture-guard openapi-gate api-vocabulary-gate test-unit-db coverage-gate

docker-build:
	docker build -f src/services/query_service/Dockerfile -t portfolio-analytics-query-service:ci .

docker-prebuild-ci:
	python scripts/release/prebuild_ci_images.py

clean:
	python scripts/development/clean_generated_artifacts.py
