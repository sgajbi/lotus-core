from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path("src/services")
REPOSITORY_PATH_PART = "/app/repositories/"
EXCLUDED_PATH_PARTS = ("/build/lib/",)
TRANSACTION_TOKENS = ("commit(", "rollback(")
TRANSITIONAL_TRANSACTION_EXCEPTIONS = {
    Path("src/services/query_service/app/repositories/operations_repository.py"): (
        "operator control-plane maintenance repository still owns standalone status updates; "
        "migrate behind an explicit unit-of-work slice before removing this exception"
    ),
}


@dataclass(frozen=True, slots=True)
class RepositoryTransactionBoundaryFinding:
    path: str
    token: str
    reason: str


def _repository_paths(root: Path) -> list[Path]:
    service_root = root / REPOSITORY_ROOT
    if not service_root.exists():
        return []
    return [
        path
        for path in service_root.rglob("*.py")
        if REPOSITORY_PATH_PART in path.relative_to(root).as_posix()
        and not any(
            excluded_part in path.relative_to(root).as_posix()
            for excluded_part in EXCLUDED_PATH_PARTS
        )
    ]


def _transaction_tokens_in_source(source: str) -> list[str]:
    return [token for token in TRANSACTION_TOKENS if token in source]


def find_repository_transaction_boundary_findings(
    root: Path,
) -> list[RepositoryTransactionBoundaryFinding]:
    findings: list[RepositoryTransactionBoundaryFinding] = []
    exception_hits: set[Path] = set()

    for path in _repository_paths(root):
        relative_path = path.relative_to(root)
        source = path.read_text(encoding="utf-8")
        tokens = _transaction_tokens_in_source(source)
        if not tokens:
            continue
        if relative_path in TRANSITIONAL_TRANSACTION_EXCEPTIONS:
            exception_hits.add(relative_path)
            continue
        for token in tokens:
            findings.append(
                RepositoryTransactionBoundaryFinding(
                    path=relative_path.as_posix(),
                    token=token,
                    reason=(
                        "repository modules must stage persistence changes and leave "
                        "commit/rollback to a unit-of-work boundary"
                    ),
                )
            )

    for exception_path, reason in TRANSITIONAL_TRANSACTION_EXCEPTIONS.items():
        path = root / exception_path
        if not path.exists():
            findings.append(
                RepositoryTransactionBoundaryFinding(
                    path=exception_path.as_posix(),
                    token="<missing-exception-file>",
                    reason="remove stale repository transaction exception or restore the file",
                )
            )
            continue
        if exception_path not in exception_hits:
            findings.append(
                RepositoryTransactionBoundaryFinding(
                    path=exception_path.as_posix(),
                    token="<stale-exception>",
                    reason=reason,
                )
            )

    return findings


def main() -> int:
    findings = find_repository_transaction_boundary_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.token}: {finding.reason}")
        return 1
    print("Repository transaction boundary guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
