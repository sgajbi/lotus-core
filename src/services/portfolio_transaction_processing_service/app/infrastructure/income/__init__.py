"""Expose income-state infrastructure adapters."""

from .accrued_income_offset_repository import SqlAlchemyAccruedIncomeOffsetRepository

__all__ = ["SqlAlchemyAccruedIncomeOffsetRepository"]
