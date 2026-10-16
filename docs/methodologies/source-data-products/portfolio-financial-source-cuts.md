# Neutral Portfolio Source Custody

`PortfolioHistoricalRegistry:v1` retains producer-declared historical membership.
`PortfolioFinancialSourceCut:v1` retains a batch manifest and independently reconstructible
five-role source graph for each selected portfolio. Custody establishes what was retained and
which native receipts and bytes support it. It does not establish institutional approval,
independent expected-population verification, cross-source compatibility, or financial results.

## Contracts And Ownership

| Responsibility | Owner |
| --- | --- |
| Registry declarations, immutable batch/CAS, capture bytes and native completion | Core |
| Normalization, compatible monthly assembly, rule evaluation and policy approval | Manage |
| Financial performance calculations and consumer acceptance | Performance |
| Independent institution/provider approval and enrollment | Named external source authority |

The shared [domain](../../../src/libs/portfolio-common/portfolio_common/domain/portfolio_financial_source_cuts.py)
and closed [admission contracts](../../../src/libs/portfolio-common/portfolio_common/portfolio_financial_source_cut_admission.py)
define the typed declarations. The [read DTO](../../../src/services/query_control_plane_service/app/contracts/portfolio_financial_source_cuts.py)
keeps batch, selected graph, capture and pagination commitments distinct.

## Historical Membership

Members are ordered by `(provider_namespace, source_member_id)` and retain nullable Core mappings,
member revision and ordered, nonoverlapping, half-open effective declarations. Currency,
discretionary `true`/`false`/`null` and explicit inclusion remain independent source declarations.
An excluded or unmapped member still contributes to the retained member population and root.
Identifiers use Unicode code-point order, without locale folding or normalization. New member
keys and financial input/link portfolio keys use PostgreSQL `C` collation with UTF-8 so indexed
verification and pagination agree with the canonical Python ordering.
Independent expected-population reference, definition, count and hash are retained separately;
reconciling supplied counts does not verify that external population.

A complete-empty registry retains an actual manifest, native receipt and empty ordered roots.
An absent or incomplete cut cannot be returned as a complete-empty registry.

## Selected Financial Graph

Each selected portfolio binds its registry root/member revision, currency, prior and month-end dates,
and exactly this role order:

1. `PRIOR_ASSETS`: existing portfolio-timeseries source or retained export selection.
2. `MONTH_END_ASSETS`: existing portfolio-timeseries source or retained export selection.
3. `CASH`: exact immutable cash-availability observation.
4. `READINESS`: exact immutable funding/investment observation.
5. `FLOWS`: one exact complete existing flow source cut, including reversal dependencies.

Native custody currently requires retained completed valuation exports with actual page evidence;
an inline selector without a completed export is explicitly unavailable. Source roots, selectors,
native job IDs and source revisions are immutable pins. Cash and readiness facts are not inferred
from valuation, lifecycle, one another, or a settled-minus-encumbered formula.

Optional settled-unencumbered semantics retain exact Decimal text or null, explicit definition,
currency/date and producer revision. Optional compatibility declarations bind the exact five roots,
registry root, producer/scope, coverage/currency and original evidence reference/digest. Their
posture is `DECLARED_UNVERIFIED`; absent declarations remain `UNAVAILABLE`.

## Hash And Count Dictionary

| Commitment | Meaning |
| --- | --- |
| Batch manifest/CAS hash | Exact source identity, revision and declared aggregate roots/counts |
| Input content hash | Header-independent closed selected-portfolio declaration |
| Graph content hash | Independently reconstructed domain graph including its source identity |
| Native typed content hash | Existing fact, complete flow-cut or retained export selection hash |
| Whole raw hash | SHA-256 over the exact retained artifact bytes |
| Segment hash | SHA-256 over one contiguous byte segment |
| Ordered set hash | Domain-separated chain over canonical logical items for one read view |

For domain string `D`, initialize `S = SHA256(UTF8(D + NUL))`. For each bare64 item hash `H`
in the required order, set `S = SHA256(S || hex_decode(H))`. After `n` items, return
`SHA256(S || NUL || ASCII(n))`, with item count `n`. Zero items still have a domain-specific root.
Checkpoints retain the domain, exact count and state; they do not change the algorithm.

| Read root kind | Domain and item projection |
| --- | --- |
| `CUT_HEADERS` | `NeutralSourceCutHeaders:v1`; one manifest content hash |
| `REGISTRY_MEMBERS` | `PortfolioHistoricalRegistryMembers:v1`; every ordered member content hash |
| `SELECTED_FINANCIAL_INPUTS` | `PortfolioFinancialSourceCutInputs:v1`; the selected input hash once |
| `CAPTURE_ARTIFACTS` | `PortfolioNeutralSourceCaptureArtifacts:v1`; one full artifact-metadata commitment per role/page/capture |

The selected-input chain has count one; it is not the batch selection root/count. Capture root
items exclude transport `row_kind`, segment index/hash and base64 bytes, and include the
`PortfolioNeutralSourceCaptureArtifact:v1` domain plus all remaining artifact metadata.
Multiple segments contribute one logical artifact. Distinct role/page uses remain distinct even
when they reference the same acquired capture. Pagination `total_count` counts wire rows or
segments; `root_item_count` counts logical commitment items.

## Captured Formats

The shared [capture catalog and reconstruction helpers](../../../src/libs/portfolio-common/portfolio_common/portfolio_financial_source_cut_models.py)
are authoritative. Original ingress tags carry original JSON bytes without a wrapper.
Acquired native tags carry canonical UTF-8 JSON `{serializer, payload}`, with sorted keys,
compact separators, ASCII escaping and nonfinite values refused.

| Acquired serializer | Typed reconstruction |
| --- | --- |
| `portfolio-cash-availability:domain-json:v1` | Complete existing cash domain DTO and original observation hash |
| `portfolio-funding-investment:domain-json:v1` | Complete existing funding/investment domain DTO and original observation hash |
| `portfolio-flow-source-cut:domain-json:v1` | Complete existing cut and event/dependency domain DTOs, validated reversal closure |
| `portfolio-timeseries-export:retained-json:v1` | Original retained export result/request and shared `analytics-export-selection-v1` identity |

Schema version is `v1`, MIME is `application/json`. Cash and flow expose no native epoch or
request scope; null remains null. Valuation requires the actual consistent retained epoch/scope.
Acquisition time, source observation/generation, native receipt/completion and original supplier
chronology are distinct. Acquired DTO bytes are never relabeled original supplier wire data.

## Validation Boundary

Rows and uncompressed bytes are bounded per admission page, not per population/history.
The current limits are 500 rows and 1 MiB, with 512 KiB byte segments. Existing flow-v1's
1000 combined native pin limit remains an existing dependency; custody does not concatenate cuts
or certify flow-v2. Worker writes retain at most two segments per fenced transaction and verify
the whole retained artifact outside that write transaction before linking it to a completed cut.

Fixed unqualified/unverified posture, source-off replay and independent downstream verification
remain mandatory. Unit/static evidence does not qualify S/M/L/D/H scale, PostgreSQL execution,
bank approval, whole-assembly authority, financial accuracy or production readiness.
See the [operating runbook](../../operations/portfolio-financial-source-cuts.md).
