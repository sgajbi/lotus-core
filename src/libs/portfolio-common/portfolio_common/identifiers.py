def normalize_lookup_identifier(identifier: object) -> str:
    """Normalize source-system identifiers for tolerant read-boundary lookups."""
    return str(identifier or "").strip()
