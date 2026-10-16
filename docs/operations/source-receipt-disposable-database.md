# Operator-owned source-receipt database qualification

The `operator-source-receipt-db/v1` candidate profile runs only the source-receipt
HTTP/process test on Windows. Offline admission and native process controls do not
qualify PostgreSQL, production lifespans, a bank feed or a compatible financial cut.
Actual database qualification requires separate operator provisioning and finite
runtime admission. No default CI-managed Compose behavior is replaced.

The supported operator host and complete native provenance unit controls require Git
**2.50.1 or newer** on developer and CI hosts. Native tests check the actual binary,
fail explicitly on unsupported versions, and never spoof a new version or silently skip
these controls. This covers local unit/warning/coverage commands, Feature warning-gate,
PR unit coverage and main unit coverage. Existing hosted lanes exercise the prerequisite;
no Git installer or workflow provisioning exception is required. Git 2.50.1 is the
tested minimum, not a claim about the first release of any option. A fixed read-only
`git --version` observation must pass before version-dependent options are used.
Older, malformed and prerelease version strings refuse before repository imports,
private input or resource work, retaining the original deadlines and capture bounds.

The operator provisions a disposable database and least-privilege role on the
existing PostgreSQL server. The runner never creates/drops databases or roles,
initializes/migrates public, operates Docker lifecycle, changes a parent reservation
or retries a failed experiment. The closed #824 broad cleanup capability remains
separate; this profile issues only an exact-schema capability.

## Reviewed inputs

A credential-free JSON admission file and a separately reviewed SHA256 are required.
Its exact keys are validated by `validate_admission` in
`tests/test_support/operator_source_database.py`:

| Fields | Required binding |
| --- | --- |
| `profile`, `repository` | `operator-source-receipt-db/v1`, `sgajbi/lotus-core` |
| `source_sha`, `source_tree` | Exact clean committed execution checkout; no hidden branch import |
| `platform_source_sha` | Independently reviewed full commit SHA for the Platform reservation helper; required without an implicit upgrade of older admissions |
| `nonce`, `database`, `role` | UUID hex32, `core_receipt_db_<nonce>`, `core_receipt_role_<nonce>` |
| `database_oid`, `database_owner_oid`, `role_oid` | Actual OIDs; test role is not database owner |
| `database_marker` | Operator-owned database comment `operator-source-receipt-db/v1:<nonce>:<role_oid>` |
| `host`, `port` | Entire published binding list contains exactly one `127.0.0.1` endpoint at the admitted port |
| `server_address`, `server_port`, `server_birth` | Actual PostgreSQL server address, port and aware postmaster start time |
| `container_id`, `container_birth` | Exact running Docker container ID and start identity |
| `parent_lease`, `parent_holder`, `scope_digest`, `bindings_digest` | Current canonical reservation; digests are hex64 without the `sha256:` prefix |
| `issued_at`, `run_deadline`, `cleanup_deadline`, `parent_expiry` | Aware timestamps; at most 900 seconds total, at least 30 seconds reserved for cleanup, inside parent expiry |
| `tls` | Explicit DSN query map: empty for an operator-reviewed local governed default, or `sslmode=require/verify-full` using system trust roots; no policy overrides |
| `prerequisite_sha256` | SHA256 of the exact canonical JSON prerequisite shape described below |
| `operator_isolation_attested` | `true`; operator owns cross-database privilege isolation and credential distribution |
| `cases` | Exact ordered inventory of allowed node, UUID schema, marker, 14 HTTP calls and four API process generations per case |

Each schema is predeclared as `core1227_<uuid32>`, with marker
`core1227-owned:<nonce>:<schema>`. Current cash-only source has one unparameterized
case. A source containing the reviewed cash/funding parameterization requires the
two exact ordered `[cash]`, `[funding_investment]` cases. Mixed source/inventory is
refused; the runner does not cherry-pick another branch or broaden selection.
Its synthetic tenant and portfolio IDs are deterministically `observation-<uuid32>`
and `portfolio-<uuid32>` from that predeclared schema suffix. Counters retain the
actual API-generation PIDs and loopback ports; parent/recovery process exits and
PIDs remain distinct from API generations.

The operator initializes only `public.portfolios`, `public.ingestion_jobs` and
`public.ingestion_ops_control` prerequisites through a separately admitted process.
The test role has CONNECT and schema CREATE in this database and SELECT on those
tables. Revoke effective public CREATE, prerequisite mutation/ownership, all public
sequence privileges and role memberships, including privileges inherited through
PUBLIC. Require non-superuser/non-CREATEDB/non-CREATEROLE/non-replication/non-BYPASSRLS.
The profile checks actual effective privileges, database/role OIDs, equal session
and current user, operator-owned marker, birth and source-owned column shape before
DDL. These checks do not establish hostile-code isolation or institutional trust.

