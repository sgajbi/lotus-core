# Core CI image acquisition

Core consumes the existing Platform image-acquisition validator from qualified commit
`0c96dd9ea00d1222e35d3e7d14de6a540a222104` through
`.github/actions/acquire-images`. Platform owns admission, publisher mappings, metadata verification
and bounded retry behavior. Core's binding adapter transports successful exact outputs into native
commands; it does not implement another admission policy or registry fallback.

## Fixed identities and boundaries

| Input | Distribution | Immutable root |
| --- | --- | --- |
| Python 3.11 slim Bookworm | `public.ecr.aws/docker/library/python` | `sha256:97b0eafb29f5ebfba254be840115b2f3bc24ff6ff3de9b905e04b74ee7227ba6` |
| PostgreSQL 16 Alpine | `public.ecr.aws/docker/library/postgres` | `sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` |
| Prometheus 2.47.2 | `quay.io/prometheus/prometheus` | `sha256:3002935850ea69a59816825d4cb718fafcdb9b124e4e6153ebc6894627525f7f` |
| Trivy 0.56.2 | `ghcr.io/aquasecurity/trivy` | `sha256:26245f364b6f5d223003dc344ec1eb5eb8439052bfecb31d79aeba0c74344b3a` |

The action checks out the fixed Platform revision without persisted credentials, performs live
native verification for each required tuple on `linux/amd64`, and exports bindings only after every
required acquisition check succeeds. Native failure evidence is retained as a workflow artifact.
Invalid output, a different governance revision or a different image override fails closed. Core
adds no retry layer around the native validator.

Python acquisition precedes Linux runtime/tooling lock replay and base-image metadata verification,
as well as all runtime and release builds. All ten Dockerfiles retain their original fixed Python
declaration and consume the same qualified `PYTHON_IMAGE` build argument in both build stages.
The original publisher lifecycle inventory remains authoritative; build evidence separately records
the acquired distribution. Registry evidence checking compares the frozen source bytes against the
selected distribution and logs the actual metadata acquisition reference.

Compose acquisition precedes native database, smoke and runtime validation. Its two qualified image
substitutions are resolved consistently in image preparation and Compose startup, including an
isolated runtime environment. All five non-build Compose images remain enumerated. The same fixed
Python binding reaches Compose builds. No health checks, ports, test workloads, security gates or
runtime image-set source/lock/Compose verification are removed.

Release and diagnostic builds consume the qualified Python output. Version probing, vulnerability
and secret scans, and release SBOM export all consume the qualified Trivy output. Scanner version,
digest, KEV, exception and receipt enforcement remain intact. Public publisher distributions do
not require a new registry account. Hosted Docker acquisition and complete CI success still require
their own actual receipts; metadata verification alone does not certify layers or release readiness.

## Owner-provisioned DockerHub capacity

Kafka `confluentinc/cp-kafka:7.5.0`, ZooKeeper `confluentinc/cp-zookeeper:7.5.0` and
Grafana `grafana/grafana:10.1.5` have no admitted alternative in this Core adoption. Compose jobs
therefore require these repository Actions secrets, provisioned by the accountable operator:

- `DOCKERHUB_USERNAME`: the intended publisher-registry read account.
- `DOCKERHUB_READ_TOKEN`: that account's correctly scoped read-only DockerHub token.

Both references are explicit on the owning workflow steps. Missing or partial credentials fail
before Compose acquisition. Login passes the token only through stdin, bounds authentication to
60 seconds and suppresses credential-bearing process output on failure. No GitHub token or branch
protection token is reused. Operators must establish account rights and available pull capacity;
the software cannot infer those from the existence of a secret name. No account, credential or
operator image copy is created by this change.

An owner-approved operator copy requires separate destination ownership/rights, a reviewed immutable
copy-tool pin, exact index/child/config/layer preservation proof, package read access and Platform
admission before use. The Confluent design proposal under Platform #945 is not publication authority.
Do not skip these three inputs, run anonymous retry loops, change image versions or substitute
another distribution to make a gate green.

## Focused verification

Working directory: the `lotus-core` checkout. These commands exercise command capture and both valid
and failing binding/authentication controls without pulling images or starting containers.

PowerShell:

```powershell
python scripts/development/repository_python.py -m pytest tests/unit/scripts/test_image_acquisition_bindings.py tests/unit/test_support/test_docker_stack.py tests/unit/test_image_release_workflow.py -q -W error
```

Bash:

```bash
python scripts/development/repository_python.py -m pytest tests/unit/scripts/test_image_acquisition_bindings.py tests/unit/test_support/test_docker_stack.py tests/unit/test_image_release_workflow.py -q -W error
```

The protected workflows subsequently prove actual runner acquisition and native validation. Keep
failed historical cohorts failed; record fresh current-head evidence independently. Missing
operator configuration remains a blocker to complete Core #1004 / PR #1255 qualification.
