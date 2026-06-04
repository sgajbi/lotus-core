from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _add_source_paths() -> None:
    source_paths = [
        ROOT,
        ROOT / "src",
        ROOT / "src" / "libs" / "portfolio-common",
    ]
    for source_path in reversed(source_paths):
        source_path_text = str(source_path)
        if source_path_text not in sys.path:
            sys.path.insert(0, source_path_text)


def main() -> int:
    _add_source_paths()
    try:
        from importlinter.cli import lint_imports
    except ModuleNotFoundError as exc:
        print(
            "import-linter is required for the import boundary gate. "
            "Install it with `python -m pip install import-linter`.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    return lint_imports(config_filename=str(ROOT / ".importlinter"))


if __name__ == "__main__":
    raise SystemExit(main())
