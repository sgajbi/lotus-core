# CR-347 Page Token Codec Boundary Review

Date: 2026-05-27

## Scope

Reviewed signed pagination token encode/decode logic inside `IntegrationService`.

## Findings

`IntegrationService` owned HMAC signing, base64 envelope encoding, signature verification, malformed
token handling, and the source-data methods that consume those tokens. This was a self-contained
security-sensitive utility concern embedded inside the largest query-service module.

Direct tests also exposed that malformed base64 could leak a raw decode error rather than the
bounded malformed-token error expected by the service contract.

## Actions Taken

Extracted signed page-token behavior into
`src/services/query_service/app/services/page_token_codec.py`.

`IntegrationService` now owns service-level pagination flow and delegates token encoding/decoding to
`PageTokenCodec`. Existing protected wrapper methods remain so current internal call sites and
tests keep their service-level shape while the implementation is modular.

Added focused tests for:

1. signed payload round trip,
2. wrong-secret signature rejection,
3. empty token handling,
4. malformed token rejection through a bounded `ValueError`.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/query_service/services/test_page_token_codec.py tests/unit/services/query_service/services/test_integration_service.py -q
96 passed

python -m ruff check src/services/query_service/app/services/integration_service.py src/services/query_service/app/services/page_token_codec.py tests/unit/services/query_service/services/test_page_token_codec.py tests/unit/services/query_service/services/test_integration_service.py
All checks passed
```

## Follow-Up

No API or wiki source change is required for this slice because public pagination contracts did not
change. Continue extracting reusable integration-service helpers where they are self-contained and
security- or correctness-sensitive.