Container qualification checks the complete PostgreSQL published binding list, not a
filtered subset. Wildcard, additional external or loopback, IPv6 and malformed bindings
are refused before engine creation; container ID, running state and birth pins still apply.
The DDL fence admits one complete statement from the fixed fixture/c178/c181 families,
including only the declared parent clone/ALTER forms. Extra top-level statements,
comment-masked tails and malformed quotes, dollar delimiters or parentheses are refused
before driver dispatch. Ordinary quoted semicolons and the three approved `$$` function
bodies retain their internal semicolons/comments; they are not statement separators.
These offline guard controls do not qualify PostgreSQL or expand cleanup authority.

The prerequisite digest uses `digest(shape)`: sorted-key compact JSON of each table's
ordered `(name, PostgreSQL-compiled type, nullable)` columns and SQLAlchemy inspector
check, primary-key, unique and foreign-key constraint structures. The source-owned
ORM column identity is checked independently. Operator review must retain the actual
catalog observation; an authored digest alone is insufficient evidence.

## Invocation

Working directory: the clean, signed, explicitly admitted `lotus-core` execution
checkout. Set `LOTUS_WORKSPACE_ROOT` to the directory holding the canonical Platform
checkout. A private UTF-8 input file contains exactly one `database_url` key; keep it
outside source/evidence/artifacts, readable only by the operator, and delete it using
the operator's secret lifecycle. Credentials are never accepted in command arguments
or generic inherited DSN variables. Clear inherited PG*, HOST_DATABASE_URL,
DATABASE_URL, POSTGRES_*/Compose target variables, PYTEST_ADDOPTS/PYTEST_PLUGINS
and Python import/startup/home overrides first. Remove all inherited `DOCKER_*` and `GIT_*` variables as
well, including empty values: repository/worktree discovery, index/object storage
and configuration inputs must not redirect the source check. Windows case variants
are refused too. The runner refuses before source-identity Git observation with a
credential-free inherited-override failure; it never echoes variable names or values
or changes global Git configuration. The owned observation receives the exact
environment snapshot that passed this guard.

Docker observations always use `--context default`. Before container inspection,
the profile projects only the context's public Docker endpoint and requires exactly
`npipe:////./pipe/docker_engine`, the reviewed Windows local default pipe. Remote
TCP/SSH endpoints, other pipes, malformed observations and client overrides are refused.
Each fixed native observation retains the5s/65536-byte bounds. Admission and the
private DSN must both use exactly `127.0.0.1`; `localhost`, IPv6 and other aliases
cannot substitute for the inspected single IPv4 binding.

