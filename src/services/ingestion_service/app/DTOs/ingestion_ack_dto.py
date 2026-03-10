from pydantic import BaseModel, Field


class IngestionAcceptedResponse(BaseModel):
    message: str = Field(
        ...,
        description="Human-readable acceptance message for the ingestion request.",
        examples=["Transactions accepted for asynchronous ingestion processing."],
    )
    entity_type: str = Field(
        ...,
        description="Canonical entity type accepted by the endpoint.",
        examples=["transaction"],
    )
    accepted_count: int = Field(
        ...,
        description="Number of records accepted for asynchronous processing.",
        ge=0,
        examples=[1],
    )
    correlation_id: str = Field(
        ...,
        description="Correlation identifier used for cross-service traceability.",
        examples=["ING:7f4a64b0-35f4-41bc-8f74-cb556f2ad9a3"],
    )
    request_id: str = Field(
        ...,
        description="Request identifier for ingress request tracking.",
        examples=["REQ:3a63936e-bf29-41e2-9f16-faf4e561d845"],
    )
    trace_id: str = Field(
        ...,
        description="Distributed trace identifier for observability stitching.",
        examples=["4bf92f3577b34da6a3ce929d0e0e4736"],
    )
    idempotency_key: str | None = Field(
        default=None,
        description=(
            "Client-supplied idempotency key if provided in the X-Idempotency-Key header."
        ),
        examples=["core-ingest-20260228-portfolio-123-batch-01"],
    )


class BatchIngestionAcceptedResponse(IngestionAcceptedResponse):
    job_id: str = Field(
        ...,
        description=(
            "Asynchronous ingestion job identifier used for client polling, "
            "replay controls, and operational support."
        ),
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )
