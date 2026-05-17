# External Order Execution Acknowledgement Methodology

## Metric

`ExternalOrderExecutionAcknowledgement:v1` is the core-owned external OMS acknowledgement posture
product exposed by
`POST /integration/portfolios/{portfolio_id}/external-order-execution-acknowledgement`.

It resolves portfolio mandate identity and returns a deterministic fail-closed unavailable posture
until bank-owned OMS acknowledgement ingestion is certified. The product is supportability evidence
only. It does not create orders, route venues, declare best execution, acknowledge OMS execution,
certify fills, confirm settlement, certify execution status, or perform autonomous execution action.

## Endpoint and Mode Coverage

| Request shape | Implemented behavior |
| --- | --- |
| `portfolio_id` path parameter | Selects the private-banking portfolio whose OMS acknowledgement posture is requested. |
| `as_of_date` | Resolves the effective discretionary mandate binding and runtime source-data metadata. |
| optional `tenant_id` | Included in runtime metadata and deterministic fingerprints. |
| optional `mandate_id` | Disambiguates the mandate binding when supplied. |
| optional `execution_intent_id` | Echoed for downstream audit only; Core does not create, amend, or route orders. |
| optional `order_reference_ids` | Echoed for downstream audit only; Core does not certify acknowledgement, fill, or settlement status from these values. |

The current implemented mode is fail-closed source posture. There is no local simulated OMS mode,
no execution-routing mode, no best-execution mode, and no bank-owned OMS ingestion mode.

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose external OMS acknowledgement supportability is requested. |
| `as_of_date` | Request body | Yes | Business date used for mandate binding and product identity. |
| `tenant_id` | Request body | No | Tenant scope included in runtime source-data metadata. |
| `mandate_id` | Request body | No | Optional mandate discriminator. |
| `execution_intent_id` | Request body | No | Downstream execution-intent identifier echoed for audit. |
| `order_reference_ids` | Request body | No, default empty | External order references requested for acknowledgement lookup and echoed for audit. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `portfolio_mandate_bindings` | `portfolio_id`, `client_id`, `mandate_id`, `mandate_type`, `effective_from`, `effective_to`, `observed_at`, `quality_status` | Binding must be discretionary, active, and effective on `as_of_date`. |
| Bank-owned OMS acknowledgement source | none ingested | Not certified in the current runtime. The product always reports the family as missing. |

## Unit Conventions

The product has no monetary, quantity, price, or return unit. It returns supportability state,
missing data families, blocked capabilities, audit echoes, lineage, and runtime source-data
metadata.

Order reference identifiers and execution intent identifiers are treated as opaque strings. They
are not parsed for venue, broker, fill, settlement, or best-execution semantics.

## Variable Dictionary

| Symbol | Response or source field | Definition |
| --- | --- | --- |
| `P` | `portfolio_id` | Requested portfolio. |
| `A` | `as_of_date` | Business date for mandate binding and product runtime identity. |
| `M` | `mandate_id` | Resolved discretionary mandate identifier, when available. |
| `C` | `client_id` | Client identifier from the resolved mandate binding. |
| `E` | `execution_intent_id` | Optional downstream execution intent echoed for audit. |
| `O` | `order_reference_ids` | Optional requested order reference ids echoed for audit. |
| `ACK` | `acknowledgements` | External OMS acknowledgement rows. Current runtime returns `[]`. |
| `n_ACK` | `supportability.acknowledgement_count` | Count of returned acknowledgement rows. Current runtime returns `0`. |
| `F_missing` | `supportability.missing_data_families` | Required source-data family not certified for use. |
| `B_blocked` | `supportability.blocked_capabilities` | Capabilities explicitly blocked while OMS acknowledgement data is unavailable. |

## Methodology and Formulas

The current posture is deterministic:

`ACK = []`

`n_ACK = len(ACK) = 0`

`F_missing = ["external_oms_order_execution_acknowledgement"]`

`B_blocked = ["order_generation", "venue_routing", "best_execution", "oms_acknowledgement", "fills", "settlement", "execution_status_certification", "autonomous_execution_action"]`

`supportability.state = "UNAVAILABLE"`

`supportability.reason = "EXTERNAL_OMS_SOURCE_NOT_INGESTED"`

`data_quality_status = "MISSING"`

The source batch fingerprint is computed from product name, portfolio id, resolved client id,
resolved mandate id, as-of date, optional execution intent id, sorted order reference ids, and the
fixed integration status `not_ingested`. The snapshot id uses the same deterministic posture with
the `external_order_execution_acknowledgement:` prefix.

## Step-by-Step Computation

