"""One operator-admitted disposable database; no managed-Compose cleanup authority."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import types
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from scripts.validation.qualify_source_receipts import OVERRIDES as OVERRIDES
from scripts.validation.qualify_source_receipts import (
    ROOT,
    EnvironmentRefused,
    SourceProvenance,
    read_admission,
    validate_environment,
)

PROFILE = "operator-source-receipt-db/v1"
NODE = (
    "tests/integration/services/query_control_plane_service/"
    "test_source_receipt_http_restart_postgresql.py::"
    "test_registered_receipt_http_restart_keeps_original_and_corrected_pins"
)
TABLES = ("portfolios", "ingestion_jobs", "ingestion_ops_control")
_session = None
_issued = {}
_fences = {}
_TOKEN = object()


class ProfileRefused(RuntimeError):
    def __init__(self, code="SOURCE_RECEIPT_PROFILE_REFUSED"):
        super().__init__(code)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def unique_fields(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ProfileRefused("SOURCE_RECEIPT_DUPLICATE_FIELD")
        result[name] = value
    return result


def observe(command, root=None, *, environment=None, deadline=None):
    environment = dict(os.environ if environment is None else environment)
    deny_overrides(environment)
    from tests.test_support.source_receipt_process_custody import run_owned

    captured = bytearray()
    remaining = 5 if deadline is None else min(5, deadline - time.time())
    if remaining <= 0:
        raise ProfileRefused("SOURCE_RECEIPT_ADMISSION_EXPIRED")
    receipt = run_owned(
        command,
        private_input=b"",
        environment=environment,
        cwd=root,
        timeout=remaining,
        output_limit=65536,
        stdout_capture=captured,
    )
    if (
        receipt.exit_code
        or receipt.timed_out
        or receipt.output_limit_exceeded
        or not receipt.descendants_retired
        or not receipt.streams_drained
    ):
        raise ProfileRefused("SOURCE_RECEIPT_OBSERVATION_REFUSED")
    return bytes(captured)


def instant(value):
    try:
        result = datetime.fromisoformat(value)
        if result.utcoffset() is None:
            raise ValueError
        return result.timestamp()
    except (ValueError, TypeError):
        raise ProfileRefused("SOURCE_RECEIPT_TIME_INVALID") from None


def deny_overrides(environment):
    try:
        validate_environment(environment)
    except EnvironmentRefused as error:
        raise ProfileRefused(error.args[0]) from None


def load_admission(path, expected_hash):
    try:
        return read_admission(path, expected_hash)
    except EnvironmentRefused as error:
        raise ProfileRefused(error.args[0]) from None


def validate_admission(value, *, now, environment, platform, cleanup_mode=False):
    deny_overrides(environment)
    if platform != "nt":
        raise ProfileRefused("SOURCE_RECEIPT_WINDOWS_REQUIRED")
    required = {
        "profile",
        "repository",
        "source_sha",
        "source_tree",
        "platform_source_sha",
        "nonce",
        "database",
        "database_oid",
        "database_owner_oid",
        "role",
        "role_oid",
        "host",
        "port",
        "server_address",
        "server_port",
        "server_birth",
        "container_id",
        "container_birth",
        "parent_lease",
        "parent_holder",
        "scope_digest",
        "bindings_digest",
        "issued_at",
        "run_deadline",
        "cleanup_deadline",
        "parent_expiry",
        "database_marker",
        "prerequisite_sha256",
        "cases",
        "tls",
        "operator_isolation_attested",
    }
    if type(value) is not dict or set(value) != required:
        raise ProfileRefused("SOURCE_RECEIPT_ADMISSION_SHAPE")
    if value["profile"] != PROFILE or value["repository"] != "sgajbi/lotus-core":
        raise ProfileRefused("SOURCE_RECEIPT_PROFILE_IDENTITY")
    nonce = value["nonce"]
    if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise ProfileRefused("SOURCE_RECEIPT_NONCE_INVALID")
    if (
        value["database"] != "core_receipt_db_" + nonce
        or value["role"] != "core_receipt_role_" + nonce
    ):
        raise ProfileRefused("SOURCE_RECEIPT_TARGET_INVALID")
    for name in ("source_sha", "source_tree", "platform_source_sha"):
        if not isinstance(value[name], str) or not re.fullmatch(r"[0-9a-f]{40}", value[name]):
            raise ProfileRefused("SOURCE_RECEIPT_SOURCE_INVALID")
    for name in ("scope_digest", "bindings_digest", "prerequisite_sha256", "container_id"):
        if not isinstance(value[name], str) or not re.fullmatch(r"[0-9a-f]{64}", value[name]):
            raise ProfileRefused("SOURCE_RECEIPT_DIGEST_INVALID")
    if value["host"] != "127.0.0.1":
        raise ProfileRefused("SOURCE_RECEIPT_ENDPOINT_INVALID")
    for name in ("port", "server_port", "database_oid", "database_owner_oid", "role_oid"):
        if type(value[name]) is not int or value[name] <= 0:
            raise ProfileRefused("SOURCE_RECEIPT_OID_PORT_INVALID")
    if value["port"] > 65535 or value["server_port"] > 65535:
        raise ProfileRefused("SOURCE_RECEIPT_ENDPOINT_INVALID")
    for name in ("parent_lease", "parent_holder", "server_address"):
        if not isinstance(value[name], str) or not 1 <= len(value[name]) <= 160:
            raise ProfileRefused("SOURCE_RECEIPT_PARENT_SERVER_INVALID")
    for name in ("server_birth", "container_birth"):
        if instant(value[name]) > now:
            raise ProfileRefused("SOURCE_RECEIPT_BIRTH_INVALID")
    issued, run, cleanup, parent = (
        instant(value[name])
        for name in ("issued_at", "run_deadline", "cleanup_deadline", "parent_expiry")
    )
    permitted_end = cleanup if cleanup_mode else run
    if not (
        issued <= now < permitted_end
        and issued < run < cleanup <= parent
        and cleanup - issued <= 900
        and cleanup - run >= 30
    ):
        raise ProfileRefused("SOURCE_RECEIPT_ADMISSION_EXPIRED")
    if value["operator_isolation_attested"] is not True:
        raise ProfileRefused("SOURCE_RECEIPT_ISOLATION_UNPROVEN")
    if value["database_owner_oid"] == value["role_oid"]:
        raise ProfileRefused("SOURCE_RECEIPT_DATABASE_OWNER_INVALID")
    marker = f"{PROFILE}:{nonce}:{value['role_oid']}"
    if value["database_marker"] != marker:
        raise ProfileRefused("SOURCE_RECEIPT_MARKER_INVALID")
    if not isinstance(value["tls"], dict) or set(value["tls"]) - {"sslmode"}:
        raise ProfileRefused("SOURCE_RECEIPT_TLS_INVALID")
    if value["tls"] and value["tls"].get("sslmode") not in ("require", "verify-full"):
        raise ProfileRefused("SOURCE_RECEIPT_TLS_INVALID")
    cases = value["cases"]
    if type(cases) is not list or not 1 <= len(cases) <= 2:
        raise ProfileRefused("SOURCE_RECEIPT_CASES_INVALID")
    seen = set()
    for case in cases:
        if type(case) is not dict or set(case) != {
            "node",
            "schema",
            "marker",
            "http_calls",
            "processes",
        }:
            raise ProfileRefused("SOURCE_RECEIPT_CASES_INVALID")
        if case["node"] not in (NODE, NODE + "[cash]", NODE + "[funding_investment]"):
            raise ProfileRefused("SOURCE_RECEIPT_NODE_REFUSED")
        if not re.fullmatch(r"core1227_[0-9a-f]{32}", case["schema"]):
            raise ProfileRefused("SOURCE_RECEIPT_SCHEMA_INVALID")
        if case["marker"] != f"core1227-owned:{nonce}:{case['schema']}" or (
            case["http_calls"],
            case["processes"],
        ) != (14, 4):
            raise ProfileRefused("SOURCE_RECEIPT_CASE_BOUNDS")
        if case["node"] in seen or case["schema"] in seen:
            raise ProfileRefused("SOURCE_RECEIPT_CASE_DUPLICATE")
        seen.update((case["node"], case["schema"]))
    return value


def qualify_source(value, root, *, cleanup=False):
    deny_overrides(os.environ)
    try:
        provenance = SourceProvenance(
            value,
            root,
            cleanup=cleanup,
            observe=lambda command, cwd, deadline: observe(command, cwd, deadline=deadline),
        ).qualify()
    except EnvironmentRefused as error:
        raise ProfileRefused(error.args[0]) from None
    source = (Path(root) / NODE.split("::")[0]).read_text()
    expected = (
        [NODE + "[cash]", NODE + "[funding_investment]"]
        if '@pytest.mark.parametrize("family"' in source
        else [NODE]
    )
    if [case["node"] for case in value["cases"]] != expected:
        raise ProfileRefused("SOURCE_RECEIPT_SOURCE_CASE_MISMATCH")
    return provenance


def operator_migration(connection, name):
    """Bind the verified snapshot to the same Alembic operations as the fixed fixture."""
    from scripts.validation.qualify_source_receipts import (
        SOURCE_RECEIPT_MIGRATIONS,
        _active_provenance,
    )

    if _active_provenance is None:
        raise ProfileRefused("SOURCE_RECEIPT_IMPORT_REFUSED")
    try:
        module = _active_provenance.migration(name)
    except EnvironmentRefused as error:
        raise ProfileRefused(error.args[0]) from None
    if (module["revision"], module["down_revision"]) != SOURCE_RECEIPT_MIGRATIONS[name]:
        raise ProfileRefused("SOURCE_RECEIPT_IMPORT_REFUSED")
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
    return module


def qualify_container(value):
    environment = dict(os.environ)
    deny_overrides(environment)
    docker = ["docker", "--context", "default"]
    endpoint = observe(
        docker + ["context", "inspect", "default", "--format", "{{json .Endpoints.docker.Host}}"],
        environment=environment,
    )
    try:
        local = len(endpoint) <= 65536 and json.loads(endpoint) == "npipe:////./pipe/docker_engine"
    except (ValueError, TypeError):
        local = False
    if not local:
        raise ProfileRefused("SOURCE_RECEIPT_DOCKER_ENDPOINT_REFUSED")
    projection = (
        '{"Id":{{json .Id}},"State":{"Running":{{json .State.Running}},'
        '"StartedAt":{{json .State.StartedAt}}},'
        '"NetworkSettings":{"Ports":{{json .NetworkSettings.Ports}}}}'
    )
    result = observe(
        docker + ["inspect", "--format", projection, value["container_id"]], environment=environment
    )
    if len(result) > 65536:
        raise ProfileRefused("SOURCE_RECEIPT_CONTAINER_UNAVAILABLE")
    try:
        actual = json.loads(result)
        bindings = actual["NetworkSettings"]["Ports"][f"{value['server_port']}/tcp"]
        valid = (
            actual["Id"] == value["container_id"]
            and actual["State"]["Running"] is True
            and actual["State"]["StartedAt"] == value["container_birth"]
            and type(bindings) is list
            and len(bindings) == 1
            and type(bindings[0]) is dict
            and bindings[0].get("HostIp") == "127.0.0.1"
            and bindings[0].get("HostPort") == str(value["port"])
        )
    except (ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        raise ProfileRefused("SOURCE_RECEIPT_CONTAINER_MISMATCH")


def _ddl_quote_end(statement, start):
    quote, position = statement[start], start + 1
    while position < len(statement):
        if statement[position] == "\\":
            return None  # The frozen clauses use standard, not backslash-escaped strings.
        if statement[position] == quote:
            if position + 1 < len(statement) and statement[position + 1] == quote:
                position += 2
                continue
            return position + 1
        position += 1
    return None


def _complete_ddl_statement(statement):
    """One closed clause; quoted data/function-body delimiters are not SQL separators."""
    if not isinstance(statement, str) or not statement.strip():
        return None
    statement = statement.strip()
    position, depth, closes, dollar_body = 0, 0, [], False
    while position < len(statement):
        character = statement[position]
        if character in "\"'":
            position = _ddl_quote_end(statement, position)
            if position is None:
                return None
            continue
        if character == "$":
            if (
                dollar_body
                or not statement.startswith("CREATE FUNCTION ")
                or not statement.startswith("$$", position)
            ):
                return None
            end = statement.find("$$", position + 2)
            if end < 0:
                return None
            dollar_body, position = True, end + 2
            continue
        if statement.startswith(("--", "/*"), position):
            return None
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return None
            if depth == 0:
                closes.append(position)
        elif character == ";":
            if depth or statement[position + 1 :].strip():
                return None
            statement = statement[:position].rstrip()
            break
        position += 1
    return None if depth else (statement, closes)


def admitted_ddl(statement, schema, marker, current):
    """Complete frozen fixture/migration grammar, never a generic DDL grant."""
    parsed = _complete_ddl_statement(statement)
    if parsed is None:
        return False
    statement, closes = parsed
    roots = (
        f'CREATE SCHEMA "{schema}" AUTHORIZATION CURRENT_USER',
        f"COMMENT ON SCHEMA \"{schema}\" IS '{marker}'",
        f'DROP SCHEMA "{schema}" CASCADE',
    )
    if statement in roots:
        return True
    parents = "(?:portfolios|ingestion_jobs|ingestion_ops_control)"
    if re.fullmatch(
        rf'CREATE TABLE "{re.escape(schema)}"\.(?P<parent>{parents}) '
        r"\(LIKE public\.(?P=parent) INCLUDING CONSTRAINTS\)",
        statement,
    ):
        return True
    alterations = {
        *(
            f'ALTER TABLE "{schema}".{table} ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY'
            for table in ("portfolios", "ingestion_jobs")
        ),
        *(
            f'ALTER TABLE "{schema}".{table} ADD UNIQUE ({columns})'
            for table, columns in (
                ("portfolios", "tenant_id, portfolio_id"),
                ("ingestion_jobs", "tenant_id, job_id"),
                ("ingestion_jobs", "job_id"),
                ("ingestion_ops_control", "id"),
            )
        ),
        *(
            f'ALTER TABLE "{schema}".{table} ALTER COLUMN {column} SET DEFAULT now()'
            for table, column in (
                ("ingestion_jobs", "submitted_at"),
                ("ingestion_ops_control", "updated_at"),
                ("portfolios", "created_at"),
                ("portfolios", "updated_at"),
            )
        ),
    }
    if statement in alterations:
        return True
    if current != schema:
        return False
    tables = (
        r"portfolio_(?:cash_availability|funding_investment)_(?:observations|observation_heads)"
    )
    tables = rf"(?:{tables}|portfolio_source_fact_verifications)"
    if closes == [len(statement) - 1] and re.fullmatch(
        rf"CREATE TABLE {tables}\s*\(.+\)", statement, re.S
    ):
        return True
    if closes == [len(statement) - 1] and re.fullmatch(
        rf"CREATE INDEX [a-z0-9_]+ ON {tables}\s*\([a-z0-9_, ]+\)", statement
    ):
        return True
    functions = (
        r"(?:reject_portfolio_source_observation_mutation|"
        r"guard_empty_portfolio_source_observation_truncate|refuse_source_fact_verification_mutation)"
    )
    if re.fullmatch(
        rf"CREATE TRIGGER [a-z0-9_]+ BEFORE (?:UPDATE(?: OR DELETE)?|TRUNCATE) ON {tables} "
        rf"FOR EACH (?:ROW|STATEMENT) EXECUTE FUNCTION {functions}\(\)",
        statement,
    ):
        return True
    return bool(
        re.fullmatch(
            rf"CREATE FUNCTION {functions}\(\) RETURNS trigger\s+"
            r"LANGUAGE plpgsql(?: VOLATILE)? AS \$\$.+\$\$",
            statement,
            re.S,
        )
    )


def qualify_parent(value, workspace, *, root=ROOT, cleanup=False):
    try:
        provenance = qualify_source(value, root, cleanup=cleanup)
        primary, platform, helper, source = provenance.platform_helper(workspace)
        module = types.ModuleType("source_receipt_parent_lease")
        module.__file__ = str(helper)
        exec(compile(source, str(helper), "exec"), module.__dict__)
        path = platform / "output/canonical-runtime/reservations.v1.json"
        with path.open("rb") as stream:
            raw = stream.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError
        record = module.current(json.loads(raw))
        valid = (
            record is not None
            and record["id"] == value["parent_lease"]
            and record["holder"] == value["parent_holder"]
            and record["operation"] is None
            and record["scopeDigest"] == "sha256:" + value["scope_digest"]
            and module.digest(record["bindings"]) == "sha256:" + value["bindings_digest"]
            and instant(record["expiryUtc"]) >= instant(value["cleanup_deadline"])
            and Path(record["scope"]["projects"]["lotus-core"]).resolve() == primary
            and record["scope"]["sources"]["lotus-platform"] == value["platform_source_sha"]
            and any(
                name in record["scope"]["projects"]
                for name in ("lotus-platform", "canonical-ingress")
            )
            and all(
                Path(record["scope"]["projects"][name]).resolve() == platform
                for name in ("lotus-platform", "canonical-ingress")
                if name in record["scope"]["projects"]
            )
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError, EnvironmentRefused):
        valid = False
    if not valid:
        raise ProfileRefused("SOURCE_RECEIPT_PARENT_REFUSED")


@dataclass(frozen=True, init=False)
class SourceReceiptSchemaAuthorization:
    session: object = field(repr=False)
    engine: object = field(repr=False)
    schema: str
    marker: str
    pid: int
    admission_digest: str
    schema_oid: int | None

    @property
    def target(self):
        from types import SimpleNamespace

        return SimpleNamespace(
            database=self.session.admission["database"], username=self.session.admission["role"]
        )

    def __init__(self, session, engine, case, token, schema_oid=None):
        if token is not _TOKEN:
            raise ProfileRefused("SOURCE_RECEIPT_FACTORY_REQUIRED")
        for name, value in dict(
            session=session,
            engine=engine,
            schema=case["schema"],
            marker=case["marker"],
            pid=os.getpid(),
            admission_digest=digest(session.admission),
            schema_oid=schema_oid,
        ).items():
            object.__setattr__(self, name, value)
        _issued[id(self)] = self


def require_schema_authorization(authorization, *, engine, schema, cleanup=False):
    if _issued.get(id(authorization)) is not authorization or authorization.pid != os.getpid():
        raise ProfileRefused("SOURCE_RECEIPT_CAPABILITY_INVALID")
    session = authorization.session
    if (
        authorization.engine is not engine
        or schema != authorization.schema
        or authorization.admission_digest != digest(session.admission)
    ):
        raise ProfileRefused("SOURCE_RECEIPT_CAPABILITY_SCOPE")
    session.check_deadline(cleanup=cleanup)
    session.validate_url(engine.url)


def retire_schema_authorization(authorization):
    from sqlalchemy import event

    engine, before, after = _fences[id(authorization)]
    event.remove(engine, "before_execute", before)
    event.remove(engine, "after_execute", after)
    _fences.pop(id(authorization))
    _issued.pop(id(authorization))


IDENTITY_SQL = """
SELECT d.oid AS database_oid, d.datdba AS database_owner_oid,
       current_database() AS database, session_user::text AS role,
       current_user::text AS current_role, r.oid AS role_oid,
       shobj_description(d.oid, 'pg_database') AS database_marker,
       pg_postmaster_start_time() AS server_birth, inet_server_addr()::text AS server_address,
       inet_server_port() AS server_port,
       r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls
         OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) AS unsafe_role,
       has_schema_privilege(r.oid, 'public', 'CREATE') AS public_create,
       has_database_privilege(r.oid, d.oid, 'CREATE') AS schema_create
