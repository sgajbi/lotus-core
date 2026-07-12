# CR-1446: AVCO Source-Quantity Reconciliation

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Finding

`AverageCostBasisStrategy` correctly maintained pooled quantity and cost but returned an empty
source-quantity map. `CostCalculatorRepository.update_lot_open_quantities(...)` interprets missing
source transaction IDs as zero. As a result, AVCO processing could mark all authoritative
`position_lot_state` rows closed while the portfolio still held the security.

This is externally observable because buy-state and `PortfolioTaxLotWindow:v1` use `open_quantity`
to classify source lots as OPEN or CLOSED.

## Change

AVCO now tracks remaining quantity by source BUY transaction and reduces those quantities pro rata
on every disposal. The allocation:

- preserves pooled average-cost COGS arithmetic;
- handles a new BUY after an earlier disposal;
- closes every source exactly on full disposal;
- uses Decimal arithmetic at the database's 10-decimal quantity scale;
- assigns any division residual to the final source row so source quantities sum exactly to pooled
  holdings.

FIFO behavior is unchanged; its available-quantity return is now explicitly typed.

## Compatibility Impact

This is an intentional correctness change. Future AVCO lot rows remain OPEN while pooled holdings
remain positive instead of being falsely reported CLOSED. Public field names and schemas do not
change, but affected source values and status become truthful.

Historical AVCO rows may already contain false zero quantities. A governed reconciliation/backfill
with rollback and source-product validation is required before runtime cutover claims current
historical lot evidence.

## Validation

- focused strategy tests: 20 passed;
- full cost-engine unit pack: 108 passed;
- focused Ruff, MyPy, and diff checks passed.

No wiki update is made in this slice because deployed runtime has not changed; final methodology and
operator guidance must include the backfill and cutover result.
