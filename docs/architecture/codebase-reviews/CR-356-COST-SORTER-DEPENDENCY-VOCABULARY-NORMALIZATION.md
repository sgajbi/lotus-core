# CR-356 Cost Sorter Dependency Vocabulary Normalization

Date: 2026-05-27

## Scope

Reviewed cost-engine transaction ordering for source-system vocabulary variation after calculation
logic normalization in the cost, position, valuation, and cashflow paths.

## Findings

`TransactionSorter` dependency ranking uppercased transaction, component, product, asset-class,
instrument, and security codes without trimming source whitespace.

That created cost-basis sequencing risks:

1. padded corporate-action transaction types could miss Bundle A dependency ranks, allowing
   quantity sorting to process target-in legs before source-out legs,
2. padded cash product, asset-class, or instrument identifiers could fail cash detection,
3. padded cash transaction types could miss inflow/outflow dependency ranks, allowing same-day
   quantity sorting to process cash outflows before available inflows.

For private banking books, this is a correctness issue because cost basis depends on deterministic
same-day sequencing for corporate actions, cash settlements, transfers, deposits, withdrawals, and
fee movements.

## Actions Taken

Hardened `src/services/calculators/cost_calculator_service/app/cost_engine/processing/sorter.py`:

1. added one sorter-local normalization helper using `strip().upper()`,
2. applied it to Bundle A dependency ranking,
3. applied it to cash dependency ranking for product type, asset class, component type,
   transaction type, instrument id, and security id.

Added direct unit proof for:

1. padded lower-case `DEMERGER_OUT` and `DEMERGER_IN` still processing source-out before target-in,
2. padded lower-case cash deposit and fee values still processing inflow before outflow even when
   the outflow has the larger quantity.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_sorter.py -q
7 passed

python -m pytest tests/unit/services/calculators/cost_calculator_service -q
91 passed

python -m ruff check src/services/calculators/cost_calculator_service/app/cost_engine/processing/sorter.py tests/unit/services/calculators/cost_calculator_service/engine/test_sorter.py
All checks passed
```

## Follow-Up

No API or wiki source change is required because this canonicalizes internal cost-engine processing
order without changing public contracts. Continue reviewing parser and consumer enrichment so source
vocabulary is normalized as early as practical while calculators remain defensive at execution time.
