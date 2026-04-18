"""Batch processing with crash recovery for font-match and url-scan jobs."""

from __future__ import annotations

import csv
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Set, Union

from lipi.exceptions import InsufficientCreditsError, LipiError, RateLimitError
from lipi.models import BatchStats

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

FONT_MATCH_FIELDS = [
    "filename",
    "status",
    "text",
    "best_match",
    "commercial_alternatives",
    "free_alternatives",
    "reasoning",
    "job_id",
    "processed_at",
    "error",
]

URL_SCAN_FIELDS = [
    "url",
    "status",
    "page_title",
    "font_family",
    "weights",
    "risk_level",
    "license_type",
    "commercial_use",
    "overall_risk",
    "overall_score",
    "job_id",
    "processed_at",
    "error",
]


def _discover_images(input_dir: Union[str, Path]) -> List[Path]:
    """Find all image files in a directory, sorted by name."""
    d = Path(input_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"Directory not found: {input_dir}")

    images = sorted(
        p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    return images


def _load_completed(output_path: Path, key_field: str) -> Set[str]:
    """Read already-processed entries from an existing CSV."""
    done: Set[str] = set()
    if not output_path.exists():
        return done
    try:
        with open(output_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                val = row.get(key_field, "").strip()
                if val:
                    done.add(val)
    except Exception:
        pass
    return done


def _load_failed(output_path: Path, key_field: str) -> Set[str]:
    """Read entries that failed from an existing CSV."""
    failed: Set[str] = set()
    if not output_path.exists():
        return failed
    try:
        with open(output_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status") == "failed":
                    val = row.get(key_field, "").strip()
                    if val:
                        failed.add(val)
    except Exception:
        pass
    return failed


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def batch_font_match(
    client,
    input_dir: Union[str, Path],
    output: Union[str, Path] = "results.csv",
    resume: bool = True,
    retry_failed: bool = False,
    on_progress: Optional[Callable[[int, int, str, Optional[str]], None]] = None,
    on_result: Optional[Callable[[str, object], None]] = None,
) -> BatchStats:
    """Process all images in a folder and save font match results to CSV.

    Args:
        client: A lipi.Client instance.
        input_dir: Directory containing images.
        output: Output CSV file path.
        resume: If True, skip already-processed images (default True).
        retry_failed: If True, re-process only images that previously failed.
        on_progress: Callback(current_index, total, filename, status_msg).
        on_result: Callback(filename, result_or_error).

    Returns:
        BatchStats with counts of succeeded/failed/skipped.
    """
    images = _discover_images(input_dir)
    output_path = Path(output)
    stats = BatchStats(total=len(images))

    # Determine which images to process
    if retry_failed:
        failed_set = _load_failed(output_path, "filename")
        remaining = [img for img in images if img.name in failed_set]
        stats.skipped = len(images) - len(remaining)
    elif resume:
        done_set = _load_completed(output_path, "filename")
        remaining = [img for img in images if img.name not in done_set]
        stats.skipped = len(done_set)
    else:
        remaining = images

    if not remaining:
        return stats

    # Determine if we need to write the header
    write_header = not output_path.exists() or output_path.stat().st_size == 0

    with open(output_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FONT_MATCH_FIELDS)
        if write_header:
            writer.writeheader()
            f.flush()

        for idx, img_path in enumerate(remaining):
            if on_progress:
                on_progress(idx + 1, len(remaining), img_path.name, "analyzing")

            try:
                result = _font_match_with_retry(client, img_path)
                now = _now_iso()

                if result.results:
                    for text_result in result.results:
                        writer.writerow({
                            "filename": img_path.name,
                            "status": "succeeded",
                            "text": text_result.text,
                            "best_match": text_result.best_match,
                            "commercial_alternatives": ", ".join(
                                text_result.commercial_alternatives
                            ),
                            "free_alternatives": ", ".join(
                                text_result.free_alternatives
                            ),
                            "reasoning": text_result.reasoning,
                            "job_id": result.job_id,
                            "processed_at": now,
                            "error": "",
                        })
                else:
                    # Succeeded but no text regions found
                    writer.writerow({
                        "filename": img_path.name,
                        "status": "succeeded",
                        "text": "",
                        "best_match": "",
                        "commercial_alternatives": "",
                        "free_alternatives": "",
                        "reasoning": "No text regions detected",
                        "job_id": result.job_id,
                        "processed_at": now,
                        "error": "",
                    })

                f.flush()
                stats.succeeded += 1
                stats.credits_used += 1

                if on_progress:
                    on_progress(idx + 1, len(remaining), img_path.name, "done")
                if on_result:
                    on_result(img_path.name, result)

            except InsufficientCreditsError as e:
                # Write the failure and stop — no point continuing
                writer.writerow({
                    "filename": img_path.name,
                    "status": "failed",
                    "text": "",
                    "best_match": "",
                    "commercial_alternatives": "",
                    "free_alternatives": "",
                    "reasoning": "",
                    "job_id": "",
                    "processed_at": _now_iso(),
                    "error": str(e),
                })
                f.flush()
                stats.failed += 1

                if on_progress:
                    on_progress(idx + 1, len(remaining), img_path.name, "no credits")
                raise

            except LipiError as e:
                writer.writerow({
                    "filename": img_path.name,
                    "status": "failed",
                    "text": "",
                    "best_match": "",
                    "commercial_alternatives": "",
                    "free_alternatives": "",
                    "reasoning": "",
                    "job_id": getattr(e, "job_id", ""),
                    "processed_at": _now_iso(),
                    "error": str(e),
                })
                f.flush()
                stats.failed += 1

                if on_progress:
                    on_progress(idx + 1, len(remaining), img_path.name, "failed")
                if on_result:
                    on_result(img_path.name, e)

    return stats


def _font_match_with_retry(client, image_path: Path, max_retries: int = 2):
    """Submit font match with automatic retry on rate limits."""
    for attempt in range(max_retries + 1):
        try:
            return client.font_match(image_path)
        except RateLimitError as e:
            if attempt >= max_retries:
                raise
            wait = e.retry_after if e.retry_after else 30
            time.sleep(wait)


def batch_url_scan(
    client,
    urls: Union[str, Path, List[str]],
    output: Union[str, Path] = "scan_results.csv",
    resume: bool = True,
    retry_failed: bool = False,
    on_progress: Optional[Callable[[int, int, str, Optional[str]], None]] = None,
    on_result: Optional[Callable[[str, object], None]] = None,
) -> BatchStats:
    """Scan multiple URLs and save font/license results to CSV.

    Args:
        client: A lipi.Client instance.
        urls: List of URLs, or path to a text file with one URL per line.
        output: Output CSV file path.
        resume: If True, skip already-processed URLs (default True).
        retry_failed: If True, re-process only URLs that previously failed.
        on_progress: Callback(current_index, total, url, status_msg).
        on_result: Callback(url, result_or_error).

    Returns:
        BatchStats with counts of succeeded/failed/skipped.
    """
    # Load URLs
    if isinstance(urls, (str, Path)):
        urls_path = Path(urls)
        if urls_path.is_file():
            url_list = [
                line.strip()
                for line in urls_path.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        else:
            raise FileNotFoundError(f"URL file not found: {urls}")
    else:
        url_list = list(urls)

    output_path = Path(output)
    stats = BatchStats(total=len(url_list))

    # Determine which URLs to process
    if retry_failed:
        failed_set = _load_failed(output_path, "url")
        remaining = [u for u in url_list if u in failed_set]
        stats.skipped = len(url_list) - len(remaining)
    elif resume:
        done_set = _load_completed(output_path, "url")
        remaining = [u for u in url_list if u not in done_set]
        stats.skipped = len(done_set)
    else:
        remaining = url_list

    if not remaining:
        return stats

    write_header = not output_path.exists() or output_path.stat().st_size == 0

    with open(output_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=URL_SCAN_FIELDS)
        if write_header:
            writer.writeheader()
            f.flush()

        for idx, url in enumerate(remaining):
            if on_progress:
                on_progress(idx + 1, len(remaining), url, "scanning")

            try:
                result = _url_scan_with_retry(client, url)
                now = _now_iso()

                if result.fonts_detected:
                    for i, font in enumerate(result.fonts_detected):
                        license_info = (
                            result.license_results[i]
                            if i < len(result.license_results)
                            else None
                        )
                        writer.writerow({
                            "url": url,
                            "status": "succeeded",
                            "page_title": result.page_title or "",
                            "font_family": font.family,
                            "weights": ", ".join(font.weights),
                            "risk_level": license_info.risk_level if license_info else "",
                            "license_type": license_info.license_type if license_info else "",
                            "commercial_use": (
                                str(license_info.commercial_use) if license_info else ""
                            ),
                            "overall_risk": result.compliance_summary.overall_risk,
                            "overall_score": result.compliance_summary.overall_score,
                            "job_id": result.job_id,
                            "processed_at": now,
                            "error": "",
                        })
                else:
                    writer.writerow({
                        "url": url,
                        "status": "succeeded",
                        "page_title": result.page_title or "",
                        "font_family": "",
                        "weights": "",
                        "risk_level": "",
                        "license_type": "",
                        "commercial_use": "",
                        "overall_risk": result.compliance_summary.overall_risk,
                        "overall_score": result.compliance_summary.overall_score,
                        "job_id": result.job_id,
                        "processed_at": now,
                        "error": "",
                    })

                f.flush()
                stats.succeeded += 1
                stats.credits_used += 1

                if on_progress:
                    on_progress(idx + 1, len(remaining), url, "done")
                if on_result:
                    on_result(url, result)

            except InsufficientCreditsError as e:
                writer.writerow({
                    "url": url,
                    "status": "failed",
                    "page_title": "",
                    "font_family": "",
                    "weights": "",
                    "risk_level": "",
                    "license_type": "",
                    "commercial_use": "",
                    "overall_risk": "",
                    "overall_score": "",
                    "job_id": "",
                    "processed_at": _now_iso(),
                    "error": str(e),
                })
                f.flush()
                stats.failed += 1
                raise

            except LipiError as e:
                writer.writerow({
                    "url": url,
                    "status": "failed",
                    "page_title": "",
                    "font_family": "",
                    "weights": "",
                    "risk_level": "",
                    "license_type": "",
                    "commercial_use": "",
                    "overall_risk": "",
                    "overall_score": "",
                    "job_id": getattr(e, "job_id", ""),
                    "processed_at": _now_iso(),
                    "error": str(e),
                })
                f.flush()
                stats.failed += 1

                if on_progress:
                    on_progress(idx + 1, len(remaining), url, "failed")
                if on_result:
                    on_result(url, e)

    return stats


def _url_scan_with_retry(client, url: str, max_retries: int = 2):
    """Submit URL scan with automatic retry on rate limits."""
    for attempt in range(max_retries + 1):
        try:
            return client.url_scan(url)
        except RateLimitError as e:
            if attempt >= max_retries:
                raise
            wait = e.retry_after if e.retry_after else 30
            time.sleep(wait)
