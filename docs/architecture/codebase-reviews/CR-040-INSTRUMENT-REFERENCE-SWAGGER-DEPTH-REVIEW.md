# CR-040 Instrument Reference Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the Swagger/OpenAPI contract for the instrument reference endpoint in `query_service`:

- `GET /instruments/`

## Findings

- The endpoint already had the correct response model and pagination contract.
- The remaining gap was twofold:
  - router-level filter docs were still thin
  - the shared `InstrumentRecord` schema lacked field-level descriptions/examples for the richer
    FX-aware attributes now present in the API
- This made Swagger valid but not sufficient for consumers trying to understand the meaning of the
  extended instrument fields.

## Actions Taken

- Added explicit descriptions/examples for the instrument query filters:
  - `security_id`
  - `product_type`
- Added field-level descriptions/examples across `InstrumentRecord`, including the FX contract
  fields.
- Added an OpenAPI integration assertion that locks the richer instrument contract in place.

## Follow-up

- Continue the same depth pass on any remaining thinner API surfaces, especially where shared DTOs
  carry domain-rich fields without descriptions.

## Evidence

- `src/services/query_service/app/routers/instruments.py`
- `src/services/query_service/app/dtos/instrument_dto.py`
- `tests/integration/services/query_service/test_main_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
