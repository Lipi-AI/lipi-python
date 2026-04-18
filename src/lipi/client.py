"""Synchronous Lipi API client."""

from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path
from typing import Any, BinaryIO, Callable, Dict, List, Optional, Union

import requests

from lipi._polling import DEFAULT_POLL_INTERVAL, DEFAULT_TIMEOUT, poll_until_done
from lipi.exceptions import (
    AuthenticationError,
    ImageError,
    InsufficientCreditsError,
    JobFailedError,
    LipiError,
    RateLimitError,
    ServerError,
)
from lipi.models import (
    CreditBalance,
    FontMatchJob,
    FontMatchResult,
    HealthStatus,
    UrlScanJob,
    UrlScanResult,
    UsageHistory,
)

DEFAULT_BASE_URL = "https://api.lipi.ai"
CONFIG_DIR = Path.home() / ".lipi"
CONFIG_FILE = CONFIG_DIR / "config.toml"


def _load_api_key_from_config() -> Optional[str]:
    """Load API key from ~/.lipi/config.toml."""
    if not CONFIG_FILE.exists():
        return None
    try:
        text = CONFIG_FILE.read_text()
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("api_key"):
                # Parse: api_key = "lpi_..."
                _, _, value = line.partition("=")
                return value.strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def _resolve_api_key(api_key: Optional[str]) -> str:
    """Resolve API key from explicit param, env var, or config file."""
    if api_key:
        return api_key

    env_key = os.environ.get("LIPI_API_KEY")
    if env_key:
        return env_key

    config_key = _load_api_key_from_config()
    if config_key:
        return config_key

    raise AuthenticationError(
        "No API key provided. Set it via:\n"
        "  1. Client(api_key='lpi_...')\n"
        "  2. LIPI_API_KEY environment variable\n"
        "  3. lipi auth set-key lpi_..."
    )


def _image_to_data_url(image: Union[str, bytes, Path, BinaryIO]) -> str:
    """Convert various image inputs to a base64 data URL."""
    if isinstance(image, bytes):
        encoded = base64.b64encode(image).decode()
        return f"data:image/png;base64,{encoded}"

    if isinstance(image, (str, Path)):
        path = Path(image)
        if path.exists():
            mime, _ = mimetypes.guess_type(str(path))
            if not mime:
                mime = "image/png"
            data = path.read_bytes()
            encoded = base64.b64encode(data).decode()
            return f"data:{mime};base64,{encoded}"
        # If it's a string that looks like a data URL, pass through
        image_str = str(image)
        if image_str.startswith("data:image/"):
            return image_str
        raise ImageError(f"File not found: {image}")

    # File-like object
    if hasattr(image, "read"):
        data = image.read()
        if isinstance(data, str):
            data = data.encode()
        encoded = base64.b64encode(data).decode()
        return f"data:image/png;base64,{encoded}"

    raise ImageError(f"Unsupported image type: {type(image)}")


