"""Lipi CLI — font identification and URL scanning from the terminal."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import click

from lipi.client import CONFIG_DIR, CONFIG_FILE

# Lazy client creation — only instantiated when a command needs it
_client = None


def _get_client():
    global _client
    if _client is None:
        from lipi.client import Client

        _client = Client()
    return _client


@click.group()
@click.version_option(package_name="lipi")
def cli():
    """Lipi — AI-powered font identification and compliance scanning."""
    pass


# ── Auth ──────────────────────────────────────────────────────────────


@cli.group()
def auth():
    """Manage API key authentication."""
    pass


@auth.command("set-key")
@click.argument("api_key")
def auth_set_key(api_key: str):
    """Save your API key to ~/.lipi/config.toml."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(f'api_key = "{api_key}"\n')
    click.echo(f"API key saved to {CONFIG_FILE}")


@auth.command("show")
def auth_show():
    """Show the currently configured API key."""
    if CONFIG_FILE.exists():
        text = CONFIG_FILE.read_text().strip()
        click.echo(text)
    else:
        click.echo("No API key configured. Run: lipi auth set-key <your-key>")


# ── Font Match ────────────────────────────────────────────────────────


@cli.command("font-match")
@click.argument("image", type=click.Path(exists=True))
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.option("--output", "-o", type=click.Path(), help="Save results to file")
@click.option("--timeout", type=float, default=120, help="Max wait time in seconds")
def font_match_cmd(image: str, as_json: bool, output: str, timeout: float):
    """Identify fonts in an image."""
    client = _get_client()
    start = time.time()

    with _spinner("Analyzing"):
        result = client.font_match(image, timeout=timeout)

    elapsed = time.time() - start

    if as_json or output:
        data = result.model_dump(mode="json")
        text = json.dumps(data, indent=2)
        if output:
            Path(output).write_text(text)
            click.echo(f"Results saved to {output}")
        else:
            click.echo(text)
        return

    # Pretty output
    click.echo(f"\nAnalyzed {click.style(image, bold=True)} in {elapsed:.1f}s\n")

    if not result.results:
        click.echo("No text regions detected in the image.")
        return

    click.echo(f"Found {len(result.results)} text region(s):\n")

    for tr in result.results:
        click.echo(f'  {click.style(f"\"{tr.text}\"", fg="cyan", bold=True)}')
        click.echo(f"  Best match:  {click.style(tr.best_match, fg='green', bold=True)}")
        if tr.commercial_alternatives:
            click.echo(f"  Commercial:  {', '.join(tr.commercial_alternatives)}")
        if tr.free_alternatives:
            click.echo(f"  Free:        {', '.join(tr.free_alternatives)}")
        click.echo()

    _print_credits(client)


# ── URL Scan ──────────────────────────────────────────────────────────


@cli.command("url-scan")
@click.argument("url")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.option("--output", "-o", type=click.Path(), help="Save results to file")
@click.option("--timeout", type=float, default=120, help="Max wait time in seconds")
def url_scan_cmd(url: str, as_json: bool, output: str, timeout: float):
    """Scan a URL for fonts and license compliance."""
    client = _get_client()
    start = time.time()

    with _spinner("Scanning"):
        result = client.url_scan(url, timeout=timeout)

    elapsed = time.time() - start

    if as_json or output:
        data = result.model_dump(mode="json")
        text = json.dumps(data, indent=2)
        if output:
            Path(output).write_text(text)
            click.echo(f"Results saved to {output}")
        else:
            click.echo(text)
        return

    # Pretty output
    click.echo(f"\nScanned {click.style(url, bold=True)} in {elapsed:.1f}s")
    if result.page_title:
        click.echo(f"Page: {result.page_title}")
    click.echo()

    if not result.fonts_detected:
        click.echo("No fonts detected on the page.")
        return

    risk_colors = {"low": "green", "medium": "yellow", "high": "red", "unknown": "white"}

    summary = result.compliance_summary
    risk_color = risk_colors.get(summary.overall_risk, "white")
    click.echo(
        f"Overall: {click.style(summary.overall_risk.upper(), fg=risk_color, bold=True)}"
        f" (score: {summary.overall_score}/100)"
    )
    click.echo(f"Fonts found: {summary.total_fonts}\n")

    for i, font in enumerate(result.fonts_detected):
        lic = result.license_results[i] if i < len(result.license_results) else None
        risk = lic.risk_level if lic else "unknown"
        color = risk_colors.get(risk, "white")
        click.echo(
            f"  {click.style(font.family, bold=True)}"
            f"  [{', '.join(font.weights)}]"
            f"  {click.style(risk, fg=color)}"
        )
        if lic:
            click.echo(f"    License: {lic.license_type}")

    click.echo()
    _print_credits(client)


# ── Batch ─────────────────────────────────────────────────────────────


