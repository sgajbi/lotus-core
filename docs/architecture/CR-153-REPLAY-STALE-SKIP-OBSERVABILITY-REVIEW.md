# CR-153 - Replay Stale-Skip Observability Review

## Scope
- valuation scheduler epoch-fenced watermark advancement
- terminal `REPROCESSING -> CURRENT` normalization
- reset-watermarks fanout under current-epoch fencing
- Grafana replay dashboard coverage

## Finding
The replay and scheduler paths already warned when stale epoch fencing caused partial updates, but the stale-skip counts were not exported as metrics. That made recurring replay pressure invisible unless operators searched logs.

## Fix
- Added `reprocessing_stale_skips_total{stage=...}` to the shared monitoring layer.
- Emitted the metric from:
  - reset-watermarks fanout
  - watermark advancement
  - terminal reprocessing normalization
- Added unit proofs for all three emission paths.
- Added a Grafana panel for stale-skip pressure by stage.

## Result
Replay pressure from stale epoch fences is now visible in Prometheus and Grafana, which turns a previously forensic-only signal into an actionable runtime metric.
