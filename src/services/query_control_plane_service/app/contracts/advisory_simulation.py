from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

ADVISORY_SIMULATION_CONTRACT_VERSION = "advisory-simulation.v1"
ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER = "X-Lotus-Contract-Version"
ADVISORY_SIMULATION_EXECUTION_PATH = "/integration/advisory/proposals/simulate-execution"
PROBLEM_TYPE_PREFIX = "https://lotus-platform.dev/problems/canonical-simulation"


class CanonicalSimulationErrorCode(str, Enum):
    REQUEST_VALIDATION_FAILED = "CANONICAL_SIMULATION_REQUEST_VALIDATION_FAILED"
    CONTRACT_VERSION_MISMATCH = "CANONICAL_SIMULATION_CONTRACT_VERSION_MISMATCH"
    EXECUTION_FAILED = "CANONICAL_SIMULATION_EXECUTION_FAILED"


class CanonicalSimulationProblemDetails(BaseModel):
    type: str = Field(description="Problem type URI.")
    title: str = Field(description="Short human-readable problem summary.")
    status: int = Field(description="HTTP status code.")
    detail: str = Field(description="Detailed problem description.")
    instance: str = Field(description="Request path for the failing simulation call.")
    error_code: CanonicalSimulationErrorCode = Field(
        description="Stable canonical simulation error code."
    )
    contract_version: str = Field(
        description="Canonical simulation contract version expected by this service."
    )
    correlation_id: str = Field(description="Correlation identifier for supportability.")


class CanonicalSimulationContractError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        error_code: CanonicalSimulationErrorCode,
        detail: str,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
