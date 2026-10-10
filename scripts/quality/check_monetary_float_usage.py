"""Reject binary floating-point usage for monetary domain values."""

import argparse
import ast
import hashlib
import importlib
import json
import re
import subprocess  # nosec B404 - fixed Git executable, never a shell
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

KEYWORDS = (
    "amount",
    "price",
    "rate",
    "value",
    "market_value",
    "cost",
    "pnl",
    "return",
    "risk",
    "notional",
    "weight",
)
IGNORE_DIRS = {"tests", ".venv", "venv", "docs", "rfcs", "output", "build", "dist", "__pycache__"}

FLOAT_CONVERSION = re.compile(r"\bfloat\s*\(")
IDENTIFIER = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")
NON_DOMAIN_TOKENS = {"return", "float"}


def is_candidate(path: Path) -> bool:
    parts = set(path.parts)
    if any(p in parts for p in IGNORE_DIRS):
        return False
    return path.suffix == ".py"


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(  # nosec B603 - fixed executable and argument vector
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def _acquisition_commit(repo_root: Path) -> str:
    """Consume the existing acquisition action/binding, not another pin registry."""
    action = yaml.safe_load(
        (repo_root / ".github/actions/acquire-images/action.yml").read_text(encoding="utf-8")
    )
    # The acquisition owner already validates the complete action and qualified pin.
    # This repair can land independently: no acquisition directory means no dependency.
    validator = importlib.import_module(
        "scripts.quality.required_status_checks.image_acquisition_action"
    )
    validator.validate_action_payload(action)
    steps = action["runs"]["steps"]
    checkouts = [step for step in steps if step.get("uses") == "actions/checkout@v6"]
    if len(checkouts) != 1:
        raise ValueError("Acquisition must declare one governed checkout")
    checkout = checkouts[0]["with"]
    pin = checkout["ref"]
    if (
        checkout.get("repository") != "sgajbi/lotus-platform"
        or checkout.get("path") != ".lotus-platform"
        or checkout.get("persist-credentials") is not False
        or not isinstance(pin, str)
        or re.fullmatch(r"[0-9a-f]{40}", pin) is None
    ):
        raise ValueError("Acquisition ownership declaration is invalid")
    binding = ast.parse(
        (repo_root / "scripts/release/image_acquisition_bindings.py").read_text(encoding="utf-8")
    )
    pins = [
        ast.literal_eval(node.value)
        for node in binding.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "GOVERNANCE_SHA"
            for target in node.targets
        )
    ]
    if pins != [pin]:
        raise ValueError("Acquisition action and native binding pins differ")
    return pin


