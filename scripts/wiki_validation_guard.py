from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
WIKI_DIR = "wiki"
SIDEBAR_FILE = "_Sidebar.md"

MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SAFE_WIKI_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*\.md$")


def evaluate_wiki_source(*, repo_root: Path = REPO_ROOT) -> list[str]:
    wiki_root = repo_root / WIKI_DIR
    sidebar_path = wiki_root / SIDEBAR_FILE
    errors: list[str] = []

    if not wiki_root.is_dir():
        return [f"wiki source directory does not exist: {wiki_root.relative_to(repo_root)}"]
    if not sidebar_path.is_file():
        return [f"wiki sidebar does not exist: {sidebar_path.relative_to(repo_root)}"]

    wiki_pages = _wiki_pages(wiki_root)
    linked_pages = _sidebar_linked_pages(sidebar_path, repo_root=repo_root)

    errors.extend(_missing_sidebar_targets(linked_pages, repo_root=repo_root))
    errors.extend(_orphaned_wiki_pages(wiki_pages, linked_pages, repo_root=repo_root))
    errors.extend(_unsafe_page_names(wiki_pages, repo_root=repo_root))
    errors.extend(_invalid_page_headings(wiki_pages, repo_root=repo_root))
    errors.extend(_broken_markdown_links(wiki_pages, repo_root=repo_root))
    return errors


def evaluate_publication_parity(
    *,
    repo_root: Path = REPO_ROOT,
    published_wiki_dir: Path,
) -> list[str]:
    wiki_root = repo_root / WIKI_DIR
    authored_pages = _markdown_files(wiki_root)
    published_pages = _markdown_files(published_wiki_dir)
    errors: list[str] = []

    for missing in sorted(authored_pages.keys() - published_pages.keys()):
        errors.append(f"published wiki is missing authored page: {missing}")
    for extra in sorted(published_pages.keys() - authored_pages.keys()):
        errors.append(f"published wiki has page absent from repo source: {extra}")
    for page_name in sorted(authored_pages.keys() & published_pages.keys()):
        if authored_pages[page_name].read_text(encoding="utf-8") != published_pages[
            page_name
        ].read_text(encoding="utf-8"):
            errors.append(f"published wiki page differs from repo source: {page_name}")
    return errors


def _markdown_files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    return {path.name: path for path in root.glob("*.md")}


def _wiki_pages(wiki_root: Path) -> tuple[Path, ...]:
    return tuple(sorted(path for path in wiki_root.glob("*.md") if path.name != SIDEBAR_FILE))


def _sidebar_linked_pages(sidebar_path: Path, *, repo_root: Path) -> set[Path]:
    linked_pages: set[Path] = set()
    for link_target in _markdown_link_targets(sidebar_path.read_text(encoding="utf-8")):
        resolved = _resolve_link_target(sidebar_path, link_target, repo_root=repo_root)
        if resolved is not None and resolved.parent == repo_root / WIKI_DIR:
            linked_pages.add(resolved)
    return linked_pages


def _missing_sidebar_targets(linked_pages: set[Path], *, repo_root: Path) -> list[str]:
    return [
        f"sidebar links to missing wiki page: {_repo_relative(page, repo_root)}"
        for page in sorted(linked_pages)
        if not page.is_file()
    ]


def _orphaned_wiki_pages(
    wiki_pages: tuple[Path, ...],
    linked_pages: set[Path],
    *,
    repo_root: Path,
) -> list[str]:
    return [
        f"wiki page is not linked from sidebar: {_repo_relative(page, repo_root)}"
        for page in wiki_pages
        if page not in linked_pages
    ]


def _unsafe_page_names(wiki_pages: tuple[Path, ...], *, repo_root: Path) -> list[str]:
    return [
        f"wiki page name is not publication-safe: {_repo_relative(page, repo_root)}"
        for page in wiki_pages
        if not SAFE_WIKI_FILENAME_RE.fullmatch(page.name)
    ]


def _invalid_page_headings(wiki_pages: tuple[Path, ...], *, repo_root: Path) -> list[str]:
    errors: list[str] = []
    for page in wiki_pages:
        first_content_line = _first_content_line(page)
        if first_content_line is None:
            errors.append(f"wiki page is empty: {_repo_relative(page, repo_root)}")
        elif not first_content_line.startswith("# "):
            errors.append(
                f"wiki page must start with a single H1 heading: {_repo_relative(page, repo_root)}"
            )
    return errors


def _first_content_line(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _broken_markdown_links(paths: tuple[Path, ...], *, repo_root: Path) -> list[str]:
    errors: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for link_target in _markdown_link_targets(text):
            resolved = _resolve_link_target(path, link_target, repo_root=repo_root)
            if resolved is not None and not resolved.exists():
                errors.append(
                    f"{_repo_relative(path, repo_root)} links to missing path: {link_target}"
                )
    return errors


def _markdown_link_targets(text: str) -> tuple[str, ...]:
    return tuple(match.group(1).strip() for match in MARKDOWN_LINK_RE.finditer(text))


def _resolve_link_target(source_path: Path, raw_target: str, *, repo_root: Path) -> Path | None:
    target = _clean_link_target(raw_target)
    if not target or target.startswith("#") or _is_external_link(target):
        return None
    if target.startswith("/"):
        return _with_markdown_suffix(repo_root / target.lstrip("/"))

    target_path = Path(target)
    if target_path.is_absolute():
        return None
    if "/" not in target and "\\" not in target:
        return _with_markdown_suffix(repo_root / WIKI_DIR / target)
    if target.startswith(("docs/", "src/", "contracts/", "quality/", "scripts/", "tests/")):
        return _with_markdown_suffix(repo_root / target)
    return _with_markdown_suffix(source_path.parent / target)


def _clean_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    target = target.split("#", 1)[0].split("?", 1)[0]
    return unquote(target)


def _is_external_link(target: str) -> bool:
    parsed = urlparse(target)
    return parsed.scheme in {"http", "https", "mailto"}


def _with_markdown_suffix(path: Path) -> Path:
    if path.suffix:
        return path
    markdown_candidate = path.with_suffix(".md")
    if markdown_candidate.exists() or path.parent.name == WIKI_DIR:
        return markdown_candidate
    return path


def _repo_relative(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate repo-authored Lotus wiki source.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--published-wiki-dir", type=Path, default=None)
    args = parser.parse_args()

    errors = evaluate_wiki_source(repo_root=args.repo_root)
    if args.published_wiki_dir is not None:
        errors.extend(
            evaluate_publication_parity(
                repo_root=args.repo_root,
                published_wiki_dir=args.published_wiki_dir,
            )
        )

    if errors:
        print("Wiki validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Wiki validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