The first trusted instruction is the fixed stdlib `-I -B -c` seed in an independently
reviewed Makefile export, under the separately qualified Python interpreter. Supply
`SOURCE_RECEIPT_BOOTSTRAP_BLOB` independently from the Root-reviewed signed source
inventory's committed CLI blob. Do not obtain the seed or expected pin by importing the
working CLI, reading unqualified HEAD, or accepting inherited environment values.
The Make recipe accepts the public pin only as an explicit command-line assignment.
The trusted initial host/launcher includes Make startup configuration; clear inherited
Make injection/option variables before selecting the independently verified export.
An unverified working Makefile and direct working-script execution are unsupported.
The seed reads the CLI once within the existing source bound, verifies its normalized
Git blob identity, then executes those captured bytes. The verified CLI cross-checks
that public pin against the admitted source commit before runtime imports or private input.
It validates isolation and the profile environment before
first-party imports or private input. A small stdlib-only bootstrap exception performs
fixed read-only Git observations with the original deadline,5s/65536-byte bounds,
disabled fsmonitor/clean filters and optional index locks. Git is explicitly anchored
to the physical checkout, so local `core.worktree` cannot substitute another directory.
Replacement objects and lazy fetching from promisor remotes are disabled.
Only absent/empty or the
exact ordered current-checkout canonical `PYTHONPATH` is accepted; arbitrary tails
and reordered roots are refused. The bootstrap reuses the repository's canonical
roots and first-party import fence. Normal, recovery and API children receive already
qualified CLI/API snapshots on the existing owned stdin pipe. The trusted seed consumes
a closed 12-byte length prefix and captured source with its own finite5s startup deadline;
it never reopens a working script for execution. CLI source authenticates before execution;
API source authenticates against admitted committed identity before its first instruction.
The complete public prefix plus private launch envelope must fit the original65536-byte
budget before a suspended process resumes. The unchanged private envelope then checks
controller/created identities, Job and pipe before JSON decoding. API reads its exact
envelope length and keeps stdin open for the existing stop line. Retirement/drain,
source-file limits and production admission deadlines remain unchanged.
Operator readiness independently checks the reported live worker with limited-access
process handles against the exact held API Job. This admits the reviewed interpreter's
intermediate worker without relying on a reported parent or membership in an unrelated Job.
PID type/range, process/image identities and a finite5s deadline must qualify; ordinary
mode retains exact created-PID equality. This resource-free custody proof does not replace
full HTTP/database acceptance.
The selected interpreter's complete actual launch chain must first pass a separately
reviewed resource-free exact-Job capability qualification, including a created/intermediate
worker, unrelated-Job rejection, held-identity terminal evidence and stream draining.
Version/supplier identity alone is insufficient. An incapable launch refuses; do not substitute
an interpreter automatically or use path-name heuristics. A separately qualified task runtime
does not qualify the operator's interpreter/dependencies or admit a real private invocation.
The profile verifies imported Core source against admitted committed blobs and compiles
that source directly. Normal cache files remain, but ignored sourceless bytecode,
packages, namespaces and transitive dependency shadows cannot execute. Public `--help`
exits using only the standard library and does not establish source qualification.
The fixed profile also verifies both directly executed migration sources, c178 and
c181, during bootstrap. Operator fixtures execute a verified source snapshot rather
than reopening the pathname through `runpy`; `skip-worktree` or `assume-unchanged`
cannot admit altered migration code. Execution preserves the original module globals,
filename and Alembic operations binding. A valid snapshot may exceed the Git observation
capture limit without increasing that limit; the existing source-file bound still applies.
Ordinary fixture aliases and SQL/DDL clauses remain unchanged.
`PYTHONUSERBASE` is inert only when the actual interpreter `no_user_site` flag is1;
the guard never resolves/uses its value and removes it from forwarded snapshots.
Otherwise its presence refuses. This admits a value injected by trusted interpreter
startup without enabling user-site packages or adding Store-specific path exceptions.
The qualified venv also disables user-site; no prior userbase-only execution is claimed.

PowerShell on Windows:

```powershell
$sourceReceiptPython = Join-Path $env:LOTUS_WORKSPACE_ROOT 'lotus-core/.venv/Scripts/python.exe'
# Review the selected interpreter/version separately; the qualified local Core interpreter is3.11.9.
$env:PATH = (Split-Path $sourceReceiptPython) + [IO.Path]::PathSeparator + $env:PATH
Remove-Item Env:MAKEFILES, Env:MAKEFLAGS, Env:GNUMAKEFLAGS, Env:MFLAGS -ErrorAction SilentlyContinue
# Stand in the admitted candidate checkout. $reviewedMakefile is the independently verified export.
# $reviewedBootstrapBlob is the separately Root-reviewed committed CLI blob, never working-file-derived.
Get-Content -LiteralPath $privateConnectionFile -Raw | make --file=$reviewedMakefile qualify-source-receipts "SOURCE_RECEIPT_BOOTSTRAP_BLOB=$reviewedBootstrapBlob" "SOURCE_RECEIPT_ADMISSION=$admissionFile" "SOURCE_RECEIPT_ADMISSION_SHA256=$reviewedAdmissionSha256" "LOTUS_WORKSPACE_ROOT=$env:LOTUS_WORKSPACE_ROOT"
if ($LASTEXITCODE -ne 0) { throw 'Source receipt qualification failed or refused' }
```

Bash on Windows using a native Windows Python interpreter, from the same checkout:

```bash
source_receipt_python="$LOTUS_WORKSPACE_ROOT/lotus-core/.venv/Scripts/python.exe"
export PATH="$(dirname "$source_receipt_python"):$PATH"
unset MAKEFILES MAKEFLAGS GNUMAKEFLAGS MFLAGS
# Stand in the admitted candidate checkout; use the independently verified Makefile export.
make --file="$reviewed_makefile" qualify-source-receipts \
  SOURCE_RECEIPT_BOOTSTRAP_BLOB="$reviewed_bootstrap_blob" \
  SOURCE_RECEIPT_ADMISSION="$admission_file" \
  SOURCE_RECEIPT_ADMISSION_SHA256="$reviewed_admission_sha256" \
  LOTUS_WORKSPACE_ROOT="$LOTUS_WORKSPACE_ROOT" < "$private_connection_file"
```

