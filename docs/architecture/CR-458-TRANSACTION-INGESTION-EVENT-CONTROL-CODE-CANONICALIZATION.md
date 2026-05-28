# CR-458: Transaction Ingestion And Event Control-Code Canonicalization

Date: 2026-05-28

## Scope

Transaction ingestion DTOs, shared `TransactionEvent`, and the neutral shared control-code
normalization helper used before Kafka publish, persistence upsert, and calculator consumption.

## Finding

CR-457 hardened the transaction-domain canonical models, but raw transaction control codes could
still enter the platform earlier through the ingestion DTO and shared event model. Padded or
lower-case values for transaction type, cash-leg modes, FX component roles, settlement status,
interest direction, corporate-action child role, and synthetic-flow classifications could be
published to Kafka or persisted before downstream domain validators saw them.

The first implementation also showed that importing normalization from the `transaction_domain`
package inside `events.py` creates an avoidable package import cycle because transaction-domain
modules import `TransactionEvent`.

## Change

Moved the tiny control-code normalization helper to neutral `portfolio_common` ownership and kept
the existing transaction-domain module as a compatibility re-export. Then applied write-boundary
canonicalization to:

1. ingestion `Transaction.transaction_type`,
2. shared `TransactionEvent.transaction_type`,
3. optional cash and linkage fields: `cash_entry_mode`, `movement_direction`,
   `originating_transaction_type`, `adjustment_reason`, and `link_type`,
4. optional income/FX fields: `interest_direction`, `component_type`, `fx_cash_leg_role`,
   `settlement_status`, `fx_rate_quote_convention`, `spot_exposure_model`, and
   `fx_realized_pnl_mode`,
5. optional corporate-action and synthetic-flow control fields: `child_role`,
   `synthetic_flow_valuation_method`, `synthetic_flow_classification`,
   `synthetic_flow_price_source`, `synthetic_flow_fx_source`, and `synthetic_flow_source`.

Optional values remain `None` when omitted so existing downstream defaulting and reason-code
validation behavior is preserved.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/ingestion_service/test_transaction_model.py tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py -q`
2. `python -m pytest tests/unit/services/ingestion_service -q`
3. `python -m pytest tests/unit/libs/portfolio_common -q`
4. `python -m pytest tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py tests/integration/services/persistence_service/repositories/test_repositories.py -q`
5. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
6. `python -m ruff check src/libs/portfolio-common/portfolio_common/control_code_normalization.py src/libs/portfolio-common/portfolio_common/events.py src/libs/portfolio-common/portfolio_common/transaction_domain/control_code_normalization.py src/services/ingestion_service/app/DTOs/transaction_dto.py src/libs/portfolio-common/portfolio_common/transaction_domain/buy_models.py src/libs/portfolio-common/portfolio_common/transaction_domain/sell_models.py src/libs/portfolio-common/portfolio_common/transaction_domain/dividend_models.py src/libs/portfolio-common/portfolio_common/transaction_domain/interest_models.py src/libs/portfolio-common/portfolio_common/transaction_domain/fx_models.py tests/unit/services/ingestion_service/test_transaction_model.py tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py`
7. `git diff --check`

Results:

1. Focused ingestion/event proof: `13 passed`
2. Ingestion-service unit pack: `121 passed`
3. Portfolio-common unit pack: `137 passed`
4. Persistence transaction pack: `16 passed`
5. Ingestion router integration pack: `212 passed`
6. Touched-surface ruff: passed
7. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
write boundary now emits canonical transaction control codes while preserving the existing
downstream validators as the authority for supported-value decisions and reason-code evidence.
