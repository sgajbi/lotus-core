# CR-1464: Backdated Cost Variant Parity

Date: 2026-07-10
Issue: #468
Status: Hardened locally

## Objective

Prove that CR-1463 affected-suffix correction applies to fee-bearing multi-lot FIFO and
cross-currency local/base calculations, not only simple FIFO and AVCO examples.

## Fee And Multi-Lot Evidence

The governed scenario inserts a fee-bearing buy before two later buys and a partial FIFO disposal.
After correction:

- later disposal cost is `1111` and realized gain is `683`;
- the two surviving source lots carry `30 / 303` and `50 / 605` quantity/base basis;
- final current-epoch position is `80` units with `908` basis;
- all four transaction fee rows remain singular;
- exactly four processed transaction events exist for four booked inputs.

## Cross-Currency Evidence

The governed EUR transaction / SGD portfolio scenario uses effective-dated rates `1.40`, `1.50`,
and `1.60`. After inserting the earlier buy:

- later disposal cost is `808` local and `1131.20` base;
- realized gain is `386` local and `779.20` base;
- the unaffected later lot remains `100` units with `1010` local and `1515` base basis;
- final current-epoch position reconciles to that same local/base basis;
- exactly three processed transaction events exist for three booked inputs.

## Validation And Compatibility

- new PostgreSQL variant pack: 2 passed in 78.15 seconds;
- full combined PostgreSQL pack: 17 passed in 116.25 seconds;
- cost and target unit pack: 231 passed;
- MyPy passed for 35 source files;
- strict architecture, in-process boundaries, dependency inversion, Ruff, format, and diff gates
  passed.

No production source changed in this slice. API, Kafka, database, event-count, idempotency, and
calculation contracts remain those implemented by CR-1463. No README or wiki update is required
because CR-1463 already updated the authored methodology and operator page.
