.PHONY: install install-ci verify-dependencies compile-runtime-lock lint typecheck architecture-guard monetary-float-guard ingestion-contract-gate config-access-guard temporal-vocabulary-guard route-contract-family-guard source-data-product-contract-guard analytics-input-consumer-contract-guard event-runtime-contract-guard rfc0083-closure-guard no-alias-gate openapi-gate api-vocabulary-gate warning-gate migration-smoke migration-apply test test-fast test-medium test-heavy test-unit test-unit-db test-integration-lite test-integration-all test-ops-contract test-transaction-buy-contract test-transaction-sell-contract test-transaction-dividend-contract test-transaction-interest-contract test-transaction-fx-contract test-transaction-portfolio-flow-bundle-contract test-e2e-smoke test-e2e-all test-docker-smoke test-latency-gate test-performance-load-gate test-performance-load-gate-full test-failure-recovery-gate test-institutional-signoff-pack test-pr-suites test-pr-runtime-gates test-release-gates security-audit check coverage-gate ci ci-main ci-local docker-build docker-prebuild-ci clean

install:
	python scripts/bootstrap_dev.py

install-ci:
	python scripts/bootstrap_dev.py

verify-dependencies:
	python scripts/dependency_health_check.py --skip-audit

compile-runtime-lock:
	python scripts/update_shared_runtime_lock.py

lint:
	python -m ruff check src/services/query_service/app src/services/query_control_plane_service/app/enterprise_readiness.py src/services/ingestion_service/app/main.py src/libs/portfolio-common/portfolio_common/enterprise_readiness.py src/libs/portfolio-common/portfolio_common/openapi_enrichment.py src/libs/portfolio-common/portfolio_common/reconstruction_identity.py src/libs/portfolio-common/portfolio_common/ingestion_evidence.py src/libs/portfolio-common/portfolio_common/reconciliation_quality.py src/libs/portfolio-common/portfolio_common/source_data_products.py src/libs/portfolio-common/portfolio_common/market_reference_quality.py src/libs/portfolio-common/portfolio_common/source_data_security.py src/libs/portfolio-common/portfolio_common/event_supportability.py src/libs/portfolio-common/portfolio_common/events.py src/libs/portfolio-common/portfolio_common/outbox_repository.py tests/unit/services/query_service tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py tests/unit/libs/portfolio-common/test_openapi_enrichment.py tests/unit/libs/portfolio-common/test_reconstruction_identity.py tests/unit/libs/portfolio-common/test_ingestion_evidence.py tests/unit/libs/portfolio-common/test_reconciliation_quality.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_market_reference_quality.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/libs/portfolio-common/test_event_supportability.py tests/unit/libs/portfolio-common/test_outbox_repository.py tests/test_support tests/unit/test_support tests/unit/scripts/test_temporal_vocabulary_guard.py tests/unit/scripts/test_route_contract_family_guard.py tests/unit/scripts/test_source_data_product_contract_guard.py tests/unit/scripts/test_analytics_input_consumer_contract_guard.py tests/unit/scripts/test_event_runtime_contract_guard.py tests/unit/scripts/test_rfc0083_closure_guard.py scripts/test_manifest.py scripts/coverage_gate.py scripts/openapi_quality_gate.py scripts/warning_budget_gate.py scripts/api_vocabulary_inventory.py scripts/no_alias_contract_guard.py scripts/ingestion_endpoint_contract_gate.py scripts/temporal_vocabulary_guard.py scripts/route_contract_family_guard.py scripts/source_data_product_contract_guard.py scripts/analytics_input_consumer_contract_guard.py scripts/event_runtime_contract_guard.py scripts/rfc0083_closure_guard.py --ignore E501,I001
	python -m ruff check scripts/docker_endpoint_smoke.py scripts/latency_profile.py scripts/performance_load_gate.py scripts/config_access_guard.py --ignore E501,I001
	python -m ruff format --check src/services/query_service/app/main.py src/services/query_control_plane_service/app/enterprise_readiness.py src/services/ingestion_service/app/main.py src/libs/portfolio-common/portfolio_common/enterprise_readiness.py src/libs/portfolio-common/portfolio_common/openapi_enrichment.py src/libs/portfolio-common/portfolio_common/reconstruction_identity.py src/libs/portfolio-common/portfolio_common/ingestion_evidence.py src/libs/portfolio-common/portfolio_common/reconciliation_quality.py src/libs/portfolio-common/portfolio_common/source_data_products.py src/libs/portfolio-common/portfolio_common/market_reference_quality.py src/libs/portfolio-common/portfolio_common/source_data_security.py src/libs/portfolio-common/portfolio_common/event_supportability.py src/libs/portfolio-common/portfolio_common/events.py src/libs/portfolio-common/portfolio_common/outbox_repository.py tests/unit/services/query_service/test_openapi_quality_gate.py tests/unit/services/query_service/test_api_vocabulary_inventory.py tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py tests/unit/libs/portfolio-common/test_openapi_enrichment.py tests/unit/libs/portfolio-common/test_reconstruction_identity.py tests/unit/libs/portfolio-common/test_ingestion_evidence.py tests/unit/libs/portfolio-common/test_reconciliation_quality.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_market_reference_quality.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/libs/portfolio-common/test_event_supportability.py tests/unit/libs/portfolio-common/test_outbox_repository.py tests/unit/scripts/test_temporal_vocabulary_guard.py tests/unit/scripts/test_route_contract_family_guard.py tests/unit/scripts/test_source_data_product_contract_guard.py tests/unit/scripts/test_analytics_input_consumer_contract_guard.py tests/unit/scripts/test_event_runtime_contract_guard.py tests/unit/scripts/test_rfc0083_closure_guard.py scripts/test_manifest.py scripts/coverage_gate.py scripts/openapi_quality_gate.py scripts/warning_budget_gate.py scripts/api_vocabulary_inventory.py scripts/no_alias_contract_guard.py scripts/docker_endpoint_smoke.py scripts/latency_profile.py scripts/performance_load_gate.py scripts/ingestion_endpoint_contract_gate.py scripts/config_access_guard.py scripts/temporal_vocabulary_guard.py scripts/route_contract_family_guard.py scripts/source_data_product_contract_guard.py scripts/analytics_input_consumer_contract_guard.py scripts/event_runtime_contract_guard.py scripts/rfc0083_closure_guard.py
	$(MAKE) monetary-float-guard
	$(MAKE) ingestion-contract-gate
	$(MAKE) config-access-guard
	$(MAKE) temporal-vocabulary-guard
	$(MAKE) route-contract-family-guard
	$(MAKE) source-data-product-contract-guard
	$(MAKE) analytics-input-consumer-contract-guard
	$(MAKE) event-runtime-contract-guard
	$(MAKE) rfc0083-closure-guard

