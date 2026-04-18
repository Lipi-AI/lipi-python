"""Asynchronous Lipi API client (requires httpx: pip install lipi[async])."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, BinaryIO, Callable, Dict, Optional, Union

try:
    import httpx
except ImportError:
    raise ImportError(
        "httpx is required for AsyncClient. Install it with: pip install lipi[async]"
    )

from lipi._polling import DEFAULT_POLL_INTERVAL, DEFAULT_TIMEOUT
from lipi.client import DEFAULT_BASE_URL, _image_to_data_url, _resolve_api_key
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
    ComplianceSummary,
    CreditBalance,
    FontMatchJob,
    FontMatchResult,
    HealthStatus,
    UrlScanJob,
    UrlScanResult,
    UsageHistory,
)


class AsyncClient:
    """Asynchronous client for the Lipi.ai Font Intelligence API.

    Requires httpx: pip install lipi[async]

    Args:
        api_key: API key. Falls back to LIPI_API_KEY env var or ~/.lipi/config.toml.
        base_url: API base URL (default: https://api.lipi.ai).
        timeout: Request timeout in seconds (default: 30).
        poll_interval: Seconds between job polls (default: 2.5).
        poll_timeout: Max seconds to wait for job completion (default: 120).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        poll_timeout: float = DEFAULT_TIMEOUT,
    ):
        self._api_key = _resolve_api_key(api_key)
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "x-api-key": self._api_key,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def close(self):
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        resp = await self._client.request(method, path, **kwargs)
        return self._handle_response(resp)

    def _handle_response(self, resp: httpx.Response) -> Dict[str, Any]:
        try:
            data = resp.json()
        except ValueError:
            data = {}

        if resp.status_code >= 400:
            msg = data.get("message", data.get("error", resp.text))
            code = resp.status_code

            if code == 401:
                raise AuthenticationError(msg, status_code=code)
            elif code == 402:
                raise InsufficientCreditsError(msg, status_code=code)
            elif code == 403:
                raise AuthenticationError(msg, status_code=code)
            elif code in (413, 422):
                raise ImageError(msg, status_code=code)
            elif code == 429:
                retry = data.get("retry_after_seconds", 60)
                raise RateLimitError(msg, retry_after=retry, status_code=code)
            elif code == 503:
                retry = data.get("retry_after_seconds", 60)
                raise RateLimitError(msg, retry_after=retry, status_code=code)
            elif code >= 500:
                raise ServerError(msg, status_code=code)
            else:
                raise LipiError(msg, status_code=code)

        return data

    # -- Health --

    async def health(self) -> HealthStatus:
        """Check API health (no auth required)."""
        resp = await self._client.get("/v3/health")
        return HealthStatus(**resp.json())

    # -- Font Match --

    async def submit_font_match(
        self, image: Union[str, bytes, Path, BinaryIO]
    ) -> FontMatchJob:
        """Submit an image for font identification."""
        data_url = _image_to_data_url(image)
        result = await self._request("POST", "/v3/font-match", json={"image": data_url})
        return FontMatchJob(**result)

    async def get_font_match(self, job_id: str) -> FontMatchJob:
        """Get font match job status."""
        result = await self._request("GET", f"/v3/font-match/{job_id}")
        return FontMatchJob(**result)

    async def font_match(
        self,
        image: Union[str, bytes, Path, BinaryIO],
        poll_interval: Optional[float] = None,
        timeout: Optional[float] = None,
        on_poll: Optional[Callable[[FontMatchJob], None]] = None,
    ) -> FontMatchResult:
        """Identify fonts in an image. Submits and polls until complete."""
        job = await self.submit_font_match(image)
        interval = poll_interval or self._poll_interval
        max_time = timeout or self._poll_timeout
        start = time.monotonic()

        while True:
            current = await self.get_font_match(job.job_id)

            if on_poll:
                on_poll(current)

            if current.is_terminal:
                if current.status == "failed":
                    raise JobFailedError(
                        current.error or "Font match job failed",
                        job_id=current.job_id,
                    )
                return FontMatchResult(
                    job_id=current.job_id,
                    status=current.status,
                    results=current.results or [],
                    created_at=current.created_at,
                    completed_at=current.completed_at,
                )

            if time.monotonic() - start >= max_time:
                raise TimeoutError(
                    f"Job {job.job_id} did not complete within {max_time}s",
                    job_id=job.job_id,
                )

            await asyncio.sleep(interval)

    # -- URL Scan --

    async def submit_url_scan(self, url: str) -> UrlScanJob:
        """Submit a URL for font scanning."""
        result = await self._request("POST", "/v3/url-scan", json={"url": url})
        return UrlScanJob(**result)

    async def get_url_scan(self, job_id: str) -> UrlScanJob:
        """Get URL scan job status."""
        result = await self._request("GET", f"/v3/url-scan/{job_id}")
        return UrlScanJob(**result)

    async def url_scan(
        self,
        url: str,
        poll_interval: Optional[float] = None,
        timeout: Optional[float] = None,
        on_poll: Optional[Callable[[UrlScanJob], None]] = None,
    ) -> UrlScanResult:
        """Scan a URL for fonts and compliance. Submits and polls until complete."""
        job = await self.submit_url_scan(url)

        if job.cached:
            return UrlScanResult(
                job_id=job.job_id,
                status="succeeded",
                url=job.url or url,
                page_title=job.page_title,
                fonts_detected=job.fonts_detected or [],
                license_results=job.license_results or [],
                compliance_summary=job.compliance_summary or ComplianceSummary(),
                cached=True,
                created_at=job.scanned_at,
            )

        interval = poll_interval or self._poll_interval
        max_time = timeout or self._poll_timeout
        start = time.monotonic()

        while True:
            current = await self.get_url_scan(job.job_id)

            if on_poll:
                on_poll(current)

            if current.is_terminal:
                if current.status == "failed":
                    raise JobFailedError(
                        current.error or "URL scan job failed",
                        job_id=current.job_id,
                    )
                return UrlScanResult(
                    job_id=current.job_id,
                    status=current.status,
                    url=current.url or url,
                    page_title=current.page_title,
                    fonts_detected=current.fonts_detected or [],
                    license_results=current.license_results or [],
                    compliance_summary=current.compliance_summary or ComplianceSummary(),
                    created_at=current.created_at,
                    completed_at=current.completed_at,
                )

            if time.monotonic() - start >= max_time:
                raise TimeoutError(
                    f"Job {job.job_id} did not complete within {max_time}s",
                    job_id=job.job_id,
                )

            await asyncio.sleep(interval)

    # -- Credits --

    async def get_credits(self) -> CreditBalance:
        """Get current credit balance."""
        result = await self._request("GET", "/v3/credits")
        return CreditBalance(**result)

    # -- Usage --

    async def get_usage(
        self,
        limit: int = 50,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        cursor: Optional[str] = None,
    ) -> UsageHistory:
        """Get paginated usage history."""
        params: Dict[str, Any] = {"limit": limit}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if cursor:
            params["cursor"] = cursor

        result = await self._request("GET", "/v3/usage", params=params)
        return UsageHistory(**result)
