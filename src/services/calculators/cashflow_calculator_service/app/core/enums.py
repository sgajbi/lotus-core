# src/services/calculators/cashflow_calculator_service/app/core/enums.py
from enum import Enum


class CashflowTiming(str, Enum):
    """Defines if the cashflow occurs at the beginning or end of the day."""

    BOD = "BOD"  # Beginning of Day
    EOD = "EOD"  # End of Day


class CashflowCalculationType(str, Enum):
    """Defines the method used to calculate the cashflow amount."""

    NET = "NET"
    GROSS = "GROSS"
    MVT = "MVT"  # Market Value Transaction


class CashflowClassification(str, Enum):
    """Standardized classification of the cashflow's purpose."""

    INVESTMENT_OUTFLOW = "INVESTMENT_OUTFLOW"
    INVESTMENT_INFLOW = "INVESTMENT_INFLOW"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    CASHFLOW_IN = "CASHFLOW_IN"
    CASHFLOW_OUT = "CASHFLOW_OUT"
    INTERNAL = "INTERNAL"
    TRANSFER = "TRANSFER"
