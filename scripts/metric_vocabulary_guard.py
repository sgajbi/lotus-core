"""Validate governed Prometheus metric names, labels, and ownership."""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_COMMON_SRC = REPO_ROOT / "src" / "libs" / "portfolio-common"
if str(PORTFOLIO_COMMON_SRC) not in sys.path:
    sys.path.insert(0, str(PORTFOLIO_COMMON_SRC))

from portfolio_common.observability_contracts import (  # noqa: E402
    PORTFOLIO_SUPPORTABILITY_METRIC_LABELS,
    SERVICE_LOCAL_METRIC_OWNERS,
    TELEMETRY_METRIC_ALLOWED_LABELS,
    TELEMETRY_METRIC_FORBIDDEN_LABELS,
)

METRIC_CONSTRUCTORS = {"Counter", "Gauge", "Histogram", "Summary"}
METRIC_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
SHARED_METRIC_REGISTRY_PATH = "src/libs/portfolio-common/portfolio_common/monitoring.py"
LABEL_CONSTANTS = {
    "PORTFOLIO_SUPPORTABILITY_METRIC_LABELS": PORTFOLIO_SUPPORTABILITY_METRIC_LABELS,
}


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    labels: tuple[str, ...]
    file: str
    line: int


def _metric_constructor_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _literal_string_sequence(node: ast.AST | None) -> tuple[str, ...] | None:
    if node is None:
        return ()
    if isinstance(node, ast.Name):
        return LABEL_CONSTANTS.get(node.id)
    if not isinstance(node, ast.Tuple | ast.List):
        return None

    labels: list[str] = []
    for element in node.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            return None
        labels.append(element.value)
    return tuple(labels)


def _labels_node(call: ast.Call) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == "labelnames":
            return keyword.value
    if len(call.args) >= 3:
        return call.args[2]
    return None


def _iter_metric_definitions(
    repo_root: Path,
    source_roots: tuple[Path, ...],
) -> list[MetricDefinition]:
    definitions: list[MetricDefinition] = []
    for source_root in source_roots:
        for path in sorted(source_root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            relative_file = path.relative_to(repo_root).as_posix()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                constructor_name = _metric_constructor_name(node)
                if constructor_name not in METRIC_CONSTRUCTORS:
                    continue
                if not node.args or not isinstance(node.args[0], ast.Constant):
                    continue
                metric_name = node.args[0].value
                if not isinstance(metric_name, str):
                    continue
                labels = _literal_string_sequence(_labels_node(node))
                if labels is None:
                    labels = ("<dynamic>",)
                definitions.append(
                    MetricDefinition(
                        name=metric_name,
                        labels=labels,
                        file=relative_file,
                        line=node.lineno,
                    )
                )
    return definitions


def evaluate_metric_vocabulary(
    *,
    repo_root: Path = REPO_ROOT,
    source_roots: tuple[Path, ...] | None = None,
    allowed_labels: tuple[str, ...] = TELEMETRY_METRIC_ALLOWED_LABELS,
    forbidden_labels: tuple[str, ...] = TELEMETRY_METRIC_FORBIDDEN_LABELS,
    service_local_metric_owners: dict[str, str] = SERVICE_LOCAL_METRIC_OWNERS,
) -> list[dict[str, object]]:
    roots = source_roots or (repo_root / "src",)
    allowed_label_set = set(allowed_labels)
    forbidden_label_set = set(forbidden_labels)
    findings: list[dict[str, object]] = []

    for metric in _iter_metric_definitions(repo_root, roots):
        metric_findings: list[str] = []
        if not METRIC_NAME_PATTERN.fullmatch(metric.name):
            metric_findings.append("metric name must be lowercase snake_case")

        if "<dynamic>" in metric.labels:
            metric_findings.append(
                "metric labelnames must be a literal tuple/list or governed constant"
            )
        else:
            unknown_labels = sorted(set(metric.labels) - allowed_label_set)
            forbidden = sorted(set(metric.labels) & forbidden_label_set)
            if unknown_labels:
                metric_findings.append(f"unregistered labels: {', '.join(unknown_labels)}")
            if forbidden:
                metric_findings.append(f"forbidden labels: {', '.join(forbidden)}")

        is_shared_registry = metric.file == SHARED_METRIC_REGISTRY_PATH
        if not is_shared_registry and metric.name not in service_local_metric_owners:
            metric_findings.append("service-local metric has no explicit owner registration")

        if metric_findings:
            findings.append(
                {
                    "metric": metric.name,
                    "file": metric.file,
                    "line": metric.line,
                    "labels": list(metric.labels),
                    "violations": metric_findings,
                }
            )

    return findings


def main() -> int:
    findings = evaluate_metric_vocabulary()
    if findings:
        print("Metric vocabulary guard failed:")
        print(json.dumps(findings, indent=2))
        return 1
    print("Metric vocabulary guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
