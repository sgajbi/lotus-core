"""Port for opaque continuation-token encoding and validation."""

from typing import Any, Protocol


class PageTokenCodecPort(Protocol):
    """Encode and validate opaque, request-bound page tokens."""

    def decode(self, token: str | None) -> dict[str, Any]: ...

    def encode(self, payload: dict[str, Any]) -> str: ...
