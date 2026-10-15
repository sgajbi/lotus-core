"""Public scope reaches only ingestion; trusted identity remains independent."""

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from portfolio_common.domain.portfolio_source_observations import (
    ObservationConflict,
    ObservationFamily,
)
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.portfolio_source_observation_qualification import (
    UnqualifiedProducerAuthority,
    parse_submission_grants,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]
SETTING = "LOTUS_PORTFOLIO_SOURCE_SUBMISSION_GRANTS_JSON"
CONFIG = json.dumps(
    [
        {
            "tenant_id": "tenant-synthetic",
            "portfolio_id": "portfolio-synthetic",
            "producer_id": "producer-synthetic",
            "family": "flow_event",
        }
    ]
)


def test_configured_public_grant_does_not_authenticate_body_or_header_identity():
    grants = parse_submission_grants(CONFIG)
    authority = UnqualifiedProducerAuthority(grants)
    context = TenantContext(
        TenantId("tenant-synthetic"), service_identity="producer-synthetic", identity_verified=True
    )
    assert authority.admit(context, grants[0]).qualification == "unqualified"
    for changes in (
        {"identity_verified": False},
        {"service_identity": "spoofed"},
        {"tenant_id": TenantId("foreign")},
        {"service_identity": None},
    ):
        with pytest.raises(ObservationConflict):
            authority.admit(replace(context, **changes), grants[0])
    for changes in (
        {"portfolio_id": "foreign"},
        {"tenant_id": "foreign"},
        {"family": ObservationFamily.CASH_AVAILABILITY},
    ):
        with pytest.raises(ObservationConflict):
            authority.admit(context, replace(grants[0], **changes))


def test_native_compose_models_absent_supplied_and_nonconsumer_preservation():
    # `config` is client-side model interpolation only; no daemon/container operation.
    root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
    environment = dict(os.environ)
    environment.pop(SETTING, None)

    def model(env):
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(root / "docker-compose.yml"),
                "config",
                "--format",
                "json",
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)["services"]

    absent = model(environment)
    supplied = model({**environment, SETTING: CONFIG})
    assert absent["ingestion_service"]["environment"][SETTING] == ""
    assert supplied["ingestion_service"]["environment"][SETTING] == CONFIG
    changed = [name for name in absent if absent[name] != supplied[name]]
    assert changed == ["ingestion_service"]
    assert all(
        SETTING not in service.get("environment", {})
        for name, service in supplied.items()
        if name != "ingestion_service"
    )