FROM pg_database d JOIN pg_roles r ON r.rolname=session_user WHERE d.datname=current_database()
"""


class OperatorSourceSession:
    def __init__(self, admission, database_url, workspace=None, *, cleanup=False):
        self.admission = json.loads(json.dumps(admission))
        self.database_url = database_url
        self.workspace = workspace
        self.engines = []
        self.check_deadline(cleanup=cleanup)
        self.validate_url(database_url)

    def check_deadline(self, *, cleanup=False):
        deadline = instant(self.admission["cleanup_deadline" if cleanup else "run_deadline"])
        if time.time() >= deadline or time.time() >= instant(self.admission["parent_expiry"]):
            raise ProfileRefused("SOURCE_RECEIPT_ADMISSION_EXPIRED")
        if self.workspace is not None:
            qualify_parent(self.admission, self.workspace, cleanup=cleanup)

    def validate_url(self, value):
        from sqlalchemy.engine import make_url
        from sqlalchemy.exc import ArgumentError

        try:
            url = make_url(value) if isinstance(value, str) else value
            admitted = self.admission
            expected_tls = admitted["tls"]
            if url.drivername == "postgresql+asyncpg" and expected_tls:
                expected_tls = {"ssl": expected_tls["sslmode"]}
            valid = (
                url.drivername in ("postgresql", "postgresql+asyncpg", "postgresql+psycopg2")
                and url.host == admitted["host"] == "127.0.0.1"
                and url.port == admitted["port"]
                and url.database == admitted["database"]
                and url.username == admitted["role"]
                and isinstance(url.password, str)
                and 1 <= len(url.password) <= 1024
                and dict(url.query) == expected_tls
            )
        except (ArgumentError, ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise ProfileRefused("SOURCE_RECEIPT_DSN_REFUSED")

    def connection_url(self, *, asynchronous=False):
        from sqlalchemy.engine import make_url

        url = make_url(self.database_url)
        tls = self.admission["tls"]
        query = {"ssl": tls["sslmode"]} if asynchronous and tls else tls
        return url.set(
            drivername="postgresql+asyncpg" if asynchronous else "postgresql", query=query
        ).render_as_string(hide_password=False)

    def handshake(self, connection, *, cleanup=False):
        from sqlalchemy import inspect, text

        self.check_deadline(cleanup=cleanup)
        self.validate_url(connection.engine.url)
        actual = dict(connection.execute(text(IDENTITY_SQL)).mappings().one())
        admitted = self.admission
        fields = (
            "database_oid",
            "database_owner_oid",
            "database",
            "role",
            "role_oid",
            "database_marker",
            "server_address",
            "server_port",
        )
        if any(actual[name] != admitted[name] for name in fields) or (
            actual["current_role"] != admitted["role"]
            or actual["unsafe_role"]
            or actual["public_create"]
            or not actual["schema_create"]
            or actual["server_birth"].timestamp() != instant(admitted["server_birth"])
        ):
            raise ProfileRefused("SOURCE_RECEIPT_HANDSHAKE_REFUSED")
        privileges = (
            connection.execute(
                text("""
            SELECT c.relname, c.relkind, c.relowner,
                   has_table_privilege(current_user,c.oid,'SELECT') AS readable,
                   CASE WHEN c.relkind='S' THEN has_sequence_privilege(current_user,c.oid,
                        'USAGE,UPDATE,SELECT') ELSE has_table_privilege(current_user,c.oid,
                        'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') END AS writable
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('r','p','S')
        """)
            )
            .mappings()
            .all()
        )
        if any(row["writable"] or row["relowner"] == admitted["role_oid"] for row in privileges):
            raise ProfileRefused("SOURCE_RECEIPT_PUBLIC_PRIVILEGE_REFUSED")
        if {
            row["relname"] for row in privileges if row["readable"] and row["relkind"] == "r"
        } != set(TABLES):
            raise ProfileRefused("SOURCE_RECEIPT_PREREQUISITES_REFUSED")
        inspector = inspect(connection)
        shape = {}
        for table in TABLES:
            shape[table] = {
                "columns": [
                    (
                        item["name"],
                        str(item["type"].compile(dialect=connection.dialect)),
                        item["nullable"],
                    )
                    for item in inspector.get_columns(table, schema="public")
                ],
                "checks": inspector.get_check_constraints(table, schema="public"),
                "primary_key": inspector.get_pk_constraint(table, schema="public"),
                "unique": inspector.get_unique_constraints(table, schema="public"),
                "foreign_keys": inspector.get_foreign_keys(table, schema="public"),
            }
        if digest(shape) != admitted["prerequisite_sha256"]:
            raise ProfileRefused("SOURCE_RECEIPT_PREREQUISITE_SHAPE_REFUSED")
        # Verify source-owned column identity independently of the operator digest.
        from portfolio_common.database_models import Base

        for table in TABLES:
            source_columns = [
                (column.name, str(column.type.compile(dialect=connection.dialect)), column.nullable)
                for column in Base.metadata.tables[table].columns
            ]
            if shape[table]["columns"] != source_columns:
                raise ProfileRefused("SOURCE_RECEIPT_SOURCE_SHAPE_REFUSED")
        return actual

    def engine(self, *, cleanup=False):
        from portfolio_common.database_runtime_profile import DatabasePoolMode
        from portfolio_common.db import create_sync_database_engine
        from sqlalchemy import event

        self.check_deadline(cleanup=cleanup)
        engine = create_sync_database_engine(
            runtime_identity="lotus-core-test",
            database_url=self.connection_url(),
            pool_mode=DatabasePoolMode.NULL,
        )

        def lock_bound(connection, record):
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout='1000ms'")

        event.listen(engine, "connect", lock_bound)
        self.engines.append(engine)
        return engine

    def authorize(self, engine, node, *, cleanup=False):
        from sqlalchemy import event, text

        case = next((case for case in self.admission["cases"] if case["node"] == node), None)
        if case is None:
            raise ProfileRefused("SOURCE_RECEIPT_NODE_REFUSED")
        with engine.begin() as connection:
            self.handshake(connection, cleanup=cleanup)
            existing = (
                connection.execute(
                    text(
                        "SELECT oid AS schema_oid,nspowner,"
                        "obj_description(oid,'pg_namespace') AS marker "
                        "FROM pg_namespace WHERE nspname=:schema"
                    ),
                    {"schema": case["schema"]},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None and (
                not cleanup
                or existing["nspowner"] != self.admission["role_oid"]
                or existing["marker"] != case["marker"]
            ):
                raise ProfileRefused("SOURCE_RECEIPT_EXISTING_SCHEMA_REFUSED")
        authorization = SourceReceiptSchemaAuthorization(
            self, engine, case, _TOKEN, existing["schema_oid"] if existing is not None else None
        )

        def fence(connection, clause, multiparams, params, options):
            statement = str(clause).strip()
            if statement.split(maxsplit=1)[0].upper() not in ("CREATE", "ALTER", "DROP", "COMMENT"):
                return
            removing = statement == f'DROP SCHEMA "{authorization.schema}" CASCADE'
            self.require_in_transaction(connection, authorization, cleanup=cleanup or removing)
            connection.execute(text("SET LOCAL lock_timeout='1000ms'"))
            current = connection.scalar(text("SELECT current_schema()"))
            if not admitted_ddl(statement, authorization.schema, authorization.marker, current):
                raise ProfileRefused("SOURCE_RECEIPT_DDL_SCOPE_REFUSED")
            if statement not in (
                f'CREATE SCHEMA "{authorization.schema}" AUTHORIZATION CURRENT_USER',
                f"COMMENT ON SCHEMA \"{authorization.schema}\" IS '{authorization.marker}'",
            ):
                identity = (
                    connection.execute(
                        text(
                            "SELECT oid,nspowner,obj_description(oid,'pg_namespace') AS marker "
                            "FROM pg_namespace WHERE nspname=:schema"
                        ),
                        {"schema": authorization.schema},
                    )
                    .mappings()
                    .one()
                )
                if (
                    identity["oid"] != authorization.schema_oid
                    or identity["nspowner"] != self.admission["role_oid"]
                    or identity["marker"] != authorization.marker
                ):
                    raise ProfileRefused("SOURCE_RECEIPT_SCHEMA_IDENTITY_REFUSED")

        def created(connection, clause, multiparams, params, options, result):
            if (
                str(clause).strip()
                == f'CREATE SCHEMA "{authorization.schema}" AUTHORIZATION CURRENT_USER'
            ):
                oid = connection.scalar(
                    text("SELECT oid FROM pg_namespace WHERE nspname=:schema"),
                    {"schema": authorization.schema},
                )
                object.__setattr__(authorization, "schema_oid", oid)

        event.listen(engine, "before_execute", fence)
        try:
            event.listen(engine, "after_execute", created)
        except Exception:
            event.remove(engine, "before_execute", fence)
            _issued.pop(id(authorization), None)
            raise
        _fences[id(authorization)] = (engine, fence, created)
        return authorization

    def require_in_transaction(self, connection, authorization, *, cleanup=False):
        require_schema_authorization(
            authorization, engine=connection.engine, schema=authorization.schema, cleanup=cleanup
        )
        self.handshake(connection, cleanup=cleanup)

    def cleanup(self, engine, authorization):
        from sqlalchemy import text

        require_schema_authorization(
            authorization, engine=engine, schema=authorization.schema, cleanup=True
        )
        with engine.begin() as connection:
            self.require_in_transaction(connection, authorization, cleanup=True)
            row = (
                connection.execute(
                    text("""
                SELECT oid AS schema_oid, nspowner, obj_description(oid,'pg_namespace') AS marker
                FROM pg_namespace WHERE nspname=:schema
            """),
                    {"schema": authorization.schema},
                )
                .mappings()
                .one_or_none()
            )
            if row is not None and (
                row["nspowner"] != self.admission["role_oid"]
                or row["marker"] != authorization.marker
                or (
                    authorization.schema_oid is not None
                    and row["schema_oid"] != authorization.schema_oid
                )
            ):
                raise ProfileRefused("SOURCE_RECEIPT_SCHEMA_IDENTITY_REFUSED")
            if row is not None:
                self.check_deadline(cleanup=True)
                connection.execute(text(f'DROP SCHEMA "{authorization.schema}" CASCADE'))
        retire_schema_authorization(authorization)
        return "absent" if row is None else "removed"


def configure(admission, database_url, workspace):
    global _session
    if _session is not None:
        raise ProfileRefused("SOURCE_RECEIPT_SESSION_ALREADY_CONFIGURED")
    _session = OperatorSourceSession(admission, database_url, workspace)
    return _session


def operator_session():
    if os.environ.get("LOTUS_OPERATOR_SOURCE_RECEIPT"):
        if _session is None:
            raise ProfileRefused("SOURCE_RECEIPT_UNISSUED_PROFILE")
        return _session
    return None


def validate_collection(items):
    session = operator_session()
    if session is None:
        return
    expected = [case["node"] for case in session.admission["cases"]]
    forbidden = {"docker_services", "clean_db", "clean_db_module", "e2e_api_client"}
    if [item.nodeid for item in items] != expected or any(
        forbidden.intersection(item.fixturenames) for item in items
    ):
        raise ProfileRefused("SOURCE_RECEIPT_COLLECTION_REFUSED")


def set_connection_bounds():
    os.environ.update(
        {
            "LOTUS_CORE_DB_CONNECT_TIMEOUT_SECONDS": "2",
            "LOTUS_CORE_DB_STATEMENT_TIMEOUT_MS": "5000",
            "LOTUS_CORE_DB_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS": "5000",
        }
    )


def budget_event(schema, event, port=None):
    """One parent-created fixed-size counter per predeclared schema, no child-chosen paths."""
    import msvcrt

    admission = load_admission(
        os.environ["LOTUS_SOURCE_RECEIPT_ADMISSION"],
        os.environ["LOTUS_SOURCE_RECEIPT_ADMISSION_SHA256"],
    )
    case = next((case for case in admission["cases"] if case["schema"] == schema), None)
    if case is None or event not in ("http_calls", "processes", "ready"):
        raise ProfileRefused("SOURCE_RECEIPT_BUDGET_SCOPE")
    path = Path(os.environ["LOTUS_SOURCE_RECEIPT_RUN_DIR"]) / (schema + ".json")
    with path.open("r+b", buffering=0) as stream:
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            stream.seek(1)
            counts = json.loads(stream.read(512))
            counts.setdefault("pids", [])
            counts.setdefault("ports", [])
            if event == "ready":
                if (
                    type(port) is not int
                    or not 1 <= port <= 65535
                    or not counts["pids"]
                    or counts["pids"][-1] != os.getpid()
                    or len(counts["ports"]) >= counts["processes"]
                ):
                    raise ProfileRefused("SOURCE_RECEIPT_LISTENER_REFUSED")
                counts["ports"].append(port)
                limit_event = "processes"
            else:
                counts[event] += 1
                limit_event = event
                if event == "processes":
                    counts["pids"].append(os.getpid())
            encoded = json.dumps(counts).encode()
            if len(encoded) > 512:
                raise ProfileRefused("SOURCE_RECEIPT_COUNTER_OVERSIZE")
            stream.seek(1)
            stream.write(encoded.ljust(512, b" "))
            if counts[limit_event] > case[limit_event] or time.time() >= instant(
                admission["run_deadline"]
            ):
                raise ProfileRefused("SOURCE_RECEIPT_BUDGET_EXCEEDED")
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def attach_api(inputs):
    """Fresh API-process authority; credentials still arrive on its original private stdin."""
    from tests.test_support.source_receipt_process_custody import require_current_job

    require_current_job()
    admission = load_admission(
        os.environ["LOTUS_SOURCE_RECEIPT_ADMISSION"],
        os.environ["LOTUS_SOURCE_RECEIPT_ADMISSION_SHA256"],
    )
    validate_admission(admission, now=time.time(), environment=os.environ, platform=os.name)
    allowed = {
        "ENTERPRISE_ENFORCE_AUTHZ",
        "ENTERPRISE_PRIMARY_KEY_ID",
        "ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET",
        "LOTUS_PORTFOLIO_FACT_VERIFICATION_KEYS",
        "LOTUS_PORTFOLIO_FACT_VERIFICATION_CUTS",
        "LOTUS_PORTFOLIO_FACT_VERIFICATION_KEY_SYNTHETIC_HTTP",
    }
    if set(inputs["environment"]) - allowed:
        raise ProfileRefused("SOURCE_RECEIPT_API_ENVIRONMENT_REFUSED")
    case = next((case for case in admission["cases"] if case["schema"] == inputs["schema"]), None)
    if case is None:
        raise ProfileRefused("SOURCE_RECEIPT_API_SCHEMA_REFUSED")
    set_connection_bounds()
    session = OperatorSourceSession(
        admission, inputs["database_url"], os.environ["LOTUS_SOURCE_RECEIPT_WORKSPACE"]
    )
    engine = session.engine()
    try:
        with engine.begin() as connection:
            session.handshake(connection)
            from sqlalchemy import text

            row = (
                connection.execute(
                    text(
                        "SELECT nspowner,obj_description(oid,'pg_namespace') AS marker "
                        "FROM pg_namespace WHERE nspname=:schema"
                    ),
                    {"schema": case["schema"]},
                )
                .mappings()
                .one()
            )
            if row["nspowner"] != admission["role_oid"] or row["marker"] != case["marker"]:
                raise ProfileRefused("SOURCE_RECEIPT_API_SCHEMA_IDENTITY")
    finally:
        engine.dispose()
    budget_event(case["schema"], "processes")
    return session
