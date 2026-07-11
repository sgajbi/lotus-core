"""Effective-dated benchmark constituent segment resolution policy."""

from dataclasses import replace
from datetime import date, timedelta

from ..domain.benchmark_definition import BenchmarkComponentEvidence


def resolve_benchmark_component_segments(
    components: list[BenchmarkComponentEvidence],
    *,
    start_date: date,
    end_date: date,
) -> list[BenchmarkComponentEvidence]:
    """Resolve non-overlapping constituent segments within a requested date window."""

    resolved: list[BenchmarkComponentEvidence] = []
    by_index: dict[str, list[BenchmarkComponentEvidence]] = {}
    for component in components:
        by_index.setdefault(component.index_id, []).append(component)
    for rows in by_index.values():
        ordered = sorted(rows, key=lambda row: row.composition_effective_from)
        for position, component in enumerate(ordered):
            next_component = ordered[position + 1] if position + 1 < len(ordered) else None
            resolved_end = component.composition_effective_to
            if next_component is not None:
                inferred_end = next_component.composition_effective_from - timedelta(days=1)
                if (
                    resolved_end is None
                    or resolved_end >= next_component.composition_effective_from
                ):
                    resolved_end = inferred_end
                else:
                    resolved_end = min(resolved_end, inferred_end)
            if component.composition_effective_from > end_date:
                continue
            if resolved_end is not None and resolved_end < start_date:
                continue
            resolved.append(replace(component, composition_effective_to=resolved_end))
    return sorted(
        resolved,
        key=lambda row: (row.composition_effective_from, row.index_id),
    )
