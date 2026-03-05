# src/core/enums/cost_method.py

from enum import Enum


class CostMethod(str, Enum):
    """
    Defines the available cost basis calculation methods.
    """

    FIFO = "FIFO"
    AVERAGE_COST = "AVERAGE_COST"
