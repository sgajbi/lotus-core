# RFC-087 Slice 1 Platform Scaffold Evidence

| Field | Value |
| --- | --- |
| RFC | RFC-087 - DPM Source Data Products for lotus-manage Stateful Execution |
| Slice | Slice 1 - Platform automation and scaffolding improvement |
| Platform branch | `lotus-platform:feat/rfc087-source-product-scaffolding` |
| Platform commit | `ec83905` |
| Status | Implemented, pushed, and remote Feature Lane run `25240166850` completed successfully. |

## Implemented Platform Improvement

Slice 1 found that `lotus-platform` already had domain-product onboarding scaffolding for
producer declarations, trust telemetry, SLO, access, evidence policy, README, and checklist files,
but it did not scaffold the source-data API and ingestion-certification material required by
RFC-087.

The platform scaffold now generates and validates these additional artifacts for every new
source-data product onboarding bundle:

1. `contracts/source-data-products/<product>.api-profile.v1.json`
   Source API profile covering ingestion, serving API, certification, and downstream consumption
   posture.
2. `docs/API-CERTIFICATION-CHECKLIST.md`
   Endpoint certification checklist covering OpenAPI, request/response attributes, output-family
   proof, error examples, non-functional proof, security, observability, and live canonical
   evidence.
3. `docs/INGESTION-PIPELINE-CHECKLIST.md`
   Ingestion checklist covering authoritative source systems, identifier mapping, idempotency,
   source-batch lineage, reconciliation, runtime telemetry, and canonical demo seed-data readiness.

The generator validation now rejects a source API profile that weakens mandatory certification
controls such as mesh certification, trust telemetry, OpenAPI quality, domain-product validation,
or live canonical evidence.

## Documentation And Wiki Updates

The platform branch updated:

1. `platform-contracts/domain-data-products/README.md`,
2. `context/CONTEXT-REFERENCE-MAP.md`,
3. `context/LOTUS-ENGINEERING-CONTEXT.md`,
4. `wiki/Enterprise-Mesh-Status.md`,
5. `wiki/Validation-and-CI.md`.

`Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-platform` reports expected publication drift for
the changed repo-authored wiki pages. Publication must happen after merge to `main`.

## Validation Evidence

Focused platform validation:

```powershell
python -m pytest tests/unit/test_domain_product_onboarding_generator.py -q
python -m pytest tests/unit/test_domain_product_onboarding_generator.py tests/unit/test_domain_product_discovery_generator.py tests/unit/test_engineering_context_system_contract.py -q
python -m ruff check automation/generate_domain_product_onboarding.py tests/unit/test_domain_product_onboarding_generator.py
python -m ruff format --check automation/generate_domain_product_onboarding.py tests/unit/test_domain_product_onboarding_generator.py
```

Observed result:

1. `5 passed` for focused onboarding generator tests.
2. `28 passed` for onboarding, generated discovery, and engineering context tests.
3. ruff check and format checks passed.

Scaffold proof:

```powershell
$dir = Join-Path $env:TEMP "lotus-platform-source-product-scaffold-proof"
python automation/generate_domain_product_onboarding.py --repository lotus-core --product-name DiscretionaryMandateBinding --product-version v1 --authoritative-domain portfolio_management --product-family dpm_source_data --output-directory $dir
python automation/generate_domain_product_onboarding.py --repository lotus-core --product-name DiscretionaryMandateBinding --product-version v1 --output-directory $dir --check
```

Observed result:

1. generated 10 onboarding files,
2. check command exited successfully.

Full local platform Feature Lane:

```powershell
powershell -ExecutionPolicy Bypass -File automation\Invoke-PlatformRepoChecks.ps1 -Lane feature
```

Observed result:

1. `478 passed`,
2. engineering context, agent engineering, heartbeat, skill alignment, analytics observability,
   scaffold CI enforcement, container baseline, and platform validation coverage contracts passed,
3. mesh certification advisory mode certified with zero errors, zero warnings, and zero info
   issues.

## Slice Exit Assessment

Slice 1 is complete. RFC-087 implementation can use the platform scaffold for future DPM
source-data products instead of creating one-off local boilerplate in `lotus-core`. The
`lotus-platform` Feature Lane for commit `ec83905` finished green.
