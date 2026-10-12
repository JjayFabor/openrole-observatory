class GreenhouseError(Exception):
    """Base class for stable Greenhouse provider failures."""


class GreenhouseValidationError(GreenhouseError):
    """Base class for stable Greenhouse source-validation failures."""


class GreenhouseResponseShapeError(GreenhouseValidationError):
    """Raised when the top-level Greenhouse response cannot be processed."""


class GreenhouseConfigurationError(GreenhouseError):
    """Raised when required Greenhouse source configuration is invalid."""


class GreenhouseRequestError(GreenhouseError):
    """Raised when a Greenhouse request cannot complete successfully."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GreenhouseTimeoutError(GreenhouseRequestError):
    """Raised when Greenhouse keeps timing out after bounded retries."""


class GreenhouseRateLimitError(GreenhouseRequestError):
    """Raised when Greenhouse rate limiting continues after bounded retries."""


class GreenhouseBoardNotFoundError(GreenhouseRequestError):
    """Raised when the configured Greenhouse board does not exist."""