monetary-float-guard:
	python scripts/check_monetary_float_usage.py

no-alias-gate:
	python scripts/no_alias_contract_guard.py

ingestion-contract-gate:
	python scripts/ingestion_endpoint_contract_gate.py

config-access-guard:
	python scripts/config_access_guard.py

temporal-vocabulary-guard:
	python scripts/temporal_vocabulary_guard.py

route-contract-family-guard:
	python scripts/route_contract_family_guard.py

source-data-product-contract-guard:
	python scripts/source_data_product_contract_guard.py

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

openapi-gate:
	python scripts/openapi_quality_gate.py

api-vocabulary-gate:
	python scripts/api_vocabulary_inventory.py --validate-only

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
	python scripts/latency_profile.py --build --enforce

test-performance-load-gate:
	python scripts/performance_load_gate.py --build --profile-tier fast --enforce

test-performance-load-gate-full:
	python scripts/performance_load_gate.py --build --profile-tier full --enforce

test-failure-recovery-gate:
	python scripts/failure_recovery_gate.py --build --enforce

test-institutional-signoff-pack:
	python scripts/institutional_signoff_pack.py --require-all --max-age-hours 24

test-pr-suites:
	$(MAKE) test-unit-db
	$(MAKE) test-integration-lite
	$(MAKE) test-ops-contract
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
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.ruff_cache', '.mypy_cache', 'src/services/query_service/build']]; [pathlib.Path(p).unlink(missing_ok=True) for p in ['.coverage', '.coverage.unit', '.coverage.integration_lite']]"