class Client:
    """Synchronous client for the Lipi.ai Font Intelligence API.

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
        self._session = requests.Session()
        self._session.headers.update({
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """Make an HTTP request and handle errors."""
        url = f"{self._base_url}{path}"
        kwargs.setdefault("timeout", self._timeout)

        resp = self._session.request(method, url, **kwargs)
        return self._handle_response(resp)

    def _handle_response(self, resp: requests.Response) -> Dict[str, Any]:
        """Parse response and raise typed exceptions on errors."""
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
                error_type = data.get("error", "")
                if error_type in ("key_revoked", "key_suspended"):
                    raise AuthenticationError(msg, status_code=code)
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

    def health(self) -> HealthStatus:
        """Check API health (no auth required)."""
        resp = self._session.get(
            f"{self._base_url}/v3/health", timeout=self._timeout
        )
        return HealthStatus(**resp.json())

    # -- Font Match --

    def submit_font_match(
        self, image: Union[str, bytes, Path, BinaryIO]
    ) -> FontMatchJob:
        """Submit an image for font identification. Returns a job to poll.

        Args:
            image: File path, bytes, file-like object, or base64 data URL.

        Returns:
            FontMatchJob with job_id and initial status.
        """
        data_url = _image_to_data_url(image)
        result = self._request("POST", "/v3/font-match", json={"image": data_url})
        return FontMatchJob(**result)

    def get_font_match(self, job_id: str) -> FontMatchJob:
        """Get the current status of a font match job.

        Args:
            job_id: The job ID returned from submit_font_match.
        """
        result = self._request("GET", f"/v3/font-match/{job_id}")
        return FontMatchJob(**result)

    def font_match(
        self,
        image: Union[str, bytes, Path, BinaryIO],
        poll_interval: Optional[float] = None,
        timeout: Optional[float] = None,
        on_poll: Optional[Callable[[FontMatchJob], None]] = None,
    ) -> FontMatchResult:
        """Identify fonts in an image. Submits and polls until complete.

        Args:
            image: File path, bytes, file-like object, or base64 data URL.
            poll_interval: Override default poll interval (seconds).
            timeout: Override default poll timeout (seconds).
            on_poll: Callback invoked after each poll.

        Returns:
            FontMatchResult with identified fonts.

        Raises:
            JobFailedError: If the job fails.
            TimeoutError: If polling times out.
        """
        job = self.submit_font_match(image)

        final = poll_until_done(
            fetch_fn=lambda: self.get_font_match(job.job_id),
            is_terminal=lambda j: j.is_terminal,
            job_id=job.job_id,
            poll_interval=poll_interval or self._poll_interval,
            timeout=timeout or self._poll_timeout,
            on_poll=on_poll,
        )

        if final.status == "failed":
            raise JobFailedError(
                final.error or "Font match job failed",
                job_id=final.job_id,
            )

        return FontMatchResult(
            job_id=final.job_id,
            status=final.status,
            results=final.results or [],
            created_at=final.created_at,
            completed_at=final.completed_at,
        )

    # -- URL Scan --

    def submit_url_scan(self, url: str) -> UrlScanJob:
        """Submit a URL for font scanning. Returns a job to poll.

        Args:
            url: The URL to scan for fonts and license compliance.

        Returns:
            UrlScanJob with job_id and initial status (or cached results).
        """
        result = self._request("POST", "/v3/url-scan", json={"url": url})
        return UrlScanJob(**result)

    def get_url_scan(self, job_id: str) -> UrlScanJob:
        """Get the current status of a URL scan job.

        Args:
            job_id: The job ID returned from submit_url_scan.
        """
        result = self._request("GET", f"/v3/url-scan/{job_id}")
        return UrlScanJob(**result)

    def url_scan(
        self,
        url: str,
        poll_interval: Optional[float] = None,
        timeout: Optional[float] = None,
        on_poll: Optional[Callable[[UrlScanJob], None]] = None,
    ) -> UrlScanResult:
        """Scan a URL for fonts and license compliance. Submits and polls until complete.

        Args:
            url: The URL to scan.
            poll_interval: Override default poll interval (seconds).
            timeout: Override default poll timeout (seconds).
            on_poll: Callback invoked after each poll.

        Returns:
            UrlScanResult with detected fonts and compliance info.

        Raises:
            JobFailedError: If the scan fails.
            TimeoutError: If polling times out.
        """
        job = self.submit_url_scan(url)

        # Cached results come back immediately
        if job.cached:
            return UrlScanResult(
                job_id=job.job_id,
                status="succeeded",
                url=job.url or url,
                page_title=job.page_title,
                fonts_detected=job.fonts_detected or [],
                license_results=job.license_results or [],
                compliance_summary=job.compliance_summary
                or __import__("lipi.models", fromlist=["ComplianceSummary"]).ComplianceSummary(),
                cached=True,
                created_at=job.scanned_at,
            )

        final = poll_until_done(
            fetch_fn=lambda: self.get_url_scan(job.job_id),
            is_terminal=lambda j: j.is_terminal,
            job_id=job.job_id,
            poll_interval=poll_interval or self._poll_interval,
            timeout=timeout or self._poll_timeout,
            on_poll=on_poll,
        )

        if final.status == "failed":
            raise JobFailedError(
                final.error or "URL scan job failed",
                job_id=final.job_id,
            )

        return UrlScanResult(
            job_id=final.job_id,
            status=final.status,
            url=final.url or url,
            page_title=final.page_title,
            fonts_detected=final.fonts_detected or [],
            license_results=final.license_results or [],
            compliance_summary=final.compliance_summary or ComplianceSummary(),
            created_at=final.created_at,
            completed_at=final.completed_at,
        )

    # -- Credits --

    def get_credits(self) -> CreditBalance:
        """Get current credit balance."""
        result = self._request("GET", "/v3/credits")
        return CreditBalance(**result)

    # -- Usage --

    def get_usage(
        self,
        limit: int = 50,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        cursor: Optional[str] = None,
    ) -> UsageHistory:
        """Get paginated usage history.

        Args:
            limit: Number of records (max 100).
            from_date: Filter from date (ISO 8601, e.g. '2026-04-01').
            to_date: Filter to date (ISO 8601).
            cursor: Pagination cursor from previous response.
        """
        params: Dict[str, Any] = {"limit": limit}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if cursor:
            params["cursor"] = cursor

        result = self._request("GET", "/v3/usage", params=params)
        return UsageHistory(**result)
