"""Tests for the synchronous Lipi client."""

import json
import os
from unittest.mock import patch

import pytest
import responses

from lipi.client import Client, _image_to_data_url, _resolve_api_key
from lipi.exceptions import (
    AuthenticationError,
    ImageError,
    InsufficientCreditsError,
    JobFailedError,
    RateLimitError,
    ServerError,
)
from tests.conftest import (
    BASE_URL,
    CREDITS_RESPONSE,
    FONT_MATCH_FAILED_RESPONSE,
    FONT_MATCH_SUBMIT_RESPONSE,
    FONT_MATCH_SUCCEEDED_RESPONSE,
    TEST_API_KEY,
    USAGE_RESPONSE,
    URL_SCAN_SUBMIT_RESPONSE,
    URL_SCAN_SUCCEEDED_RESPONSE,
)


class TestApiKeyResolution:
    def test_explicit_key(self):
        assert _resolve_api_key("lpi_abc") == "lpi_abc"

    def test_env_var(self):
        with patch.dict(os.environ, {"LIPI_API_KEY": "lpi_env"}):
            assert _resolve_api_key(None) == "lpi_env"

    def test_config_file(self, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text('api_key = "lpi_file"\n')
        with patch.dict(os.environ, {}, clear=True), \
             patch("lipi.client.CONFIG_FILE", config):
            assert _resolve_api_key(None) == "lpi_file"

    def test_no_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("lipi.client._load_api_key_from_config", return_value=None):
                with pytest.raises(AuthenticationError):
                    _resolve_api_key(None)


class TestImageToDataUrl:
    def test_from_bytes(self):
        result = _image_to_data_url(b"\x89PNG")
        assert result.startswith("data:image/png;base64,")

    def test_from_file_path(self, sample_image):
        result = _image_to_data_url(str(sample_image))
        assert result.startswith("data:image/png;base64,")

    def test_from_path_object(self, sample_image):
        result = _image_to_data_url(sample_image)
        assert result.startswith("data:image/png;base64,")

    def test_passthrough_data_url(self):
        url = "data:image/png;base64,abc123"
        assert _image_to_data_url(url) == url

    def test_missing_file_raises(self):
        with pytest.raises(ImageError):
            _image_to_data_url("/nonexistent/file.png")


class TestClientHealth:
    @responses.activate
    def test_health_check(self):
        responses.add(
            responses.GET,
            f"{BASE_URL}/v3/health",
            json={"status": "healthy", "version": "v3", "env": "prod"},
        )
        client = Client(api_key=TEST_API_KEY, base_url=BASE_URL)
        result = client.health()
        assert result.status == "healthy"
        assert result.version == "v3"


class TestFontMatch:
    @responses.activate
    def test_submit_font_match(self, sample_image):
        responses.add(
            responses.POST,
            f"{BASE_URL}/v3/font-match",
            json=FONT_MATCH_SUBMIT_RESPONSE,
            status=201,
        )
        client = Client(api_key=TEST_API_KEY, base_url=BASE_URL)
        job = client.submit_font_match(sample_image)
        assert job.job_id == "test-job-123"
        assert job.status == "pending"
        assert job.credits_charged == 1

    @responses.activate
    def test_font_match_full_flow(self, sample_image):
        # Submit
        responses.add(
            responses.POST,
            f"{BASE_URL}/v3/font-match",
            json=FONT_MATCH_SUBMIT_RESPONSE,
            status=201,
        )
        # Poll → succeeded immediately
        responses.add(
            responses.GET,
            f"{BASE_URL}/v3/font-match/test-job-123",
            json=FONT_MATCH_SUCCEEDED_RESPONSE,
        )
        client = Client(api_key=TEST_API_KEY, base_url=BASE_URL)
        result = client.font_match(sample_image)

        assert result.status == "succeeded"
        assert len(result.results) == 1
        assert result.results[0].best_match == "Helvetica Neue Bold"
        assert "Inter Bold" in result.results[0].free_alternatives

    @responses.activate
    def test_font_match_failed_raises(self, sample_image):
        responses.add(
            responses.POST,
            f"{BASE_URL}/v3/font-match",
            json=FONT_MATCH_SUBMIT_RESPONSE,
            status=201,
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/v3/font-match/test-job-123",
            json=FONT_MATCH_FAILED_RESPONSE,
        )
        client = Client(api_key=TEST_API_KEY, base_url=BASE_URL)
        with pytest.raises(JobFailedError) as exc_info:
            client.font_match(sample_image)
        assert exc_info.value.job_id == "test-job-123"


class TestUrlScan:
    @responses.activate
    def test_url_scan_full_flow(self):
        responses.add(
            responses.POST,
            f"{BASE_URL}/v3/url-scan",
            json=URL_SCAN_SUBMIT_RESPONSE,
            status=201,
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/v3/url-scan/scan-job-456",
            json=URL_SCAN_SUCCEEDED_RESPONSE,
        )
        client = Client(api_key=TEST_API_KEY, base_url=BASE_URL)
        result = client.url_scan("https://example.com")

        assert result.status == "succeeded"
        assert result.page_title == "Example Domain"
        assert len(result.fonts_detected) == 1
        assert result.fonts_detected[0].family == "Inter"
        assert result.compliance_summary.overall_risk == "low"


class TestCredits:
    @responses.activate
    def test_get_credits(self):
        responses.add(
            responses.GET,
            f"{BASE_URL}/v3/credits",
            json=CREDITS_RESPONSE,
        )
        client = Client(api_key=TEST_API_KEY, base_url=BASE_URL)
        balance = client.get_credits()

        assert balance.free_credits_remaining == 6
        assert balance.paid_credits_remaining == 94
        assert balance.total_credits == 100
        assert balance.subscription_status == "active"


class TestUsage:
    @responses.activate
    def test_get_usage(self):
        responses.add(
            responses.GET,
            f"{BASE_URL}/v3/usage",
            json=USAGE_RESPONSE,
        )
        client = Client(api_key=TEST_API_KEY, base_url=BASE_URL)
        history = client.get_usage(limit=10)

        assert len(history.usage) == 1
        assert history.usage[0].endpoint == "font-match"
        assert not history.pagination.has_more


class TestErrorHandling:
    @responses.activate
    def test_401_raises_auth_error(self):
        responses.add(
            responses.GET,
            f"{BASE_URL}/v3/credits",
            json={"error": "invalid_api_key", "message": "Bad key"},
            status=401,
        )
        client = Client(api_key=TEST_API_KEY, base_url=BASE_URL)
        with pytest.raises(AuthenticationError):
            client.get_credits()

    @responses.activate
    def test_402_raises_credits_error(self, sample_image):
        responses.add(
            responses.POST,
            f"{BASE_URL}/v3/font-match",
            json={"error": "insufficient_credits", "message": "No credits"},
            status=402,
        )
        client = Client(api_key=TEST_API_KEY, base_url=BASE_URL)
        with pytest.raises(InsufficientCreditsError):
            client.submit_font_match(sample_image)

    @responses.activate
    def test_429_raises_rate_limit(self, sample_image):
        responses.add(
            responses.POST,
            f"{BASE_URL}/v3/font-match",
            json={
                "error": "rate_limited",
                "message": "Too fast",
                "retry_after_seconds": 30,
            },
            status=429,
        )
        client = Client(api_key=TEST_API_KEY, base_url=BASE_URL)
        with pytest.raises(RateLimitError) as exc_info:
            client.submit_font_match(sample_image)
        assert exc_info.value.retry_after == 30

    @responses.activate
    def test_500_raises_server_error(self):
        responses.add(
            responses.GET,
            f"{BASE_URL}/v3/credits",
            json={"error": "internal_error"},
            status=500,
        )
        client = Client(api_key=TEST_API_KEY, base_url=BASE_URL)
        with pytest.raises(ServerError):
            client.get_credits()
