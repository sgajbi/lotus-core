"""Restart only the already-owned query service and attest an actual process generation."""

import json
import subprocess

from tests.test_support.runtime.compose_fault_recovery import ComposeFaultRecoveryBoundary


def restart_owned_query(*, project, compose_file, ready, runner=subprocess.run):
    assert project and compose_file
    service = "query_service"
    command = ["docker", "compose", "-p", project, "-f", compose_file]
    container = runner(
        [*command, "ps", "-q", service], check=True, capture_output=True, text=True, timeout=10
    ).stdout.strip()
    assert container and "\n" not in container

    def inspect():
        (row,) = json.loads(
            runner(
                ["docker", "inspect", container],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        )
        labels = row["Config"]["Labels"]
        assert row["Id"] == container
        assert labels["com.docker.compose.project"] == project
        assert labels["com.docker.compose.service"] == service
        return row

    before = inspect()
    assert before["State"]["Running"] is True
    with ComposeFaultRecoveryBoundary(
        project_name=project,
        compose_file=compose_file,
        faulted_service=service,
        recovery_services=(),
        faulted_service_ready=ready,
        recovery_services_ready=lambda: None,
        runner=runner,
    ) as recovery:
        stopped = inspect()
        assert stopped["State"]["Running"] is False
        assert stopped["State"]["Status"] == "exited"
        assert stopped["State"]["ExitCode"] == 0
    after = inspect()
    assert after["State"]["Running"] is True and after["State"]["Status"] == "running"
    assert after["Image"] == before["Image"]
    assert after["State"]["StartedAt"] != before["State"]["StartedAt"]
    return {
        "project": project,
        "service": service,
        "container": container,
        "image": after["Image"],
        "before_started_at": before["State"]["StartedAt"],
        "after_started_at": after["State"]["StartedAt"],
        "stopped_exit_code": stopped["State"]["ExitCode"],
        "healthy_restore": recovery.recovery_evidence is not None,
    }
