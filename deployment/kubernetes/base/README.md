# Release-Managed Kubernetes Base

The base contains hardened deployments for `portfolio-transaction-processing` and
`portfolio-derived-state`. Checked-in images use all-zero digest placeholders and must not be
applied directly.

Render it from the CI image-release manifest:

```bash
python scripts/release/render_release_deployment.py \
  --service portfolio_transaction_processing_service \
  --release-manifest output/build-evidence/portfolio_transaction_processing_service-image-release-manifest.json \
  --output output/deployment/portfolio-transaction-processing.yaml
kubectl apply -f output/deployment/portfolio-transaction-processing.yaml

python scripts/release/render_release_deployment.py \
  --service portfolio_derived_state_service \
  --release-manifest output/build-evidence/portfolio_derived_state_service-image-release-manifest.json \
  --output output/deployment/portfolio-derived-state.yaml
kubectl apply -f output/deployment/portfolio-derived-state.yaml
```

The renderer fails unless the manifest proves SBOM generation, passed vulnerability scanning,
signature, provenance, digest deployment, and one identical digest for dev, UAT, and prod. Supply
the following configuration before deployment:

- `lotus-core-database` Secret key `database-url` with a non-default credential;
- `lotus-core-runtime` ConfigMap keys `environment` and `kafka-bootstrap-servers`;
- `lotus-core-kafka` Secret keys `sasl-username` and `sasl-password`;
- `lotus-core-kafka-trust` Secret key `ca.pem` containing the broker CA bundle.

The base deliberately fixes promoted Kafka transport to `SASL_SSL` with `SCRAM-SHA-512` and mounts
the CA read-only. Missing release authority prevents pod startup; it never falls back to app-local
plaintext. Complete the governed Kafka offset handoff before the first target pod starts.
