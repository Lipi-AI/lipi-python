"""Pydantic models for Lipi API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# -- Font Match models --


class FontMatch(BaseModel):
    """Font match suggestions for a detected text region."""

    most_likely_commercial: str = ""
    close_commercial_alternatives: List[str] = Field(default_factory=list)
    closest_free_alternatives: List[str] = Field(default_factory=list)


class TextResult(BaseModel):
    """A single text region with its font identification results."""

    text: str = ""
    font_match: FontMatch = Field(default_factory=FontMatch)
    reasoning: str = ""

    @property
    def best_match(self) -> str:
        return self.font_match.most_likely_commercial

    @property
    def commercial_alternatives(self) -> List[str]:
        return self.font_match.close_commercial_alternatives

    @property
    def free_alternatives(self) -> List[str]:
        return self.font_match.closest_free_alternatives


class FontMatchJob(BaseModel):
    """Status of a font match job (pending, running, succeeded, or failed)."""

    job_id: str
    status: str  # pending, running, succeeded, failed
    progress: int = 0
    stage: str = "queued"
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    results: Optional[List[TextResult]] = None
    error: Optional[str] = None

    # Credit info (only on submission response)
    credits_charged: Optional[int] = None
    credits_remaining: Optional[int] = None
    free_credits_remaining: Optional[int] = None
    poll_url: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return self.status in ("succeeded", "failed")

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"


class FontMatchResult(BaseModel):
    """Completed font match result with all text regions identified."""

    job_id: str
    status: str
    results: List[TextResult] = Field(default_factory=list)
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

    @property
    def texts(self) -> List[TextResult]:
        return self.results


# -- URL Scan models --


class FontDetected(BaseModel):
    """A font detected on a scanned webpage."""

    family: str
    weights: List[str] = Field(default_factory=list)
    source: Optional[str] = None


class LicenseResult(BaseModel):
    """License/compliance info for a detected font."""

    font_name: str
    risk_level: str  # low, medium, high, unknown
    license_type: str = ""
    commercial_use: bool = False


class ComplianceSummary(BaseModel):
    """Overall compliance summary for a URL scan."""

    total_fonts: int = 0
    low_risk: int = 0
    medium_risk: int = 0
    high_risk: int = 0
    unknown_risk: int = 0
    overall_score: int = 0
    overall_risk: str = "unknown"


class UrlScanJob(BaseModel):
    """Status of a URL scan job."""

    job_id: str
    status: str
    progress: int = 0
    stage: str = "queued"
    url: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Results (populated when succeeded)
    page_title: Optional[str] = None
    fonts_detected: Optional[List[FontDetected]] = None
    license_results: Optional[List[LicenseResult]] = None
    compliance_summary: Optional[ComplianceSummary] = None
    error: Optional[str] = None

    # Cached results
    cached: bool = False
    scanned_at: Optional[str] = None

    # Credit info (only on submission response)
    credits_charged: Optional[int] = None
    credits_remaining: Optional[int] = None
    free_credits_remaining: Optional[int] = None
    poll_url: Optional[str] = None
    message: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return self.status in ("succeeded", "failed") or self.cached

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded" or self.cached


class UrlScanResult(BaseModel):
    """Completed URL scan result."""

    job_id: str
    status: str
    url: str = ""
    page_title: Optional[str] = None
    fonts_detected: List[FontDetected] = Field(default_factory=list)
    license_results: List[LicenseResult] = Field(default_factory=list)
    compliance_summary: ComplianceSummary = Field(default_factory=ComplianceSummary)
    cached: bool = False
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


# -- Credits & Usage models --


class CreditBalance(BaseModel):
    """Current credit balance for an API key."""

    free_credits_remaining: int = 0
    free_credits_reset_date: Optional[str] = None
    paid_credits_remaining: int = 0
    subscription_status: str = "none"
    total_requests: int = 0
    rate_limit_rpm: int = 60

    @property
    def total_credits(self) -> int:
        return self.free_credits_remaining + self.paid_credits_remaining


class UsageEntry(BaseModel):
    """A single API usage log entry."""

    timestamp: str
    endpoint: str
    credits_charged: int = 0
    credit_type: str = ""
    status_code: int = 0
    job_id: Optional[str] = None


class UsagePagination(BaseModel):
    """Pagination info for usage history."""

    next_cursor: Optional[str] = None
    has_more: bool = False


class UsageSummary(BaseModel):
    """Summary stats for usage history."""

    total_requests_shown: int = 0
    total_credits_shown: int = 0
    period: Optional[dict] = None


class UsageHistory(BaseModel):
    """Paginated usage history."""

    usage: List[UsageEntry] = Field(default_factory=list)
    pagination: UsagePagination = Field(default_factory=UsagePagination)
    summary: UsageSummary = Field(default_factory=UsageSummary)


# -- Health --


class HealthStatus(BaseModel):
    """API health check response."""

    status: str
    version: str = ""
    env: str = ""


# -- Batch --


class BatchStats(BaseModel):
    """Statistics from a batch processing run."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    credits_used: int = 0

    @property
    def processed(self) -> int:
        return self.succeeded + self.failed
