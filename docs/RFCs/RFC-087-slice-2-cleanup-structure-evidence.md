# RFC-087 Slice 2 Cleanup And Structure Evidence

| Field | Value |
| --- | --- |
| RFC | RFC-087 - DPM Source Data Products for lotus-manage Stateful Execution |
| Slice | Slice 2 - Cleanup and structure |
| Status | Locally implemented and validated; remote Feature Lane proof follows the slice commit. |

## Review Findings

The Slice 2 scan checked for stale DPM execution-context assumptions, advisory leftovers, duplicate
product definitions, and source-product structure gaps across `src/`, `tests/`, `docs/`,
`contracts/`, `wiki/`, and `scripts/`.

Findings:

1. No live core route for a monolithic `dpm-execution-context` exists and no new one should be
   added.
2. Existing advisory simulation code in core is not dead code: it remains the simulation support
   surface used by `lotus-advise` and should not be removed as part of `lotus-manage` DPM cleanup.
3. The main maintainability gap was that the five RFC-087 DPM source products existed only in RFC
   prose, which would force later endpoint slices to copy names, routes, ingestion dependencies,
   and certification requirements manually.

## Implemented Cleanup

Slice 2 added `docs/standards/rfc-087-dpm-source-product-spec.v1.json` as the machine-readable
implementation structure for the five DPM source-data products:

1. `DpmModelPortfolioTarget:v1`,
2. `DiscretionaryMandateBinding:v1`,
3. `InstrumentEligibilityProfile:v1`,
4. `PortfolioTaxLotWindow:v1`,
5. `MarketDataCoverageWindow:v1`.

The spec records:

1. the no-monolithic-route architecture decision,
2. certification controls that every endpoint slice must keep mandatory,
3. proposed route, required ingestion, response-output families, and implementation slice for each
   product.

This reduces RFC prose duplication and gives later implementation slices a stable target contract.

## Validation Evidence

Focused test added:

```powershell
python -m pytest tests/unit/docs/test_rfc087_dpm_source_product_spec.py -q
```

The test proves:

1. all five DPM products are present and aligned to the expected slices,
2. every product uses a `POST /integration/...` serving route,
3. no proposed route contains `dpm-execution-context` or `execution-context`,
4. certification controls remain mandatory,
5. the RFC links to the machine-readable spec and names every product in the spec.

Existing source-data governance guards:

```powershell
make route-contract-family-guard
make source-data-product-contract-guard
make domain-product-validate
```

Observed result:

1. route contract-family guard passed,
2. source-data product contract guard passed,
3. domain-product validation passed for the repo-native producer declaration.

Wiki decision:

No repo-local wiki update is needed in Slice 2. The slice adds implementation structure and tests
for a still-planned RFC; long-lived business/operator wiki material should be added only after the
affected DPM APIs are implemented and proven.

## Slice Exit Assessment

Slice 2 can close after the focused spec test and existing source-data product guards pass locally
and the branch Feature Lane is green after the slice commit.
