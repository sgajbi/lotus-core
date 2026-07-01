class OutboxRecoveryRejected(RuntimeError):
    def __init__(self, message: str, *, metadata: dict[str, object] | None = None):
        super().__init__(message)
        self.message = message
        self.metadata = metadata or {}
