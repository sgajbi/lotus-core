"""Conservative source-surface decisions and actual merge-base/event identity proof."""

import json
import subprocess

import pytest

from scripts.quality import change_classification as classifier


@pytest.mark.parametrize(
    "path",
    ["README.md", "wiki/Validation-and-CI.md", "docs/architecture/codebase-reviews/CR-1558.md"],
)
def test_only_allowlisted_authored_documents_can_select_docs_only(path):
    changes = classifier.parse_changes(f"M\0{path}\0")
    assert classifier.classify_changes(changes)[0] == "docs-only"


@pytest.mark.parametrize(
    "path",
    [
        "src/services/query_service/app/main.py",
        "tests/unit/test_example.py",
        "alembic/versions/example.py",
        "contracts/openapi.json",
        "docs/standards/openapi.json",
        ".github/workflows/pr-merge-gate.yml",
        "requirements/shared-runtime.lock.txt",
        "src/services/query_service/Dockerfile",
        "docker-compose.yml",
        "src/libs/portfolio-common/portfolio_common/database_models.py",
        "Makefile",
        "pyproject.toml",
        "package.json",
        "unknown.md",
        "scripts/quality/change_classification.py",
        "quality/module-size-baseline.v1.json",
        "docs/generated/openapi.md",
        "docs/operations/config.json",
        "wiki/nested/unknown.md",
        "../README.md",
        "/README.md",
        "wiki\\Validation-and-CI.md",
    ],
)
def test_runtime_governance_contracts_dependencies_and_unknown_are_full(path):
    changes = classifier.parse_changes(f"M\0README.md\0A\0{path}\0")
    assert classifier.classify_changes(changes)[0] == "full"


@pytest.mark.parametrize("status", ["D", "T", "U", "R100", "C100", "X"])
def test_deletions_renames_copies_type_changes_and_unknown_status_are_full(status):
    record = f"{status}\0README.md\0"
    if status.startswith(("R", "C")):
        record += "wiki/Validation-and-CI.md\0"
    changes = classifier.parse_changes(record)
    assert classifier.classify_changes(changes)[0] == "full"


@pytest.mark.parametrize("raw", ["M\0README.md", "M\0", "R100\0README.md\0", "M\0\0"])
def test_malformed_diff_cannot_produce_docs_only(raw):
    with pytest.raises(ValueError):
        classifier.parse_changes(raw)


def test_empty_diff_is_full():
    assert classifier.parse_changes("") == []
    assert classifier.classify_changes([]) == ("full", ["empty-diff"])


@pytest.fixture
def document_repository(tmp_path):
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Classification Test")
    git("config", "user.email", "classification@example.invalid")
    document = tmp_path / "README.md"
    document.write_text("Baseline\n", encoding="utf-8")
    git("add", "README.md")
    git("-c", "commit.gpgsign=false", "commit", "-qm", "baseline")
    base = git("rev-parse", "HEAD")
    document.write_text("Authored correction\n", encoding="utf-8")
    git("add", "README.md")
    git("-c", "commit.gpgsign=false", "commit", "-qm", "document correction")
    return tmp_path, git, base, git("rev-parse", "HEAD")


def test_real_merge_base_and_executable_document_refusal(document_repository):
    root, git, base, head = document_repository
    plan = classifier.classify_range(base, head, root=root)
    assert plan["mode"] == "docs-only"
    assert plan["base_sha"] == plan["merge_base_sha"] == base
    assert plan["source_head_sha"] == head
    git("update-index", "--chmod=+x", "README.md")
    git("-c", "commit.gpgsign=false", "commit", "-qm", "executable document")
    assert classifier.classify_range(base, "HEAD", root=root)["mode"] == "full"
    assert classifier.classify_range(head, head, root=root)["mode"] == "full"