1. Resolve `DiscretionaryMandateBinding:v1` for `portfolio_id`, `as_of_date`, and optional
   `mandate_id`.
2. Return HTTP `404` if no active discretionary mandate binding exists.
3. Preserve optional `execution_intent_id` and `order_reference_ids` as audit echoes only.
4. Set `acknowledgements` to an empty list and `acknowledgement_count` to `0`.
5. Set missing data family to `external_oms_order_execution_acknowledgement`.
6. Set blocked capabilities to order generation, venue routing, best execution, OMS
   acknowledgement, fills, settlement, execution-status certification, and autonomous execution
   action.
7. Emit lineage with source system `external-bank-oms`, source table `not_ingested`, contract
   version `rfc_042_external_order_execution_acknowledgement_v1`, runtime posture `fail_closed`,
   and blocked-capability non-claims.
8. Emit runtime source-data metadata with `data_quality_status=MISSING`, no latest evidence
   timestamp, and deterministic fingerprints.

## Validation and Failure Behavior

| Condition | Behavior |
| --- | --- |
| No active discretionary mandate binding exists | API returns HTTP `404`; no unavailable supportability body is fabricated. |
| OMS acknowledgement ingestion is not certified | Response returns supportability `UNAVAILABLE` and reason `EXTERNAL_OMS_SOURCE_NOT_INGESTED`. |
| `execution_intent_id` is supplied | Value is echoed for audit only and does not trigger order creation, routing, or status certification. |
| `order_reference_ids` are supplied | Values are echoed for audit only and do not trigger OMS lookup or status certification. |
| Duplicate or unknown order references are supplied | Current fail-closed posture does not classify them; OMS ingestion must be certified before reference-level status can be claimed. |

`data_quality_status` is `MISSING` because no external OMS acknowledgement source table is
certified. Consumers must fail closed when this product is required for execution-acknowledgement
realization.

## Configuration Options

| Option | Current value |
| --- | --- |
| Product identity | `ExternalOrderExecutionAcknowledgement:v1` |
| Supportability state | `UNAVAILABLE` |
| Supportability reason | `EXTERNAL_OMS_SOURCE_NOT_INGESTED` |
| Missing data family | `external_oms_order_execution_acknowledgement` |
| Acknowledgement rows | Always empty until bank-owned OMS ingestion is certified |
| Latest evidence timestamp | `null` |

## Outputs

| Field | Methodology mapping |
| --- | --- |
| `portfolio_id` | Requested portfolio `P`. |
| `client_id` | Client `C` from resolved discretionary mandate binding. |
| `mandate_id` | Resolved mandate `M`, when available. |
| `execution_intent_id` | Request echo `E`; audit only. |
| `order_reference_ids` | Request echo `O`; audit only. |
| `acknowledgements` | `ACK`, currently `[]`. |
| `supportability.acknowledgement_count` | `n_ACK`, currently `0`. |
| `supportability.missing_data_families` | `F_missing`. |
| `supportability.blocked_capabilities` | `B_blocked`. |
| `lineage` | External OMS source system, not-ingested table posture, contract version, fail-closed runtime posture, and non-claims. |

## Worked Example

Request:

`POST /integration/portfolios/PB_SG_GLOBAL_BAL_001/external-order-execution-acknowledgement`

```json
{
  "as_of_date": "2026-05-03",
  "execution_intent_id": "rebalance-run-2026-05-03-001",
  "order_reference_ids": ["OMS-ORDER-001", "OMS-ORDER-002"]
}
```

Resolved source facts:

| Source fact | Value |
| --- | --- |
| Portfolio | `PB_SG_GLOBAL_BAL_001` |
| Client | resolved from active discretionary mandate binding |
| OMS acknowledgement source table | `not_ingested` |
| Certified OMS acknowledgement rows | none |

Final output mapping:

| Response field | Value |
| --- | --- |
| `supportability.state` | `UNAVAILABLE` |
| `supportability.reason` | `EXTERNAL_OMS_SOURCE_NOT_INGESTED` |
| `supportability.acknowledgement_count` | `0` |
| `acknowledgements` | `[]` |
| `supportability.missing_data_families[0]` | `external_oms_order_execution_acknowledgement` |
| `supportability.blocked_capabilities` | order generation, venue routing, best execution, OMS acknowledgement, fills, settlement, execution-status certification, autonomous execution action |
| `data_quality_status` | `MISSING` |

## Downstream Consumption Rules

Consumers may use the unavailable posture to block execution-acknowledgement realization and route
operators to OMS source-integration work. Gateway and Workbench surfaces must consume the
authoritative downstream contract and must not invent acknowledgement rows, replay posture,
fill/settlement status, venue status, or best-execution conclusions from this Core source posture.
