"""Lipi SDK exceptions."""

from __future__ import annotations


class LipiError(Exception):
    """Base exception for all Lipi SDK errors."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(LipiError):
    """API key is missing, invalid, revoked, or suspended (HTTP 401/403)."""


class InsufficientCreditsError(LipiError):
    """No credits remaining (HTTP 402)."""


class RateLimitError(LipiError):
    """Rate limit exceeded (HTTP 429 or 503)."""

    def __init__(self, message: str, retry_after: int = 60, **kwargs):
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


class ValidationError(LipiError):
    """Request validation failed (HTTP 422) — invalid image, URL, or parameters."""


class ImageError(ValidationError):
    """Image is invalid, too large, or unsupported format (HTTP 413/422)."""


class JobFailedError(LipiError):
    """A submitted job failed during processing."""

    def __init__(self, message: str, job_id: str, **kwargs):
        self.job_id = job_id
        super().__init__(message, **kwargs)


class ServerError(LipiError):
    """Unexpected server-side error (HTTP 5xx)."""


class TimeoutError(LipiError):
    """Polling timed out waiting for job to complete."""

    def __init__(self, message: str, job_id: str, **kwargs):
        self.job_id = job_id
        super().__init__(message, **kwargs)
