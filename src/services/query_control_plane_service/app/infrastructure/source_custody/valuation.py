"""Retained valuation export identity, original request and dense page verification."""

from .reconstruction import require_capture_fields, retained_stamp


class RetainedValuationCaptureVerifier:
    def verify(self, payload, artifact, selection, financial_input):
        require_capture_fields(
            payload, ("product_name", "product_version", "result", "request", "receipt")
        )
        receipt, original, result = payload["receipt"], payload["request"], payload["result"]
        require_capture_fields(
            receipt,
            (
                "job_id",
                "status",
                "dataset_type",
                "portfolio_id",
                "completed_at",
                "result_row_count",
            ),
        )
        retained_stamp(receipt["completed_at"])
        if type(original) is not dict or type(result) is not dict:
            raise ValueError("retained valuation export identity mismatch")
        self._export_identity(receipt, artifact, selection, financial_input)
        self._export_request(original, result, artifact.source_context, selection, financial_input)
        data, evidence = result.get("data"), result.get("source_evidence")
        if (
            type(data) is not list
            or type(evidence) is not dict
            or evidence.get("availability") != "RETAINED"
        ):
            raise ValueError("actual retained valuation evidence required")
        count = self._pages(
            evidence.get("pages"),
            original,
            selection.selector,
            financial_input,
            artifact.source_context,
        )
        if (
            type(receipt["result_row_count"]) is not int
            or type(result.get("result_row_count")) is not int
            or (receipt["result_row_count"], result["result_row_count"], len(data))
            != (count, count, count)
        ):
            raise ValueError("retained valuation result cardinality mismatch")
        return count

    def _export_identity(self, receipt, artifact, selection, financial_input):
        selector, context = selection.selector, artifact.source_context
        if selector.export_job_id is None or (
            receipt["job_id"],
            receipt["status"],
            receipt["dataset_type"],
            receipt["portfolio_id"],
            selection.receipt_job_id,
            selection.source_revision,
            context.export_job_id,
            selector.export_content_hash,
        ) != (
            selector.export_job_id,
            "completed",
            "portfolio_timeseries",
            financial_input.graph.portfolio_id,
            selector.export_job_id,
            selector.export_job_id,
            selector.export_job_id,
            artifact.typed_content_hash,
        ):
            raise ValueError("retained valuation export identity mismatch")

    def _export_request(self, original, result, context, selection, financial_input):
        selector = selection.selector
        if (
            context.refresh_of_job_id,
            original.get("refresh_of_job_id"),
            original.get("portfolio_id"),
            original.get("dataset_type"),
            result.get("job_id"),
            result.get("dataset_type"),
        ) != (
            selector.refresh_of_job_id,
            selector.refresh_of_job_id,
            financial_input.graph.portfolio_id,
            "portfolio_timeseries",
            selector.export_job_id,
            "portfolio_timeseries",
        ):
            raise ValueError("retained valuation export identity mismatch")

    def _pages(self, pages, original, selector, financial_input, context):
        if type(pages) is not list or not pages:
            raise ValueError("retained valuation page evidence required")
        requested = original.get("portfolio_timeseries_request")
        if type(requested) is not dict:
            raise ValueError("original retained valuation request required")
        window = dict(
            start_date=selector.from_date.isoformat(), end_date=selector.to_date.isoformat()
        )
        count, tokens, epoch_scope = 0, set(), None
        for index, page in enumerate(pages):
            metadata, scope = page["source_metadata"], page["requested_scope"]
            paging = metadata.get("page", {})
            self._page_counts(page, index, paging)
            self._page_scope(metadata, scope, requested, selector, financial_input, window)
            epoch, fingerprint = self._page_epoch(paging, context)
            if epoch_scope is not None and epoch_scope != (epoch, fingerprint):
                raise ValueError("retained valuation mixed native page context")
            epoch_scope = (epoch, fingerprint)
            count += page["row_count"]
            token = paging.get("next_page_token")
            if index == len(pages) - 1:
                if token is not None:
                    raise ValueError("retained valuation traversal incomplete")
            elif type(token) is not str or not token or token in tokens or page["row_count"] == 0:
                raise ValueError("retained valuation traversal did not progress")
            else:
                tokens.add(token)
        return count

    def _page_counts(self, page, index, paging):
        if (
            type(page["page_number"]) is not int
            or page["page_number"] != index + 1
            or type(page["row_count"]) is not int
            or page["row_count"] < 0
            or type(paging.get("returned_row_count")) is not int
            or page["row_count"] != paging["returned_row_count"]
        ):
            raise ValueError("retained valuation page scope or actual epoch mismatch")

    def _page_scope(self, metadata, scope, requested, selector, financial_input, window):
        if (
            (
                metadata.get("tenant_id"),
                metadata.get("portfolio_id"),
                metadata.get("reporting_currency"),
                metadata.get("resolved_window"),
                scope.get("window"),
                scope.get("as_of_date"),
                scope.get("reporting_currency"),
                scope.get("consumer_system"),
                {key: value for key, value in requested.items() if key != "page"},
                metadata.get("data_quality_status"),
                metadata.get("freshness_status"),
            )
            != (
                financial_input.graph.identity.tenant_id,
                financial_input.graph.portfolio_id,
                financial_input.graph.currency,
                window,
                window,
                selector.as_of_date.isoformat(),
                financial_input.graph.currency,
                selector.consumer_system,
                scope,
                "COMPLETE",
                "CURRENT",
            )
            or scope.get("period") is not None
            or metadata.get("source_evidence_current") is not True
        ):
            raise ValueError("retained valuation page scope or actual epoch mismatch")

    def _page_epoch(self, paging, context):
        epoch, fingerprint = paging.get("snapshot_epoch"), paging.get("request_scope_fingerprint")
        if (
            type(epoch) is not int
            or epoch < 0
            or type(fingerprint) is not str
            or not fingerprint.strip()
            or (str(epoch), fingerprint) != (context.snapshot_epoch, context.request_scope)
        ):
            raise ValueError("retained valuation page scope or actual epoch mismatch")
        return epoch, fingerprint
