"""Host identity and fail-closed controls for measured deployed admission rows."""

import json

import pytest

from tests.test_support.native_consumer_boundary import assert_worker_advisory_admission


def admission_row(host="172.20.0.4", raw="172.20.0.4/32"):
    return {
        "pid": 42,
        "client_addr_raw": raw,
        "client_host": host,
        "query": "SELECT pg_advisory_xact_lock($1)",
        "blocking_pids": [17],
        "wait_event_type": "Lock",
        "wait_event": "advisory",
    }


def worker(ips=None):
    return {
        "ips": ["172.20.0.4"] if ips is None else ips,
        "container": "actual-worker",
        "project": "private-owned-project",
        "source": "signed-source",
        "image_id": "actual-image",
        "manifest_hash": "verified-manifest",
    }


@pytest.mark.parametrize(
    ("host", "raw", "docker_ip"),
    [
        ("172.20.0.4", "172.20.0.4/32", "172.20.0.4"),
        ("2001:db8::4", "2001:db8::4/128", "2001:0db8:0:0:0:0:0:4"),
    ],
)
def test_identical_host_accepts_raw_mask_and_ipv6_representation(host, raw, docker_ip):
    assert_worker_advisory_admission(
        [admission_row(host, raw)], worker([docker_ip]), holder_pid=17, lock_key=-123
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("client_host", None),
        ("client_host", "172.20.0.5"),
        ("client_host", "172.20.0.4/32"),
        ("client_host", "2001:db8::5"),
        ("query", "SELECT pg_advisory_lock($1)"),
        ("query", None),
        ("blocking_pids", [18]),
        ("blocking_pids", []),
        ("pid", 17),
        ("pid", 0),
        ("wait_event_type", "Client"),
        ("wait_event", "relation"),
    ],
)
def test_any_unexpected_row_refuses_and_emits_complete_diagnostic(field, value):
    unexpected = {**admission_row(), field: value}
    rows = [admission_row(), unexpected]
    identity = worker()
    with pytest.raises(AssertionError) as caught:
        assert_worker_advisory_admission(rows, identity, holder_pid=17, lock_key=-123)
    diagnostic = json.loads(str(caught.value).split("refused: ", 1)[1])
    assert diagnostic == {
        "rows": rows,
        "worker": identity,
        "holder_pid": 17,
        "production_lock_key": -123,
    }


@pytest.mark.parametrize("ips", [[], [None], ["172.20.0.4/24"], ["not-an-address"]])
def test_missing_or_non_host_worker_identity_refuses(ips):
    with pytest.raises(AssertionError, match="admission refused"):
        assert_worker_advisory_admission(
            [admission_row()], worker(ips), holder_pid=17, lock_key=-123
        )


def test_no_observed_backend_refuses():
    with pytest.raises(AssertionError, match="admission refused"):
        assert_worker_advisory_admission([], worker(), holder_pid=17, lock_key=-123)
