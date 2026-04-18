"""Lipi — Python SDK for the Lipi.ai Font Intelligence API.

Usage:
    import lipi

    client = lipi.Client(api_key="lpi_...")
    result = client.font_match("screenshot.png")
    print(result.texts[0].best_match)
"""

from lipi.client import Client
from lipi.exceptions import (
    AuthenticationError,
    ImageError,
    InsufficientCreditsError,
    JobFailedError,
    LipiError,
    RateLimitError,
    ServerError,
    TimeoutError,
)
from lipi.models import (
    BatchStats,
    ComplianceSummary,
    CreditBalance,
    FontDetected,
    FontMatch,
    FontMatchJob,
    FontMatchResult,
    HealthStatus,
    LicenseResult,
    TextResult,
    UrlScanJob,
    UrlScanResult,
    UsageHistory,
)

__all__ = [
    # Client
    "Client",
    # Models
    "BatchStats",
    "ComplianceSummary",
    "CreditBalance",
    "FontDetected",
    "FontMatch",
    "FontMatchJob",
    "FontMatchResult",
    "HealthStatus",
    "LicenseResult",
    "TextResult",
    "UrlScanJob",
    "UrlScanResult",
    "UsageHistory",
    # Exceptions
    "AuthenticationError",
    "ImageError",
    "InsufficientCreditsError",
    "JobFailedError",
    "LipiError",
    "RateLimitError",
    "ServerError",
    "TimeoutError",
]


def __getattr__(name: str):
    if name == "AsyncClient":
        from lipi.async_client import AsyncClient

        return AsyncClient
    raise AttributeError(f"module 'lipi' has no attribute {name!r}")
