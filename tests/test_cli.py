"""Tests for the CLI."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from lipi.cli import cli
from lipi.models import CreditBalance, FontMatchResult, TextResult, FontMatch


@pytest.fixture
def runner():
    return CliRunner()


class TestAuthCommands:
    def test_set_key(self, runner, tmp_path):
        config_file = tmp_path / "config.toml"
        with patch("lipi.cli.CONFIG_DIR", tmp_path), patch("lipi.cli.CONFIG_FILE", config_file):
            result = runner.invoke(cli, ["auth", "set-key", "lpi_test123"])
            assert result.exit_code == 0
            assert "saved" in result.output.lower()
            assert config_file.read_text().strip() == 'api_key = "lpi_test123"'

    def test_show_no_key(self, runner, tmp_path):
        config_file = tmp_path / "nonexistent.toml"
        with patch("lipi.cli.CONFIG_FILE", config_file):
            result = runner.invoke(cli, ["auth", "show"])
            assert "no api key" in result.output.lower()


class TestFontMatchCommand:
    def test_font_match_pretty(self, runner, sample_image):
        mock_result = FontMatchResult(
            job_id="j1",
            status="succeeded",
            results=[
                TextResult(
                    text="Hello",
                    font_match=FontMatch(
                        most_likely_commercial="Helvetica",
                        close_commercial_alternatives=["Arial"],
                        closest_free_alternatives=["Inter"],
                    ),
                    reasoning="Sans-serif",
                )
            ],
        )
        mock_client = MagicMock()
        mock_client.font_match.return_value = mock_result

        with patch("lipi.cli._get_client", return_value=mock_client):
            result = runner.invoke(cli, ["font-match", str(sample_image)])
            assert result.exit_code == 0
            assert "Helvetica" in result.output
            assert "Inter" in result.output

    def test_font_match_json(self, runner, sample_image):
        mock_result = FontMatchResult(
            job_id="j1",
            status="succeeded",
            results=[],
        )
        mock_client = MagicMock()
        mock_client.font_match.return_value = mock_result

        with patch("lipi.cli._get_client", return_value=mock_client):
            result = runner.invoke(cli, ["font-match", str(sample_image), "--json-output"])
            assert result.exit_code == 0
            assert '"job_id"' in result.output


class TestCreditsCommand:
    def test_credits_display(self, runner):
        mock_balance = CreditBalance(
            free_credits_remaining=6,
            free_credits_reset_date="2026-05-01",
            paid_credits_remaining=94,
            subscription_status="active",
            total_requests=12,
            rate_limit_rpm=60,
        )
        mock_client = MagicMock()
        mock_client.get_credits.return_value = mock_balance

        with patch("lipi.cli._get_client", return_value=mock_client):
            result = runner.invoke(cli, ["credits"])
            assert result.exit_code == 0
            assert "6" in result.output
            assert "94" in result.output
            assert "active" in result.output


class TestBatchCommand:
    def test_batch_runs(self, runner, tmp_images, tmp_path):
        output = tmp_path / "out.csv"

        mock_client = MagicMock()
        mock_client.get_credits.return_value = CreditBalance(
            free_credits_remaining=10,
            paid_credits_remaining=0,
        )

        from lipi.models import BatchStats

        mock_stats = BatchStats(total=3, succeeded=3, failed=0, skipped=0, credits_used=3)

        with patch("lipi.cli._get_client", return_value=mock_client), \
             patch("lipi.batch.batch_font_match", return_value=mock_stats):
            result = runner.invoke(
                cli, ["batch", str(tmp_images), "--output", str(output)]
            )
            assert result.exit_code == 0
            assert "3 succeeded" in result.output
