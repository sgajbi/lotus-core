"""Runtime build metadata shared by Lotus Core service images."""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, Field

from portfolio_common.runtime_settings import env_str

UNKNOWN_METADATA_VALUE: Final = "unknown"
MAX_METADATA_VALUE_LENGTH: Final = 512

GIT_COMMIT_SHA_ENV: Final = "LOTUS_GIT_COMMIT_SHA"
GIT_BRANCH_ENV: Final = "LOTUS_GIT_BRANCH"
BUILD_TIMESTAMP_ENV: Final = "LOTUS_BUILD_TIMESTAMP"
REPO_URL_ENV: Final = "LOTUS_REPO_URL"
IMAGE_VERSION_ENV: Final = "LOTUS_IMAGE_VERSION"
IMAGE_DIGEST_ENV: Final = "LOTUS_IMAGE_DIGEST"
CI_PIPELINE_RUN_ID_ENV: Final = "LOTUS_CI_RUN_ID"

BUILD_METADATA_ENV_VARS: Final[tuple[str, ...]] = (
    GIT_COMMIT_SHA_ENV,
    GIT_BRANCH_ENV,
    BUILD_TIMESTAMP_ENV,
    REPO_URL_ENV,
    IMAGE_VERSION_ENV,
    IMAGE_DIGEST_ENV,
    CI_PIPELINE_RUN_ID_ENV,
)

BUILD_METADATA_RESPONSE_FIELDS: Final[tuple[str, ...]] = (
    "git_commit_sha",
    "git_branch",
    "build_timestamp",
    "repo_url",
    "image_version",
    "image_digest",
    "ci_pipeline_run_id",
)

OCI_METADATA_LABELS: Final[dict[str, str]] = {
    "org.opencontainers.image.revision": "git_commit_sha",
    "org.opencontainers.image.ref.name": "git_branch",
    "org.opencontainers.image.created": "build_timestamp",
    "org.opencontainers.image.source": "repo_url",
    "org.opencontainers.image.version": "image_version",
    "org.opencontainers.image.digest": "image_digest",
    "org.opencontainers.image.ci.run_id": "ci_pipeline_run_id",
}


class BuildMetadataResponse(BaseModel):
    service_name: str = Field(description="Lotus Core service reporting this runtime metadata.")
    git_commit_sha: str = Field(description="Git commit SHA embedded in the container image.")
    git_branch: str = Field(description="Git branch embedded in the container image.")
    build_timestamp: str = Field(description="UTC image build timestamp.")
    repo_url: str = Field(description="Repository URL embedded in the container image.")
    image_version: str = Field(description="Image version embedded in OCI metadata.")
    image_digest: str = Field(description="OCI image digest supplied by the build or release lane.")
    ci_pipeline_run_id: str = Field(
        description="CI pipeline or GitHub Actions run identifier embedded in the image."
    )
    oci_labels: dict[str, str] = Field(
        description=(
            "OCI label names plus release-resolved metadata values used for manifest and runtime "
            "parity checks."
        )
    )


def _metadata_value(env_name: str) -> str:
    value = env_str(env_name, "").strip()
    if not value:
        return UNKNOWN_METADATA_VALUE
    sanitized = "".join(character if character.isprintable() else "_" for character in value)
    return sanitized[:MAX_METADATA_VALUE_LENGTH] or UNKNOWN_METADATA_VALUE


def build_metadata_payload(*, service_name: str) -> BuildMetadataResponse:
    payload = BuildMetadataResponse(
        service_name=service_name,
        git_commit_sha=_metadata_value(GIT_COMMIT_SHA_ENV),
        git_branch=_metadata_value(GIT_BRANCH_ENV),
        build_timestamp=_metadata_value(BUILD_TIMESTAMP_ENV),
        repo_url=_metadata_value(REPO_URL_ENV),
        image_version=_metadata_value(IMAGE_VERSION_ENV),
        image_digest=_metadata_value(IMAGE_DIGEST_ENV),
        ci_pipeline_run_id=_metadata_value(CI_PIPELINE_RUN_ID_ENV),
        oci_labels={},
    )
    payload.oci_labels = {
        label_name: getattr(payload, field_name)
        for label_name, field_name in OCI_METADATA_LABELS.items()
    }
    return payload
