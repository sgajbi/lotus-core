"""Read port for effective classification taxonomy evidence."""

from datetime import date
from typing import Protocol

from ..domain.classification_taxonomy import ClassificationTaxonomyEvidence


class ClassificationTaxonomyReader(Protocol):
    """Read governed taxonomy labels without exposing persistence models."""

    async def list_effective(
        self, *, as_of_date: date, taxonomy_scope: str | None
    ) -> list[ClassificationTaxonomyEvidence]: ...
