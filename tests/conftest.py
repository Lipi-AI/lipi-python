"""Shared test fixtures."""


import pytest
import responses

from lipi.client import Client

BASE_URL = "https://api.lipi.ai"
TEST_API_KEY = "lpi_test_key_12345"


@pytest.fixture
def api_key():
    return TEST_API_KEY


@pytest.fixture
def mock_api():
    """Activate responses mock for all API calls."""
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture
def client(mock_api):
    """Create a Client with a test API key (responses mocked)."""
    return Client(api_key=TEST_API_KEY, base_url=BASE_URL)


@pytest.fixture
def tmp_images(tmp_path):
    """Create a temp directory with fake image files."""
    for name in ["img1.png", "img2.png", "img3.jpg"]:
        (tmp_path / name).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return tmp_path


@pytest.fixture
def sample_image(tmp_path):
    """Create a single fake image file."""
    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return img


# Sample API response payloads

FONT_MATCH_SUBMIT_RESPONSE = {
    "job_id": "test-job-123",
    "status": "pending",
    "credits_charged": 1,
    "credits_remaining": 9,
    "free_credits_remaining": 5,
    "poll_url": "/v3/font-match/test-job-123",
}

FONT_MATCH_RUNNING_RESPONSE = {
    "job_id": "test-job-123",
    "status": "running",
    "progress": 50,
    "stage": "analyzing",
    "created_at": "2026-04-18T10:00:00Z",
    "completed_at": None,
}

FONT_MATCH_SUCCEEDED_RESPONSE = {
    "job_id": "test-job-123",
    "status": "succeeded",
    "progress": 100,
    "stage": "completed",
    "created_at": "2026-04-18T10:00:00Z",
    "completed_at": "2026-04-18T10:00:12Z",
    "results": [
        {
            "text": "Hello World",
            "font_match": {
                "most_likely_commercial": "Helvetica Neue Bold",
                "close_commercial_alternatives": ["Arial Bold", "Univers Bold"],
                "closest_free_alternatives": ["Inter Bold", "Albert Sans Bold"],
            },
            "reasoning": "Sans-serif with uniform stroke width and rounded terminals.",
        }
    ],
}

FONT_MATCH_FAILED_RESPONSE = {
    "job_id": "test-job-123",
    "status": "failed",
    "error": "Processing failed: invalid image format",
    "created_at": "2026-04-18T10:00:00Z",
}

URL_SCAN_SUBMIT_RESPONSE = {
    "job_id": "scan-job-456",
    "status": "pending",
    "url": "https://example.com",
    "credits_charged": 1,
    "credits_remaining": 8,
    "free_credits_remaining": 4,
    "poll_url": "/v3/url-scan/scan-job-456",
}

URL_SCAN_SUCCEEDED_RESPONSE = {
    "job_id": "scan-job-456",
    "status": "succeeded",
    "progress": 100,
    "stage": "completed",
    "url": "https://example.com",
    "page_title": "Example Domain",
    "fonts_detected": [
        {"family": "Inter", "weights": ["400", "700"], "source": "google_fonts"}
    ],
    "license_results": [
        {
            "family": "Inter",
            "found_in_db": True,
            "license_model": "OFL",
            "risk_level": "low",
            "commercial_use": "Allowed",
            "web_use": "Allowed",
            "foundry": "Google",
            "confidence": 95,
            "license_url": "",
            "source_name": "Google Fonts",
            "license_summary": "SIL Open Font License",
            "disclaimer": "Informational only, not legal advice.",
        }
    ],
    "compliance_summary": {
        "total_fonts": 1,
        "low_risk": 1,
        "medium_risk": 0,
        "high_risk": 0,
        "unknown_risk": 0,
        "overall_score": 100,
        "overall_risk": "low",
    },
    "created_at": "2026-04-18T10:00:00Z",
    "completed_at": "2026-04-18T10:00:45Z",
}

CREDITS_RESPONSE = {
    "free_credits_remaining": 6,
    "free_credits_reset_date": "2026-05-01",
    "paid_credits_remaining": 94,
    "subscription_status": "active",
    "total_requests": 12,
    "rate_limit_rpm": 60,
}

USAGE_RESPONSE = {
    "usage": [
        {
            "timestamp": "2026-04-18T10:00:00Z",
            "endpoint": "font-match",
            "credits_charged": 1,
            "credit_type": "free",
            "status_code": 200,
            "job_id": "test-job-123",
        }
    ],
    "pagination": {"next_cursor": None, "has_more": False},
    "summary": {
        "total_requests_shown": 1,
        "total_credits_shown": 1,
        "period": {
            "from": "2026-04-18T10:00:00Z",
            "to": "2026-04-18T10:00:00Z",
        },
    },
}
