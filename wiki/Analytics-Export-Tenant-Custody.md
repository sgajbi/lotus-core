# Analytics Export Tenant Custody

Durable analytics export access follows the admitted tenant and the authoritative portfolio
owner. Status, result retrieval, reuse, refresh and lifecycle writes enforce that ownership;
foreign and orphan exports fail closed. The source reader also admits the portfolio before
reservation effects.

The design reuses globally unique portfolio identity and immutable tenant ownership. It adds no
schema or tenant transfer facility. Capability admission and financial source qualification
remain separate controls.

See the [ownership and validation notes](https://github.com/sgajbi/lotus-core/blob/main/docs/operations/analytics-export-tenant-custody.md)
for the supported ownership premise, refusal behavior and PostgreSQL evidence boundary.
