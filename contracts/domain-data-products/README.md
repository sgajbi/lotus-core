# Lotus Core Domain Data Product Declarations

This directory stores `lotus-core` repo-native declarations for governed Lotus domain data
products.

The platform-owned schemas, vocabulary registries, and cross-repository validators remain in
`lotus-platform`. This repository owns the producer declaration content for the products it
publishes.

Current declarations:

1. `lotus-core-products.v1.json`
   Producer declaration for the governed RFC-0083 source-data product catalog.

Local validation:

```powershell
python scripts/validate_domain_data_product_contracts.py
```

Make target:

```powershell
make domain-product-validate
```

Governance rules:

1. declaration product names, versions, routes, consumers, and serving-plane metadata must align
   with `src/libs/portfolio-common/portfolio_common/source_data_products.py`,
2. security profile references must align with
   `src/libs/portfolio-common/portfolio_common/source_data_security.py`,
3. platform validation runs when a sibling `lotus-platform` checkout is available,
4. tests must keep repo-native declaration truth synchronized with the live source-data product
   catalog.