The supported entry uses the independently verified Makefile export as above, with
`SOURCE_RECEIPT_BOOTSTRAP_BLOB`, `SOURCE_RECEIPT_ADMISSION`, `SOURCE_RECEIPT_ADMISSION_SHA256` and
`LOTUS_WORKSPACE_ROOT` set explicitly and private stdin redirected as above.
Activate the reviewed interpreter so Make's `python` selects that same executable;
the profile-specific recipe contains the fixed stdlib seed, encoded literally for portable
shell quoting. Its decoded text is `SOURCE_SEED` in the reviewed CLI source. The ordinary
repository Python launcher and other Make recipes retain their existing behavior.
Linux/macOS custody is unsupported and refused before SQL. Commands are source
interfaces; actual invocation against PostgreSQL remains subject to runtime admission.

In operator mode, the HTTP test launches its API descendant with the trusted seed and
verified captured source. It applies the same source provenance policy before reading
the private descriptor or importing application dependencies. Ordinary test mode retains
its module entry. Direct imports of internal runner
functions, including external adapters, do not earn the supported isolated-entry proof
and need separate reviewed invocation/environment integration before live admission.

Case-insensitive collision refusal applies only to existing protected Git/Docker/PG/Python
families, explicit overrides and repository-root authority. Unrelated POSIX pairs such as
`HTTP_PROXY`/`http_proxy` remain accepted with both original names and values unchanged.
These controls assume a cooperative trusted host and reviewed initial launcher; they do
not attest a hostile host or authorize any obsolete invocation, private packet or live run.

Core qualification precedes loading the reservation helper. `--workspace-root` must
identify the directory containing Core's actual common primary checkout and the sibling
`lotus-platform`, including when execution uses a managed Core worktree. Platform HEAD
must equal `platform_source_sha`; the helper's normalized working bytes must match its
committed blob, and only the committed bytes execute. The reservation's Core and Platform
project paths and Platform source pin must match these qualified checkouts. Its canonical
Core source pin may differ from the candidate Core source. Reservation reads remain read-only.

The guarantee assumes a trusted cooperative Windows host, selected interpreter/venv,
installed startup hooks, Git/Docker executables and stable default-context configuration.
It does not sandbox hostile host code or cryptographically attest the local container
to the PostgreSQL peer. Offline controls and a public context observation are not a
live financial qualification.

## Custody, evidence and recovery

The child command and pytest plugins are fixed internally; inherited overrides,
extra tests, broad cleanup and Compose fixtures are refused. Application imports
follow admission; managed port/DSN preparation is skipped only for an issued profile.
Governed factories retain transport policy, NULL pools, two-second connection,
five-second statement/idle bounds and one-second lock waits. TLS policy is never
disabled by this runner. Exact schema creation is transactional and actual immutable
observation/receipt migrations run only there.

Windows creates each supervised child suspended, assigns it to a kill-on-close Job
Object without breakaway, then resumes it. Output is drained and discarded under a
64KiB limit. Private input is bounded to 64KiB/five seconds. The fixed pytest child
and, if needed, one fixed recovery child each have finite custody; native API
descendants remain within that job. This supports pinned cooperative source, not
arbitrary hostile code. HTTP/process counters in parent-created nonsecret per-case
files enforce admission and make attempted overruns fail the final receipt.
Twenty seconds of each remaining admission window are reserved for process retirement
and drain; insufficient remaining time refuses another child. These are finite
software budgets, not a hard operating-system scheduling or PostgreSQL rollback SLO.
Custom TLS root-file parameters are unsupported and refused before SQL; TLS modes
are mapped explicitly between psycopg2 and asyncpg without relaxing their mode.

Recovery uses the predeclared inventory, a fresh process-local schema capability and
fresh read-only target handshake. It has at most the remaining cleanup window/60
seconds under its own Job Object. No capability is decoded from child output. Only
the exact marker/owner/schema may be dropped; absent is distinct from removed.
Expired/foreign/uncertain identity or unconfirmed process retirement leaves explicit
residue for the operator. The original test/process failure cannot become success
because cleanup passed. Parent database/role teardown remains operator-owned.

The credential-free final receipt distinguishes exact source, native producer exit,
timeout/output bound, stream/custody retirement, per-case counts and cleanup results.
Retain native logs/receipts and exact cleanup evidence under the approved private
evidence boundary. Green offline tests or collection alone are not live acceptance.
