"""Tests for batch processing and crash recovery."""

import csv
from unittest.mock import MagicMock

import pytest

from lipi.batch import (
    _discover_images,
    _load_completed,
    _load_failed,
    batch_font_match,
)
from lipi.exceptions import InsufficientCreditsError, JobFailedError
from lipi.models import FontMatch, FontMatchResult, TextResult


def _make_result(job_id="job-1", texts=None):
    """Helper to create a FontMatchResult."""
    if texts is None:
        texts = [
            TextResult(
                text="Hello",
                font_match=FontMatch(
                    most_likely_commercial="Arial",
                    close_commercial_alternatives=["Helvetica"],
                    closest_free_alternatives=["Inter"],
                ),
                reasoning="Sans-serif",
            )
        ]
    return FontMatchResult(
        job_id=job_id,
        status="succeeded",
        results=texts,
        created_at="2026-04-18T10:00:00Z",
        completed_at="2026-04-18T10:00:12Z",
    )


class TestDiscoverImages:
    def test_finds_images(self, tmp_images):
        images = _discover_images(tmp_images)
        names = [p.name for p in images]
        assert "img1.png" in names
        assert "img2.png" in names
        assert "img3.jpg" in names

    def test_ignores_non_images(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "data.csv").write_text("a,b")
        (tmp_path / "photo.png").write_bytes(b"\x89PNG")
        images = _discover_images(tmp_path)
        assert len(images) == 1
        assert images[0].name == "photo.png"

    def test_nonexistent_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            _discover_images("/nonexistent/path")


class TestLoadCompleted:
    def test_reads_completed_filenames(self, tmp_path):
        csv_file = tmp_path / "results.csv"
        csv_file.write_text("filename,status,text\nimg1.png,succeeded,Hello\nimg2.png,failed,\n")
        done = _load_completed(csv_file, "filename")
        assert done == {"img1.png", "img2.png"}

    def test_empty_file(self, tmp_path):
        csv_file = tmp_path / "results.csv"
        csv_file.write_text("")
        done = _load_completed(csv_file, "filename")
        assert done == set()

    def test_nonexistent_file(self, tmp_path):
        done = _load_completed(tmp_path / "nope.csv", "filename")
        assert done == set()


class TestLoadFailed:
    def test_reads_only_failed(self, tmp_path):
        csv_file = tmp_path / "results.csv"
        csv_file.write_text(
            "filename,status,text\nimg1.png,succeeded,Hello\nimg2.png,failed,\n"
        )
        failed = _load_failed(csv_file, "filename")
        assert failed == {"img2.png"}


