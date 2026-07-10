# Transaction Processing Kubernetes Base

The base contains the hardened `portfolio-transaction-processing` Deployment, ServiceAccount,
Service, and disruption budget. The checked-in image uses an all-zero digest placeholder and must
not be applied directly.

Render it from the CI image-release manifest:

```bash
python scripts/render_transaction_processing_deployment.py \
  --release-manifest output/build-evidence/portfolio_transaction_processing_service-image-release-manifest.json \
  --output output/deployment/portfolio-transaction-processing.yaml
kubectl apply -f output/deployment/portfolio-transaction-processing.yaml
```

The renderer fails unless the manifest proves SBOM generation, passed vulnerability scanning,
signature, provenance, digest deployment, and one identical digest for dev, UAT, and prod. Supply
`lotus-core-database` Secret key `database-url` and `lotus-core-runtime` ConfigMap key
`kafka-bootstrap-servers` before deployment. Complete the governed Kafka offset handoff before the
first target pod starts.
