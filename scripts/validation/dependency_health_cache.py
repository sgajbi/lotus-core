"""Content-addressed cache identity and integrity markers for dependency health proof."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

CACHE_SCHEMA_VERSION = 1
CACHE_MARKER_FILE = "dependency-health-cache.json"


@dataclass(frozen=True)
class DependencyHealthCacheIdentity:
    """Immutable identity for one compatible dependency-health environment."""

    key: str
    python_identity: str
    platform_identity: str
    installer_version: str
    input_digests: tuple[tuple[str, str], ...]
    schema_version: int = CACHE_SCHEMA_VERSION

    def marker_payload(self) -> dict[str, object]:
        """Return the canonical successful-cache marker payload."""
        payload = asdict(self)
        payload["input_digests"] = [list(item) for item in self.input_digests]
        return payload


def discover_cache_inputs(
    root: Path,
    *,
    implementation_files: Iterable[Path] = (),
) -> tuple[Path, ...]:
    """Discover every dependency, packaging, and cache-policy input used by the proof."""
    candidates = {
        root / "pyproject.toml",
        root / "tests" / "requirements.txt",
        *root.glob("requirements/**/*.txt"),
        *root.glob("src/**/pyproject.toml"),
        *implementation_files,
    }
    return tuple(sorted(path.resolve() for path in candidates if path.is_file()))


def build_cache_identity(
    root: Path,
    *,
    installer_version: str,
    implementation_files: Iterable[Path] = (),
    python_identity: str | None = None,
    platform_identity: str | None = None,
) -> DependencyHealthCacheIdentity:
    """Build a deterministic SHA-256 identity from runtime and authored inputs."""
    resolved_root = root.resolve()
    resolved_python_identity = python_identity or _current_python_identity()
    resolved_platform_identity = platform_identity or _current_platform_identity()
    input_digests = tuple(
        (
            path.relative_to(resolved_root).as_posix(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in discover_cache_inputs(
            resolved_root,
            implementation_files=implementation_files,
        )
    )
    key_material = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "python_identity": resolved_python_identity,
        "platform_identity": resolved_platform_identity,
        "installer_version": installer_version,
        "input_digests": input_digests,
    }
    key = hashlib.sha256(
        json.dumps(key_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return DependencyHealthCacheIdentity(
        key=key,
        python_identity=resolved_python_identity,
        platform_identity=resolved_platform_identity,
        installer_version=installer_version,
        input_digests=input_digests,
    )


def cache_marker_matches(cache_dir: Path, identity: DependencyHealthCacheIdentity) -> bool:
    """Return whether a cache carries the exact successful identity marker."""
    marker_path = cache_dir / CACHE_MARKER_FILE
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return payload == identity.marker_payload()


def write_cache_marker(cache_dir: Path, identity: DependencyHealthCacheIdentity) -> None:
    """Atomically publish a successful dependency-health cache marker."""
    marker_path = cache_dir / CACHE_MARKER_FILE
    temporary_path = marker_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(identity.marker_payload(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(marker_path)


def _current_python_identity() -> str:
    return ":".join(
        (
            sys.implementation.name,
            platform.python_version(),
            sys.implementation.cache_tag or "no-cache-tag",
        )
    )


def _current_platform_identity() -> str:
    return ":".join((platform.system(), platform.machine(), sys.platform))
