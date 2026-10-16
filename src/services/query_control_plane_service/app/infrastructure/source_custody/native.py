"""Selected native capture verification using the producer-owned typed root recipes."""

import hashlib
import json

from portfolio_common.domain.portfolio_financial_source_cuts import InputRole, source_product_bytes
from portfolio_common.domain.portfolio_flow_source_observations import (
    FlowEventObservation,
    FlowSourceCut,
)
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
    ObservationCoverage,
)
from portfolio_common.portfolio_financial_source_cut_admission import closed_source_json
from portfolio_common.portfolio_financial_source_cut_models import (
    NATIVE_CAPTURE_SERIALIZERS,
    native_capture_typed_root,
)
from pydantic import TypeAdapter

from .reconstruction import native_capture_identity, require_capture_fields, require_capture_receipt
from .valuation import RetainedValuationCaptureVerifier


class NativeRetainedCaptureVerifier:
    """Consumer of the admitted producer catalog; hashes reuse the existing shared recipes."""

    def verify(self, artifact, raw, *, identity, financial_input=None):
        if financial_input is None or financial_input.graph.identity != identity:
            raise ValueError("selected retained financial graph required")
        if (
            artifact.role not in set(InputRole)
            or type(artifact.source_context.selector_json) is not str
        ):
            raise ValueError("actual retained native role and selector required")
        selection = next(
            s for s in financial_input.declaration.selections if s.role == artifact.role
        )
        context = artifact.source_context
        if (
            artifact.serializer_id != NATIVE_CAPTURE_SERIALIZERS.get(artifact.role)
            or artifact.schema_version != "v1"
            or artifact.mime_type != "application/json"
            or context.capture_origin != "ACQUIRED_NATIVE_DTO"
            or (
                artifact.source_product,
                artifact.product_version,
                artifact.selector_hash,
                artifact.typed_content_hash,
                context.receipt_job_id,
                context.source_revision,
                closed_source_json(context.selector_json),
            )
            != (
                selection.product_name,
                selection.product_version,
                selection.selector_hash,
                selection.content_hash,
                selection.receipt_job_id,
                selection.source_revision,
                selection.selector.model_dump(mode="json"),
            )
            or artifact.capture_id
            != native_capture_identity(
                identity.tenant_id,
                financial_input.graph.portfolio_id,
                selection,
                artifact.source_page_index,
            )
        ):
            raise ValueError("retained native catalog, selection or context mismatch")
        retained = raw.read()
        if (
            len(retained) != artifact.byte_count
            or hashlib.sha256(retained).hexdigest() != artifact.raw_hash
        ):
            raise ValueError("retained native whole byte root mismatch")
        wrapper = closed_source_json(retained)
        require_capture_fields(wrapper, ("serializer", "payload"))
        if wrapper["serializer"] != artifact.serializer_id or type(wrapper["payload"]) is not dict:
            raise ValueError("retained native wrapper substitution")
        payload = wrapper["payload"]
        if source_product_bytes(payload, serializer=artifact.serializer_id) != retained:
            raise ValueError("retained native wrapper is not canonical acquired UTF8")
        if (
            native_capture_typed_root(artifact.serializer_id, payload)
            != artifact.typed_content_hash
        ):
            raise ValueError("retained native typed root mismatch")
        if artifact.role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS):
            count = RetainedValuationCaptureVerifier().verify(
                payload, artifact, selection, financial_input
            )
        else:
            count = self._fact_or_flow(payload, artifact, selection, financial_input)
        if (
            type(artifact.source_page_index) is not int
            or artifact.source_page_index != 0
            or type(context.returned_count) is not int
            or type(context.total_count) is not int
            or (context.returned_count, context.total_count, context.next_page_token)
            != (count, count, None)
        ):
            raise ValueError("retained native complete-artifact cardinality mismatch")

    def _fact_or_flow(self, payload, artifact, selection, financial_input):
        context = artifact.source_context
        if any(
            getattr(context, name) is not None
            for name in (
                "snapshot_epoch",
                "request_scope",
                "export_job_id",
                "refresh_of_job_id",
            )
        ):
            raise ValueError("fact or flow native context must remain unavailable")
        if artifact.role is InputRole.FLOWS:
            return self._flow(payload, selection, financial_input)
        require_capture_fields(
            payload,
            (
                "product_name",
                "product_version",
                "fact",
                "observation_id",
                "content_hash",
                "received_at",
                "receipt",
            ),
        )
        cash = artifact.role is InputRole.CASH
        model = CashAvailabilityObservation if cash else FundingInvestmentObservation
        fact = TypeAdapter(model).validate_json(
            json.dumps(payload["fact"], allow_nan=False), strict=True
        )
        envelope, selector = fact.envelope, selection.selector
        if (
            (
                envelope.tenant_id,
                envelope.portfolio_id,
                envelope.producer_id,
                envelope.source_record_id,
                envelope.source_cut_id,
                envelope.source_revision,
            )
            != (
                financial_input.graph.identity.tenant_id,
                financial_input.graph.portfolio_id,
                selector.producer_id,
                selector.source_record_id,
                selector.source_cut_id,
                selector.source_version,
            )
            or selection.source_revision != str(envelope.source_revision)
            or selector.observation_id != fact.content_hash
            or selector.content_hash != fact.content_hash
            or envelope.coverage is not ObservationCoverage.COMPLETE
            or not envelope.is_effective(selector.as_of_date)
            or cash
            and fact.currency != financial_input.graph.currency
        ):
            raise ValueError("retained observation source scope mismatch")
        require_capture_receipt(
            payload["receipt"],
            tenant=envelope.tenant_id,
            job_id=selection.receipt_job_id,
            endpoint="/ingest/portfolio-cash-availability-observations"
            if cash
            else "/ingest/portfolio-funding-investment-observations",
            entity="portfolio_cash_availability_observation"
            if cash
            else "portfolio_funding_investment_observation",
            received_at=payload["received_at"],
        )
        return 1

    def _flow(self, payload, selection, financial_input):
        require_capture_fields(
            payload,
            (
                "product_name",
                "product_version",
                "cut",
                "events",
                "dependencies",
                "received_at",
                "receipt",
            ),
        )
        cut = TypeAdapter(FlowSourceCut).validate_json(
            json.dumps(payload["cut"], allow_nan=False), strict=True
        )
        selector = selection.selector
        if (
            cut.tenant_id,
            cut.portfolio_id,
            cut.source_system,
            cut.source_cut_id,
            cut.cut_revision,
            cut.coverage_from,
            cut.coverage_to,
            cut.currency,
            cut.content_hash,
        ) != (
            financial_input.graph.identity.tenant_id,
            financial_input.graph.portfolio_id,
            selector.source_system,
            selector.source_cut_id,
            selector.cut_revision,
            selector.from_date,
            selector.to_date,
            financial_input.graph.currency,
            selector.manifest_hash,
        ) or selection.source_revision != str(cut.cut_revision):
            raise ValueError("retained flow cut source scope mismatch")
        require_capture_receipt(
            payload["receipt"],
            tenant=cut.tenant_id,
            job_id=selection.receipt_job_id,
            endpoint="/ingest/portfolio-flow-source-cuts",
            entity="portfolio_flow_source_cut",
            received_at=payload["received_at"],
        )
        for name, pins in (("events", cut.event_pins), ("dependencies", cut.dependency_pins)):
            if type(payload[name]) is not list or len(payload[name]) != len(pins):
                raise ValueError("retained flow membership shape mismatch")
            for value, pin in zip(payload[name], pins, strict=True):
                require_capture_fields(value, ("fact", "received_at", "receipt"))
                fact = TypeAdapter(FlowEventObservation).validate_json(
                    json.dumps(value["fact"], allow_nan=False), strict=True
                )
                if fact.content_hash != pin.content_hash:
                    raise ValueError("retained flow native pin order mismatch")
                require_capture_receipt(
                    value["receipt"],
                    tenant=cut.tenant_id,
                    job_id=value["receipt"]["job_id"],
                    endpoint="/ingest/portfolio-flow-event-observations",
                    entity="portfolio_flow_event_observation",
                    received_at=value["received_at"],
                )
        return len(cut.event_pins) + len(cut.dependency_pins)
