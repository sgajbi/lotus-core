"""Read port for effective classification taxonomy evidence."""

from datetime import date
from typing import Protocol

from portfolio_common.api_contract.classification_history import (
    ClassificationHistorySelection,
    RetainedClassificationCut,
)

from ..domain.classification_taxonomy import ClassificationTaxonomyEvidence


class ClassificationTaxonomyReader(Protocol):
    """Read governed taxonomy labels without exposing persistence models."""

    async def list_effective(
        self, *, as_of_date: date, taxonomy_scope: str | None
    ) -> list[ClassificationTaxonomyEvidence]: ...

    async def load_cut(
        self, selection: ClassificationHistorySelection
    ) -> RetainedClassificationCut | None: ...
