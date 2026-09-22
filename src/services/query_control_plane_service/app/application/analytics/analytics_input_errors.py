"""Application-level analytics input failures mapped by the HTTP adapter."""


class AnalyticsInputError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)