class TestBatchFontMatch:
    def test_processes_all_images(self, tmp_images, tmp_path):
        output = tmp_path / "out.csv"
        mock_client = MagicMock()
        mock_client.font_match.return_value = _make_result()

        stats = batch_font_match(mock_client, tmp_images, output)

        assert stats.succeeded == 3
        assert stats.failed == 0
        assert stats.credits_used == 3
        assert output.exists()

        # Verify CSV content
        with open(output) as f:
            reader = list(csv.DictReader(f))
            assert len(reader) == 3  # 1 text region per image
            assert reader[0]["best_match"] == "Arial"

    def test_resume_skips_completed(self, tmp_images, tmp_path):
        output = tmp_path / "out.csv"

        # Pre-populate with 2 completed images
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "filename", "status", "text", "best_match",
                    "commercial_alternatives", "free_alternatives",
                    "reasoning", "job_id", "processed_at", "error",
                ],
            )
            writer.writeheader()
            writer.writerow({
                "filename": "img1.png", "status": "succeeded", "text": "X",
                "best_match": "Arial", "commercial_alternatives": "",
                "free_alternatives": "", "reasoning": "", "job_id": "j1",
                "processed_at": "2026-04-18T10:00:00Z", "error": "",
            })
            writer.writerow({
                "filename": "img2.png", "status": "succeeded", "text": "Y",
                "best_match": "Times", "commercial_alternatives": "",
                "free_alternatives": "", "reasoning": "", "job_id": "j2",
                "processed_at": "2026-04-18T10:00:00Z", "error": "",
            })

        mock_client = MagicMock()
        mock_client.font_match.return_value = _make_result()

        stats = batch_font_match(mock_client, tmp_images, output, resume=True)

        assert stats.skipped == 2
        assert stats.succeeded == 1  # only img3.jpg
        assert mock_client.font_match.call_count == 1

    def test_retry_failed_only(self, tmp_images, tmp_path):
        output = tmp_path / "out.csv"

        # Pre-populate: img1 succeeded, img2 failed, img3 succeeded
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "filename", "status", "text", "best_match",
                    "commercial_alternatives", "free_alternatives",
                    "reasoning", "job_id", "processed_at", "error",
                ],
            )
            writer.writeheader()
            for name, status in [
                ("img1.png", "succeeded"), ("img2.png", "failed"), ("img3.jpg", "succeeded")
            ]:
                writer.writerow({
                    "filename": name, "status": status, "text": "",
                    "best_match": "", "commercial_alternatives": "",
                    "free_alternatives": "", "reasoning": "", "job_id": "",
                    "processed_at": "", "error": "some error" if status == "failed" else "",
                })

        mock_client = MagicMock()
        mock_client.font_match.return_value = _make_result()

        stats = batch_font_match(
            mock_client, tmp_images, output, retry_failed=True
        )

        assert stats.succeeded == 1  # only img2.png retried
        assert mock_client.font_match.call_count == 1

    def test_handles_job_failure(self, tmp_images, tmp_path):
        output = tmp_path / "out.csv"
        mock_client = MagicMock()

        # First call succeeds, second fails, third succeeds
        mock_client.font_match.side_effect = [
            _make_result(job_id="j1"),
            JobFailedError("boom", job_id="j2"),
            _make_result(job_id="j3"),
        ]

        stats = batch_font_match(mock_client, tmp_images, output)

        assert stats.succeeded == 2
        assert stats.failed == 1

        # CSV should have all 3 entries
        with open(output) as f:
            rows = list(csv.DictReader(f))
            statuses = [r["status"] for r in rows]
            assert statuses.count("succeeded") == 2
            assert statuses.count("failed") == 1

    def test_insufficient_credits_stops_batch(self, tmp_images, tmp_path):
        output = tmp_path / "out.csv"
        mock_client = MagicMock()

        mock_client.font_match.side_effect = [
            _make_result(),
            InsufficientCreditsError("No credits"),
        ]

        with pytest.raises(InsufficientCreditsError):
            batch_font_match(mock_client, tmp_images, output)

    def test_no_resume_reprocesses_all(self, tmp_images, tmp_path):
        output = tmp_path / "out.csv"

        # Pre-populate with all 3 completed
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "filename", "status", "text", "best_match",
                    "commercial_alternatives", "free_alternatives",
                    "reasoning", "job_id", "processed_at", "error",
                ],
            )
            writer.writeheader()
            for name in ["img1.png", "img2.png", "img3.jpg"]:
                writer.writerow({
                    "filename": name, "status": "succeeded", "text": "",
                    "best_match": "", "commercial_alternatives": "",
                    "free_alternatives": "", "reasoning": "", "job_id": "",
                    "processed_at": "", "error": "",
                })

        mock_client = MagicMock()
        mock_client.font_match.return_value = _make_result()

        stats = batch_font_match(mock_client, tmp_images, output, resume=False)

        # Should process all 3 again
        assert stats.succeeded == 3
        assert mock_client.font_match.call_count == 3

    def test_progress_callback(self, tmp_images, tmp_path):
        output = tmp_path / "out.csv"
        mock_client = MagicMock()
        mock_client.font_match.return_value = _make_result()

        progress_calls = []

        def on_progress(idx, total, filename, status):
            progress_calls.append((idx, total, filename, status))

        batch_font_match(
            mock_client, tmp_images, output, on_progress=on_progress
        )

        # Should have 2 calls per image (analyzing + done)
        assert len(progress_calls) == 6
        assert progress_calls[0][3] == "analyzing"
        assert progress_calls[1][3] == "done"