@cli.command("batch")
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--output", "-o", default="results.csv", help="Output CSV file")
@click.option("--no-resume", is_flag=True, help="Ignore existing results, re-process all")
@click.option("--retry-failed", is_flag=True, help="Only retry previously failed images")
def batch_cmd(input_dir: str, output: str, no_resume: bool, retry_failed: bool):
    """Batch process a folder of images for font identification."""
    from lipi.batch import batch_font_match

    client = _get_client()

    # Pre-check credits
    try:
        credits = client.get_credits()
        click.echo(
            f"Credits available: {credits.total_credits}"
            f" ({credits.free_credits_remaining} free + {credits.paid_credits_remaining} paid)"
        )
    except Exception:
        pass

    click.echo(f"Input: {input_dir}")
    click.echo(f"Output: {output}\n")

    start = time.time()

    def on_progress(idx, total, filename, status):
        if status == "analyzing":
            click.echo(f"[{idx}/{total}] analyzing {filename}...", nl=False)
        elif status == "done":
            click.echo(click.style(" done", fg="green"))
        elif status == "failed":
            click.echo(click.style(" failed", fg="red"))
        elif status == "no credits":
            click.echo(click.style(" no credits left", fg="red"))

    try:
        stats = batch_font_match(
            client,
            input_dir=input_dir,
            output=output,
            resume=not no_resume,
            retry_failed=retry_failed,
            on_progress=on_progress,
        )
    except KeyboardInterrupt:
        click.echo(click.style("\n\nInterrupted. Progress saved — re-run to resume.", fg="yellow"))
        sys.exit(1)

    elapsed = time.time() - start
    click.echo(
        f"\nBatch complete in {elapsed:.1f}s: "
        f"{stats.succeeded} succeeded, {stats.failed} failed, {stats.skipped} skipped"
    )
    click.echo(f"Results saved to {output}")

    _print_credits(client)


@cli.command("batch-urls")
@click.argument("urls_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", default="scan_results.csv", help="Output CSV file")
@click.option("--no-resume", is_flag=True, help="Ignore existing results, re-process all")
@click.option("--retry-failed", is_flag=True, help="Only retry previously failed URLs")
def batch_urls_cmd(urls_file: str, output: str, no_resume: bool, retry_failed: bool):
    """Batch scan URLs from a text file for font compliance."""
    from lipi.batch import batch_url_scan

    client = _get_client()

    click.echo(f"URLs file: {urls_file}")
    click.echo(f"Output: {output}\n")

    start = time.time()

    def on_progress(idx, total, url, status):
        if status == "scanning":
            short = url[:60] + "..." if len(url) > 60 else url
            click.echo(f"[{idx}/{total}] scanning {short}...", nl=False)
        elif status == "done":
            click.echo(click.style(" done", fg="green"))
        elif status == "failed":
            click.echo(click.style(" failed", fg="red"))

    try:
        stats = batch_url_scan(
            client,
            urls=urls_file,
            output=output,
            resume=not no_resume,
            retry_failed=retry_failed,
            on_progress=on_progress,
        )
    except KeyboardInterrupt:
        click.echo(click.style("\n\nInterrupted. Progress saved — re-run to resume.", fg="yellow"))
        sys.exit(1)

    elapsed = time.time() - start
    click.echo(
        f"\nBatch complete in {elapsed:.1f}s: "
        f"{stats.succeeded} succeeded, {stats.failed} failed, {stats.skipped} skipped"
    )
    click.echo(f"Results saved to {output}")


# ── Credits ───────────────────────────────────────────────────────────


@cli.command("credits")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def credits_cmd(as_json: bool):
    """Check your credit balance."""
    client = _get_client()
    balance = client.get_credits()

    if as_json:
        click.echo(json.dumps(balance.model_dump(mode="json"), indent=2))
        return

    click.echo(f"Free credits:    {balance.free_credits_remaining}")
    if balance.free_credits_reset_date:
        click.echo(f"  Resets:        {balance.free_credits_reset_date}")
    click.echo(f"Paid credits:    {balance.paid_credits_remaining}")
    click.echo(f"Subscription:    {balance.subscription_status}")
    click.echo(f"Total requests:  {balance.total_requests}")
    click.echo(f"Rate limit:      {balance.rate_limit_rpm} RPM")


# ── Usage ─────────────────────────────────────────────────────────────


@cli.command("usage")
@click.option("--limit", type=int, default=20, help="Number of records")
@click.option("--from", "from_date", help="From date (ISO 8601)")
@click.option("--to", "to_date", help="To date (ISO 8601)")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def usage_cmd(limit: int, from_date: str, to_date: str, as_json: bool):
    """View API usage history."""
    client = _get_client()
    history = client.get_usage(limit=limit, from_date=from_date, to_date=to_date)

    if as_json:
        click.echo(json.dumps(history.model_dump(mode="json"), indent=2))
        return

    if not history.usage:
        click.echo("No usage records found.")
        return

    click.echo(f"{'Timestamp':<26} {'Endpoint':<14} {'Credits':<9} {'Type':<8} {'Status'}")
    click.echo("-" * 75)
    for entry in history.usage:
        ts = entry.timestamp[:19] if entry.timestamp else ""
        click.echo(
            f"{ts:<26} {entry.endpoint:<14} {entry.credits_charged:<9} "
            f"{entry.credit_type:<8} {entry.status_code}"
        )

    if history.pagination.has_more:
        click.echo(f"\nMore records available (cursor: {history.pagination.next_cursor})")


# ── Helpers ───────────────────────────────────────────────────────────


def _print_credits(client):
    """Print credit balance after an operation."""
    try:
        balance = client.get_credits()
        total = balance.total_credits
        click.echo(
            f"Credits remaining: {total}"
            f" ({balance.free_credits_remaining} free"
            f" + {balance.paid_credits_remaining} paid)"
        )
    except Exception:
        pass


class _spinner:
    """Simple spinner context manager for CLI feedback."""

    def __init__(self, message: str):
        self.message = message

    def __enter__(self):
        click.echo(f"{self.message}...", nl=False)
        return self

    def __exit__(self, *args):
        click.echo(" done")


if __name__ == "__main__":
    cli()
