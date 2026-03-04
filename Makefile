.PHONY: install lint typecheck architecture-guard monetary-float-guard ingestion-contract-gate config-access-guard no-alias-gate openapi-gate api-vocabulary-gate warning-gate migration-smoke migration-apply test test-fast test-medium test-heavy test-unit test-unit-db test-integration-lite test-ops-contract test-transaction-buy-contract test-transaction-sell-contract test-buy-rfc test-sell-rfc test-e2e-smoke test-docker-smoke test-latency-gate test-performance-load-gate test-performance-load-gate-full test-failure-recovery-gate security-audit check coverage-gate ci ci-local docker-build clean

install:
	python scripts/bootstrap_dev.py

lint:
	python -m ruff check src/services/query_service/app src/services/ingestion_service/app/main.py src/libs/portfolio-common/portfolio_common/openapi_enrichment.py tests/unit/services/query_service tests/unit/libs/portfolio-common/test_openapi_enrichment.py tests/test_support tests/unit/test_support scripts/test_manifest.py scripts/coverage_gate.py scripts/openapi_quality_gate.py scripts/warning_budget_gate.py scripts/api_vocabulary_inventory.py scripts/no_alias_contract_guard.py scripts/ingestion_endpoint_contract_gate.py --ignore E501,I001
	python -m ruff check scripts/docker_endpoint_smoke.py scripts/latency_profile.py scripts/performance_load_gate.py scripts/config_access_guard.py --ignore E501,I001
	python -m ruff format --check src/services/query_service/app/main.py src/services/ingestion_service/app/main.py src/libs/portfolio-common/portfolio_common/openapi_enrichment.py tests/unit/services/query_service/test_openapi_quality_gate.py tests/unit/services/query_service/test_api_vocabulary_inventory.py tests/unit/libs/portfolio-common/test_openapi_enrichment.py scripts/test_manifest.py scripts/coverage_gate.py scripts/openapi_quality_gate.py scripts/warning_budget_gate.py scripts/api_vocabulary_inventory.py scripts/no_alias_contract_guard.py scripts/docker_endpoint_smoke.py scripts/latency_profile.py scripts/performance_load_gate.py scripts/ingestion_endpoint_contract_gate.py scripts/config_access_guard.py
	$(MAKE) monetary-float-guard
	$(MAKE) ingestion-contract-gate
	$(MAKE) config-access-guard

monetary-float-guard:
	python scripts/check_monetary_float_usage.py

no-alias-gate:
	python scripts/no_alias_contract_guard.py

ingestion-contract-gate:
	python scripts/ingestion_endpoint_contract_gate.py

config-access-guard:
	python scripts/config_access_guard.py

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
	alembic upgrade head

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

test-ops-contract:
	python scripts/test_manifest.py --suite ops-contract --quiet

test-transaction-buy-contract:
	python scripts/test_manifest.py --suite transaction-buy-contract --quiet

test-buy-rfc: test-transaction-buy-contract

test-transaction-sell-contract:
	python scripts/test_manifest.py --suite transaction-sell-contract --quiet

test-sell-rfc: test-transaction-sell-contract

test-e2e-smoke:
	python scripts/test_manifest.py --suite e2e-smoke --quiet

test-docker-smoke:
	python scripts/docker_endpoint_smoke.py --build

test-latency-gate:
	python scripts/latency_profile.py --build --enforce

test-performance-load-gate:
	python scripts/performance_load_gate.py --profile-tier fast --enforce

test-performance-load-gate-full:
	python scripts/performance_load_gate.py --build --profile-tier full --enforce

test-failure-recovery-gate:
	python scripts/failure_recovery_gate.py --build --enforce

security-audit:
	python -m pip_audit -r tests/requirements.txt

check: lint no-alias-gate typecheck architecture-guard openapi-gate api-vocabulary-gate warning-gate test

coverage-gate:
	python scripts/coverage_gate.py

ci: lint no-alias-gate typecheck architecture-guard openapi-gate api-vocabulary-gate warning-gate migration-smoke test-unit-db test-integration-lite coverage-gate security-audit

ci-local: lint typecheck coverage-gate

docker-build:
	docker build -f src/services/query_service/Dockerfile -t portfolio-analytics-query-service:ci .

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.ruff_cache', '.mypy_cache']]; pathlib.Path('.coverage').unlink(missing_ok=True)"
