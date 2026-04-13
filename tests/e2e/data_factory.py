import uuid


def unique_suffix(length: int = 8) -> str:
    return uuid.uuid4().hex[:length].upper()


def unique_id(prefix: str, *, length: int = 8) -> str:
    return f"{prefix}_{unique_suffix(length)}"
