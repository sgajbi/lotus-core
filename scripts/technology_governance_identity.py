"""Stable identities for text-backed technology-governance evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path


def normalized_text_sha256(path: Path) -> str:
    """Hash UTF-8 text independently of the checkout's newline convention."""

    normalized = path.read_text(encoding="utf-8").encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()
