class ServiceError(RuntimeError):
    """A request the caller can fix: validation, a missing record, or a rejected AI response."""

    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.status = status
        self.details = details


class UpstreamError(RuntimeError):
    """A dependency this service needs (its database service, or Ollama) is unavailable."""

    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status
