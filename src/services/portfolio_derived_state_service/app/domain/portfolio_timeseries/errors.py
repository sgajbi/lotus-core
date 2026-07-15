"""Domain errors for invalid portfolio-timeseries contribution sets."""


class PortfolioTimeseriesCalculationError(ValueError):
    """Base error for invalid portfolio-timeseries calculation inputs."""


class InvalidPortfolioPositionContribution(PortfolioTimeseriesCalculationError):
    """Reject one contribution whose identity or FX rate is invalid."""


class InvalidPortfolioAggregationScope(PortfolioTimeseriesCalculationError):
    """Reject a portfolio aggregation scope without authoritative identity."""


class PortfolioContributionScopeMismatch(PortfolioTimeseriesCalculationError):
    """Reject a position contribution belonging to another portfolio."""


class PortfolioContributionWindowMismatch(PortfolioTimeseriesCalculationError):
    """Reject a contribution later than the target date or processing epoch."""


class DuplicatePortfolioPositionContribution(PortfolioTimeseriesCalculationError):
    """Reject duplicate security contributions that would overstate a portfolio."""