@pytest.fixture
def pull_request_event(document_repository, monkeypatch):
    root, git, base, head = document_repository
    event_path = root / "event.json"
    event = {
        "pull_request": {
            "number": 123,
            "base": {"sha": base, "ref": "main", "repo": {"full_name": classifier.REPOSITORY}},
            "head": {"sha": head},
        }
    }
    event_path.write_text(json.dumps(event), encoding="utf-8")
    for key, value in {
        "GITHUB_REPOSITORY": classifier.REPOSITORY,
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_SHA": head,
        "GITHUB_WORKFLOW": "Pull Request Merge Gate",
        "GITHUB_RUN_ID": "456",
    }.items():
        monkeypatch.setenv(key, value)
    return root, git, event, event_path


def test_exact_pr_event_selects_documentation_with_auditable_identity(pull_request_event):
    root, _, event, _ = pull_request_event
    plan = classifier.current_plan(root=root)
    assert plan["mode"] == "docs-only"
    assert plan["source_head_sha"] == plan["checkout_sha"] == event["pull_request"]["head"]["sha"]
    assert plan["run_id"] == "456"
    assert plan["pr_number"] == 123


def test_exact_synthetic_merge_retains_source_diff_and_rejects_wrong_parent_order(
    pull_request_event, monkeypatch
):
    root, git, event, event_path = pull_request_event
    source = event["pull_request"]["head"]["sha"]
    git("checkout", "-qb", "base-update", event["pull_request"]["base"]["sha"])
    (root / "base-only.py").write_text("BASE = 1\n", encoding="utf-8")
    git("add", "base-only.py")
    git("-c", "commit.gpgsign=false", "commit", "-qm", "main advance")
    base = git("rev-parse", "HEAD")
    event["pull_request"]["base"]["sha"] = base
    event_path.write_text(json.dumps(event), encoding="utf-8")
    git("-c", "commit.gpgsign=false", "merge", "--no-ff", "-qm", "PR merge", source)
    monkeypatch.setenv("GITHUB_SHA", git("rev-parse", "HEAD"))
    plan = classifier.current_plan(root=root)
    assert plan["mode"] == "docs-only"
    assert plan["source_head_sha"] == source
    assert plan["base_sha"] == base
    assert [change["path"] for change in plan["changes"]] == ["README.md"]
    git("checkout", "--detach", source)
    git("-c", "commit.gpgsign=false", "merge", "--no-ff", "-qm", "wrong parents", base)
    monkeypatch.setenv("GITHUB_SHA", git("rev-parse", "HEAD"))
    assert classifier.current_plan(root=root)["mode"] == "full"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GITHUB_EVENT_NAME", "workflow_dispatch"),
        ("GITHUB_EVENT_NAME", "merge_group"),
        ("GITHUB_WORKFLOW", "Main Releasability Gate"),
        ("GITHUB_SHA", "wrong"),
        ("GITHUB_REPOSITORY", "other/repository"),
        ("GITHUB_EVENT_PATH", "missing.json"),
    ],
)
def test_unverified_or_non_pr_context_is_full(pull_request_event, monkeypatch, key, value):
    root, _, _, _ = pull_request_event
    monkeypatch.setenv(key, value)
    monkeypatch.setenv("LOTUS_PR_VALIDATION_MODE", "docs-only")
    assert classifier.current_plan(root=root)["mode"] == "full"


def test_wrong_source_wrong_base_dirty_checkout_and_absent_refs_fail_closed(pull_request_event):
    root, _, event, event_path = pull_request_event
    original = json.loads(json.dumps(event))
    for section, key, value in [
        ("head", "sha", "missing"),
        ("base", "ref", "other"),
        ("base", "sha", "missing"),
    ]:
        changed = json.loads(json.dumps(original))
        changed["pull_request"][section][key] = value
        event_path.write_text(json.dumps(changed), encoding="utf-8")
        assert classifier.current_plan(root=root)["mode"] == "full"
    event_path.write_text(json.dumps(original), encoding="utf-8")
    (root / "README.md").write_text("Uncommitted change\n", encoding="utf-8")
    assert classifier.current_plan(root=root)["mode"] == "full"
