"""Infrastructure adapter binding shared signed page tokens to one API route."""

from dataclasses import dataclass
from typing import Any, cast

from portfolio_common.page_tokens import PageTokenCodec


@dataclass(frozen=True, slots=True)
class RouteScopedPageTokenCodec:
    """Encode and validate page tokens within one immutable route scope."""

    codec: PageTokenCodec
    route: str

    def encode(self, payload: dict[str, Any]) -> str:
        return cast(str, self.codec.encode(payload, route=self.route))

    def decode(self, token: str | None) -> dict[str, Any]:
        return cast(dict[str, Any], self.codec.decode(token, route=self.route))
