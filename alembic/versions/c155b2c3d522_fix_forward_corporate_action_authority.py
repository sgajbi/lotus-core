"""Fix forward corporate-action manifest and legacy observation authority.

Revision ID: c155b2c3d522
Revises: c154b2c3d521
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c155b2c3d522"
down_revision: str | Sequence[str] | None = "c154b2c3d521"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_PAYLOAD_KEYS = """
                    'canonical_payload_version', 'completion_declared',
                    'corporate_action_event_id', 'corporate_action_type',
                    'expected_children', 'linked_transaction_group_id',
                    'parent_event_reference', 'portfolio_id', 'source_reference', 'version'
""".strip()
_BOOK_SCOPED_PAYLOAD_KEYS = """
                    'canonical_payload_version', 'completion_declared',
                    'corporate_action_event_id', 'corporate_action_type',
                    'expected_children', 'legal_book_id', 'linked_transaction_group_id',
                    'parent_event_reference', 'portfolio_id', 'source_reference',
                    'tenant_id', 'version'
""".strip()


def upgrade() -> None:
    """Accept historical manifests while requiring exact scope on new payloads."""

    op.execute(sa.text(_canonical_manifest_hash_sql(accept_book_scoped_payloads=True)))
    op.execute(
        sa.text(
            """
            CREATE FUNCTION enforce_ca_manifest_payload_book_scope()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                event_tenant_id text;
                event_legal_book_id text;
            BEGIN
                IF NOT (NEW.manifest_payload ? 'tenant_id')
                   AND NOT (NEW.manifest_payload ? 'legal_book_id') THEN
                    RETURN NEW;
                END IF;
                SELECT event.tenant_id, event.legal_book_id
                INTO event_tenant_id, event_legal_book_id
                FROM corporate_action_events AS event
                WHERE event.id = NEW.event_id;
                IF event_tenant_id IS NULL
                   OR NEW.manifest_payload ->> 'tenant_id' <> event_tenant_id
                   OR NEW.manifest_payload ->> 'legal_book_id' <> event_legal_book_id THEN
                    RAISE EXCEPTION
                        'corporate-action manifest payload book scope conflicts with parent event'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$;

            CREATE TRIGGER trg_ca_manifest_payload_book_scope
            BEFORE INSERT OR UPDATE ON corporate_action_manifest_versions
            FOR EACH ROW
            EXECUTE FUNCTION enforce_ca_manifest_payload_book_scope();
            """
        )
    )


def downgrade() -> None:
    """Restore the original c152 legacy-only manifest hash contract."""

    op.execute(
        sa.text(
            "DROP TRIGGER trg_ca_manifest_payload_book_scope ON corporate_action_manifest_versions"
        )
    )
    op.execute(sa.text("DROP FUNCTION enforce_ca_manifest_payload_book_scope()"))
    op.execute(sa.text(_canonical_manifest_hash_sql(accept_book_scoped_payloads=False)))


def _canonical_manifest_hash_sql(*, accept_book_scoped_payloads: bool) -> str:
    if accept_book_scoped_payloads:
        shape_guard = f"""
                IF payload_keys IS DISTINCT FROM ARRAY[
                    {_LEGACY_PAYLOAD_KEYS}
                ]::text[]
                   AND payload_keys IS DISTINCT FROM ARRAY[
                    {_BOOK_SCOPED_PAYLOAD_KEYS}
                ]::text[] THEN
                    RAISE EXCEPTION 'corporate-action manifest payload shape is not canonical'
                        USING ERRCODE = '23514';
                END IF;
                book_scoped_payload := payload_keys IS NOT DISTINCT FROM ARRAY[
                    {_BOOK_SCOPED_PAYLOAD_KEYS}
                ]::text[];
        """
        identity_keys = """
                    CASE WHEN book_scoped_payload THEN ARRAY[
                        'corporate_action_event_id', 'corporate_action_type',
                        'legal_book_id', 'linked_transaction_group_id',
                        'parent_event_reference', 'portfolio_id', 'tenant_id'
                    ]::text[] ELSE ARRAY[
                        'corporate_action_event_id', 'corporate_action_type',
                        'linked_transaction_group_id', 'parent_event_reference', 'portfolio_id'
                    ]::text[] END
        """.strip()
    else:
        shape_guard = f"""
                IF payload_keys IS DISTINCT FROM ARRAY[
                    {_LEGACY_PAYLOAD_KEYS}
                ]::text[] THEN
                    RAISE EXCEPTION 'corporate-action manifest payload shape is not canonical'
                        USING ERRCODE = '23514';
                END IF;
                book_scoped_payload := false;
        """
        identity_keys = """
                    ARRAY[
                        'corporate_action_event_id', 'corporate_action_type',
                        'linked_transaction_group_id', 'parent_event_reference', 'portfolio_id'
                    ]::text[]
        """.strip()
    return f"""
            CREATE OR REPLACE FUNCTION canonical_ca_manifest_payload_hash(payload jsonb)
            RETURNS text
            LANGUAGE plpgsql
            IMMUTABLE
            STRICT
            AS $$
            DECLARE
                payload_keys text[];
                source_keys text[];
                normalized_children jsonb;
                normalized_payload jsonb;
                book_scoped_payload boolean;
            BEGIN
                IF jsonb_typeof(payload) <> 'object' THEN
                    RAISE EXCEPTION 'corporate-action manifest payload must be an object'
                        USING ERRCODE = '23514';
                END IF;
                SELECT array_agg(key ORDER BY key COLLATE "C")
                INTO payload_keys
                FROM jsonb_object_keys(payload) AS key;
                {shape_guard}
                IF payload ->> 'canonical_payload_version' <> '1'
                   OR jsonb_typeof(payload -> 'completion_declared') <> 'boolean'
                   OR jsonb_typeof(payload -> 'version') <> 'number'
                   OR (payload -> 'version')::text !~ '^[1-9][0-9]*$'
                   OR jsonb_typeof(payload -> 'expected_children') <> 'array'
                   OR jsonb_typeof(payload -> 'source_reference') <> 'object' THEN
                    RAISE EXCEPTION 'corporate-action manifest payload shape is not canonical'
                        USING ERRCODE = '23514';
                END IF;
                IF EXISTS (
                    SELECT 1
                    FROM unnest({identity_keys}) AS required_key
                    WHERE jsonb_typeof(payload -> required_key) <> 'string'
                       OR payload ->> required_key <> btrim(payload ->> required_key)
                       OR payload ->> required_key = ''
                ) THEN
                    RAISE EXCEPTION 'corporate-action manifest identity is not canonical'
                        USING ERRCODE = '23514';
                END IF;
                SELECT array_agg(key ORDER BY key COLLATE "C")
                INTO source_keys
                FROM jsonb_object_keys(payload -> 'source_reference') AS key;
                IF source_keys IS DISTINCT FROM ARRAY[
                    'observed_at', 'source_content_hash', 'source_record_id',
                    'source_revision', 'source_system'
                ]::text[]
                   OR EXISTS (
                       SELECT 1
                       FROM unnest(ARRAY[
                           'observed_at', 'source_content_hash', 'source_record_id',
                           'source_revision', 'source_system'
                       ]) AS source_key
                       WHERE jsonb_typeof(payload -> 'source_reference' -> source_key) <> 'string'
                          OR payload #>> ARRAY['source_reference', source_key]
                              <> btrim(payload #>> ARRAY['source_reference', source_key])
                          OR payload #>> ARRAY['source_reference', source_key] = ''
                   )
                   OR payload #>> '{{source_reference,source_content_hash}}'
                       !~ '^[0-9a-f]{{64}}$' THEN
                    RAISE EXCEPTION 'corporate-action manifest source evidence is not canonical'
                        USING ERRCODE = '23514';
                END IF;
                PERFORM canonical_ca_child_payload_hash(child)
                FROM jsonb_array_elements(payload -> 'expected_children') AS expected(child);
                PERFORM assert_ca_manifest_semantics(payload);
                SELECT coalesce(
                    jsonb_agg(
                        jsonb_set(
                            child,
                            '{{dependency_transaction_ids}}',
                            (
                                SELECT coalesce(
                                    jsonb_agg(
                                        to_jsonb(dependency.transaction_id)
                                        ORDER BY dependency.transaction_id COLLATE "C"
                                    ),
                                    '[]'::jsonb
                                )
                                FROM jsonb_array_elements_text(
                                    child -> 'dependency_transaction_ids'
                                ) AS dependency(transaction_id)
                            ),
                            false
                        )
                        ORDER BY child ->> 'transaction_id' COLLATE "C"
                    ),
                    '[]'::jsonb
                )
                INTO normalized_children
                FROM jsonb_array_elements(payload -> 'expected_children') AS expected(child);
                normalized_payload := jsonb_set(
                    jsonb_set(
                        payload,
                        '{{expected_children}}',
                        normalized_children,
                        false
                    ),
                    '{{source_reference,observed_at}}',
                    jsonb_build_object(
                        'datetime', payload #> '{{source_reference,observed_at}}'
                    ),
                    false
                );
                RETURN encode(
                    sha256(convert_to(canonical_ca_json_value(normalized_payload), 'UTF8')),
                    'hex'
                );
            END;
            $$;
    """
