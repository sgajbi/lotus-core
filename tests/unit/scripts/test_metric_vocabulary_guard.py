from pathlib import Path

from scripts import metric_vocabulary_guard as guard


def test_metric_vocabulary_guard_accepts_current_truth() -> None:
    assert guard.evaluate_metric_vocabulary() == []


def test_metric_vocabulary_guard_rejects_forbidden_label(tmp_path: Path) -> None:
    source_dir = tmp_path / "src" / "services" / "demo" / "app"
    source_dir.mkdir(parents=True)
    (source_dir / "monitoring.py").write_text(
        "\n".join(
            [
                "from prometheus_client import Counter",
                "HTTP_TOTAL = Counter(",
                '    "demo_http_total",',
                '    "Demo HTTP metric.",',
                '    labelnames=("service", "path"),',
                ")",
            ]
        ),
        encoding="utf-8",
    )

    findings = guard.evaluate_metric_vocabulary(
        repo_root=tmp_path,
        source_roots=(tmp_path / "src",),
        allowed_labels=("service", "endpoint_template"),
        forbidden_labels=("path",),
        service_local_metric_owners={"demo_http_total": "demo"},
    )

    assert findings == [
        {
            "metric": "demo_http_total",
            "file": "src/services/demo/app/monitoring.py",
            "line": 2,
            "labels": ["service", "path"],
            "violations": [
                "unregistered labels: path",
                "forbidden labels: path",
            ],
        }
    ]


def test_metric_vocabulary_guard_rejects_unowned_service_local_metric(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "src" / "services" / "demo" / "app"
    source_dir.mkdir(parents=True)
    (source_dir / "monitoring.py").write_text(
        "\n".join(
            [
                "from prometheus_client import Counter",
                "EVENTS_TOTAL = Counter(",
                '    "demo_events_total",',
                '    "Demo events metric.",',
                '    labelnames=("service",),',
                ")",
            ]
        ),
        encoding="utf-8",
    )

    findings = guard.evaluate_metric_vocabulary(
        repo_root=tmp_path,
        source_roots=(tmp_path / "src",),
        allowed_labels=("service",),
        forbidden_labels=(),
        service_local_metric_owners={},
    )

    assert findings == [
        {
            "metric": "demo_events_total",
            "file": "src/services/demo/app/monitoring.py",
            "line": 2,
            "labels": ["service"],
            "violations": ["service-local metric has no explicit owner registration"],
        }
    ]


def test_metric_vocabulary_guard_accepts_owned_service_local_metric(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "src" / "services" / "demo" / "app"
    source_dir.mkdir(parents=True)
    (source_dir / "monitoring.py").write_text(
        "\n".join(
            [
                "from prometheus_client import Counter",
                "EVENTS_TOTAL = Counter(",
                '    "demo_events_total",',
                '    "Demo events metric.",',
                '    labelnames=("service",),',
                ")",
            ]
        ),
        encoding="utf-8",
    )

    assert (
        guard.evaluate_metric_vocabulary(
            repo_root=tmp_path,
            source_roots=(tmp_path / "src",),
            allowed_labels=("service",),
            forbidden_labels=(),
            service_local_metric_owners={"demo_events_total": "demo"},
        )
        == []
    )