def _foreign_python_files(repo_root: Path) -> set[Path]:
    """Exclude only immutable acquired Python, never arbitrary hidden Core code."""
    foreign = repo_root / ".lotus-platform"
    if not foreign.exists() and not foreign.is_symlink():
        return set()
    try:
        pin = _acquisition_commit(repo_root)
        if foreign.is_symlink() or not foreign.is_dir():
            raise ValueError("Acquired source is not a real checkout directory")
        if _git(repo_root, "ls-files", "--", ".lotus-platform"):
            raise ValueError("Core-tracked content cannot be classified as foreign")
        if Path(_git(foreign, "rev-parse", "--show-toplevel")).resolve() != foreign.resolve():
            raise ValueError("Acquired source has no independent Git ownership")
        if _git(foreign, "remote", "get-url", "origin") not in {
            "https://github.com/sgajbi/lotus-platform",
            "https://github.com/sgajbi/lotus-platform.git",
            "git@github.com:sgajbi/lotus-platform.git",
        }:
            raise ValueError("Acquired source origin is not Platform")
        if _git(foreign, "rev-parse", "HEAD") != pin:
            raise ValueError("Acquired source is not the native acquisition pin")
        if _git(foreign, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError("Acquired source contains modified or injected files")
        tracked: dict[Path, str] = {}
        for entry in _git(foreign, "ls-tree", "-rz", "HEAD").split("\0"):
            if not entry:
                continue
            metadata, name = entry.split("\t", 1)
            if name.endswith(".py"):
                mode, kind, blob = metadata.split()
                if mode not in {"100644", "100755"} or kind != "blob":
                    raise ValueError("Acquired Python is not a regular committed file")
                tracked[foreign / name] = blob
        actual = set(foreign.rglob("*.py"))
        if (
            not tracked
            or actual != set(tracked)
            or any(path.is_symlink() for path in foreign.rglob("*"))
        ):
            raise ValueError("Acquired Python inventory is empty, injected or redirected")
        for path, blob in tracked.items():
            content = path.read_bytes()
            # Git blob identity, not a cryptographic approval or a new trust registry.
            actual_blob = hashlib.sha1(
                f"blob {len(content)}\0".encode() + content, usedforsecurity=False
            ).hexdigest()
            if actual_blob != blob:
                raise ValueError("Acquired Python bytes differ from the pinned committed blob")
        return actual
    except (
        OSError,
        ImportError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        SyntaxError,
        yaml.YAMLError,
        subprocess.SubprocessError,
    ) as exc:
        raise ValueError(f"Foreign source ownership verification failed: {exc}") from exc


def scan_repo(repo_root: Path) -> list[str]:
    foreign_files = _foreign_python_files(repo_root)
    findings: list[str] = []
    for file_path in repo_root.rglob("*.py"):
        if file_path in foreign_files:
            continue
        if not is_candidate(file_path.relative_to(repo_root)):
            continue
        rel = file_path.relative_to(repo_root).as_posix()
        source = file_path.read_text(encoding="utf-8")
        source_lines = source.splitlines()
        for line_no, line in enumerate(source_lines, start=1):
            lowered = line.lower()
            if not _contains_monetary_keyword(lowered):
                continue
            if not FLOAT_CONVERSION.search(lowered):
                continue
            if "# monetary-float-allow" in lowered:
                continue
            finding = f"{rel}:{line_no}:{line.strip()}"
            findings.append(finding)
        findings.extend(_monetary_annotation_findings(rel, source, source_lines))
    return sorted(set(findings))


def _monetary_annotation_findings(
    relative_path: str, source: str, source_lines: list[str]
) -> list[str]:
    tree = ast.parse(source, filename=relative_path)
    findings: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_arguments = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            if node.args.vararg is not None:
                function_arguments += (node.args.vararg,)
            if node.args.kwarg is not None:
                function_arguments += (node.args.kwarg,)
            for argument in function_arguments:
                if (
                    _annotation_contains_float(argument.annotation)
                    and _contains_monetary_keyword(argument.arg)
                    and not _line_allows_float(argument.lineno, source_lines)
                ):
                    findings.append(_format_finding(relative_path, argument.lineno, source_lines))
            if (
                _annotation_contains_float(node.returns)
                and _contains_monetary_keyword(node.name)
                and not _line_allows_float(node.returns.lineno, source_lines)
            ):
                findings.append(_format_finding(relative_path, node.returns.lineno, source_lines))
        elif (
            isinstance(node, ast.AnnAssign)
            and _annotation_contains_float(node.annotation)
            and _contains_monetary_keyword(_assignment_target_name(node.target))
            and not _line_allows_float(node.lineno, source_lines)
        ):
            findings.append(_format_finding(relative_path, node.lineno, source_lines))

    return findings


def _annotation_contains_float(annotation: ast.expr | None) -> bool:
    return annotation is not None and any(
        isinstance(node, ast.Name) and node.id == "float" for node in ast.walk(annotation)
    )


def _assignment_target_name(target: ast.expr) -> str:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def _format_finding(relative_path: str, line_number: int, source_lines: list[str]) -> str:
    line = source_lines[line_number - 1]
    return f"{relative_path}:{line_number}:{line.strip()}"


def _line_allows_float(line_number: int, source_lines: list[str]) -> bool:
    return "# monetary-float-allow" in source_lines[line_number - 1].lower()


def _contains_monetary_keyword(line: str) -> bool:
    tokens = set(_identifier_tokens(line))
    return any(keyword in tokens for keyword in KEYWORDS)


def _identifier_tokens(line: str) -> list[str]:
    tokens: list[str] = []
    for identifier in IDENTIFIER.findall(line):
        normalized_identifier = identifier.lower()
        if normalized_identifier == "value":
            continue
        for token in normalized_identifier.split("_"):
            if token and token not in NON_DOMAIN_TOKENS:
                tokens.append(token)
    return tokens


def _parse_review_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(f"Invalid review_by date format: {value!r}, expected YYYY-MM-DD") from exc


def load_allowlist(path: Path) -> tuple[dict[str, dict], list[str], list[str]]:
    if not path.exists():
        return {}, [], []
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_entries = data.get("allowlist", [])
    entries: dict[str, dict] = {}
    errors: list[str] = []
    stale: list[str] = []
    today = datetime.now(tz=UTC).date()
    for item in raw_entries:
        if isinstance(item, str):
            errors.append(f"Legacy allowlist string entry must be migrated: {item}")
            continue
        if not isinstance(item, dict):
            errors.append(f"Allowlist entry must be object, found: {type(item).__name__}")
            continue
        finding = item.get("finding")
        justification = item.get("justification")
        owner = item.get("owner")
        review_by = item.get("review_by")
        if not all([finding, justification, owner, review_by]):
            errors.append(
                "Allowlist entry missing required fields (finding/justification/owner/review_by): "
                + json.dumps(item, sort_keys=True)
            )
            continue
        try:
            review_dt = _parse_review_date(str(review_by))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if review_dt.date() < today:
            stale.append(str(finding))
        entries[str(finding)] = {
            "finding": str(finding),
            "justification": str(justification),
            "owner": str(owner),
            "review_by": review_dt.strftime("%Y-%m-%d"),
        }
    return entries, errors, stale


def write_allowlist(
    path: Path, findings: list[str], existing_entries: dict[str, dict], review_by: str
) -> None:
    generated_at = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    allowlist_entries: list[dict] = []
    for finding in sorted(set(findings)):
        if finding in existing_entries:
            allowlist_entries.append(existing_entries[finding])
            continue
        allowlist_entries.append(
            {
                "finding": finding,
                "justification": "Temporary approved monetary float usage; migrate to Decimal.",
                "owner": "platform-governance",
                "review_by": review_by,
            }
        )
    payload = {
        "description": "Approved baseline monetary-float findings. New findings fail CI.",
        "policy_version": "1.1.0",
        "generated_at": generated_at,
        "allowlist": allowlist_entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard against unauthorized monetary float usage")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--allowlist",
        default="docs/standards/monetary-float-allowlist.json",
    )
    parser.add_argument("--update-allowlist", action="store_true")
    parser.add_argument(
        "--default-review-days",
        type=int,
        default=180,
        help="Days until review_by for newly generated allowlist entries.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    allowlist_path = (repo_root / args.allowlist).resolve()
    try:
        findings = scan_repo(repo_root)
    except ValueError as exc:
        print(str(exc))
        return 1
    allowlist_entries, allowlist_errors, stale_entries = load_allowlist(allowlist_path)

    if args.update_allowlist:
        review_deadline = datetime.now(tz=UTC) + timedelta(days=args.default_review_days)
        default_review_by = review_deadline.strftime("%Y-%m-%d")
        write_allowlist(allowlist_path, findings, allowlist_entries, default_review_by)
        print(f"Updated allowlist with {len(findings)} finding(s): {allowlist_path}")
        return 0

    if allowlist_errors:
        print("Allowlist schema validation failed:")
        for item in allowlist_errors:
            print(f" - {item}")
        return 1

    if stale_entries:
        print("Allowlist contains stale entries (review_by in the past):")
        for item in stale_entries:
            print(f" - {item}")
        print(f"\nUpdate {allowlist_path} with refreshed review dates and remediation status.")
        return 1

    unexpected = sorted(set(findings) - set(allowlist_entries))
    unused_allowlist_entries = sorted(set(allowlist_entries) - set(findings))

    if unused_allowlist_entries:
        print("Allowlist contains entries that no longer match active findings:")
        for item in unused_allowlist_entries:
            print(f" - {item}")
        print(f"\nRemove stale entries from {allowlist_path}.")
        return 1

    if unexpected:
        print("Unauthorized monetary float usage detected:")
        for item in unexpected:
            print(f" - {item}")
        print(f"\nBaseline allowlist file: {allowlist_path}")
        print("If intentional and approved, run with --update-allowlist in dedicated PR.")
        return 1

    print(
        "Monetary float guard passed. "
        f"Findings={len(findings)}, allowlisted={len(allowlist_entries)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
