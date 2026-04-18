# lipi

Python SDK for the [Lipi.ai](https://lipi.ai) Font Intelligence API.

Identify fonts from images and scan websites for font licensing compliance.

## Install

```bash
pip install lipi
```

For async support:
```bash
pip install lipi[async]
```

## Quick Start

```python
import lipi

client = lipi.Client(api_key="lpi_...")

# Identify fonts in an image
result = client.font_match("screenshot.png")
for text in result.texts:
    print(f'"{text.text}" → {text.best_match}')
    print(f"  Free alternatives: {', '.join(text.free_alternatives)}")

# Scan a URL for font compliance
scan = client.url_scan("https://stripe.com")
print(f"Risk: {scan.compliance_summary.overall_risk}")
for font in scan.fonts_detected:
    print(f"  {font.family}")
```

## Authentication

API key is resolved in this order:

1. `Client(api_key="lpi_...")`
2. `LIPI_API_KEY` environment variable
3. `~/.lipi/config.toml` (set via CLI)

```bash
# Save your key via CLI
lipi auth set-key lpi_your_key_here
```

## API Reference

### `Client(api_key=None, base_url="https://api.lipi.ai", timeout=30)`

#### Font Identification

```python
# High-level: submit + poll until done
result = client.font_match("image.png")

# Low-level: manual polling
job = client.submit_font_match("image.png")
status = client.get_font_match(job.job_id)
```

**Input formats:** file path (`str`/`Path`), `bytes`, file-like object, or base64 data URL.

#### URL Scanning

```python
# High-level: submit + poll until done
scan = client.url_scan("https://example.com")

# Low-level: manual polling
job = client.submit_url_scan("https://example.com")
status = client.get_url_scan(job.job_id)
```

#### Credits & Usage

```python
balance = client.get_credits()
print(f"Free: {balance.free_credits_remaining}")
print(f"Paid: {balance.paid_credits_remaining}")

history = client.get_usage(limit=20, from_date="2026-04-01")
for entry in history.usage:
    print(f"{entry.timestamp} {entry.endpoint} {entry.credits_charged} credits")
```

### Batch Processing

Process an entire folder of images with crash recovery:

```python
from lipi import Client
from lipi.batch import batch_font_match

client = Client()

# Process all images → CSV (resumes automatically if interrupted)
stats = batch_font_match(
    client,
    input_dir="./screenshots",
    output="results.csv",
)
print(f"{stats.succeeded}/{stats.total} succeeded")
```

Crash recovery works by reading the output CSV on startup and skipping already-processed files. Results are flushed after each image, so at most one image of work is lost on crash.

```python
# Retry only failed images
stats = batch_font_match(client, "./screenshots", "results.csv", retry_failed=True)

# Force re-process everything
stats = batch_font_match(client, "./screenshots", "results.csv", resume=False)
```

**CSV output** (one row per text region detected):
```
filename,status,text,best_match,commercial_alternatives,free_alternatives,reasoning,job_id,processed_at,error
logo.png,succeeded,ACME,Futura Bold,"Avant Garde, Kabel","Jost, Nunito Sans","Geometric sans-serif...",abc123,2026-04-18T10:00:00Z,
```

Batch URL scanning:
```python
from lipi.batch import batch_url_scan

stats = batch_url_scan(client, urls="urls.txt", output="scan_results.csv")
```

### Async Client

```python
import asyncio
from lipi import AsyncClient

async def main():
    async with AsyncClient() as client:
        result = await client.font_match("screenshot.png")
        print(result.texts[0].best_match)

asyncio.run(main())
```

### Exceptions

```python
from lipi import (
    LipiError,                # Base
    AuthenticationError,      # 401/403 — bad or revoked API key
    InsufficientCreditsError, # 402 — no credits remaining
    RateLimitError,           # 429 — too many requests (.retry_after seconds)
    ImageError,               # 413/422 — invalid or too-large image
    JobFailedError,           # Job processing failed (.job_id)
    ServerError,              # 5xx — server-side error
    TimeoutError,             # Polling timed out (.job_id)
)
```

## CLI

```bash
# Font identification
lipi font-match image.png
lipi font-match image.png --json-output
lipi font-match image.png -o results.json

# URL scanning
lipi url-scan https://stripe.com
lipi url-scan https://stripe.com --json-output

# Batch processing
lipi batch ./screenshots --output results.csv
lipi batch ./screenshots --output results.csv --retry-failed
lipi batch ./screenshots --output results.csv --no-resume

# Batch URL scanning
lipi batch-urls urls.txt --output scan_results.csv

# Account
lipi credits
lipi usage --limit 20 --from 2026-04-01

# Auth
lipi auth set-key lpi_your_key
lipi auth show
```

### CLI Output Example

```
Analyzed screenshot.png in 12.3s

Found 2 text region(s):

  "NIZO"
  Best match:  Eurostile Extended Bold Italic
  Commercial:  Microgramma D Extended Bold Italic, ITC Machine Bold Oblique
  Free:        Michroma, Orbitron Bold

  "Premium Quality"
  Best match:  Garamond Premier Pro
  Commercial:  Adobe Garamond, Sabon
  Free:        EB Garamond, Cormorant Garamond

Credits remaining: 8 (6 free + 2 paid)
```

### Batch CLI Output

```
Credits available: 42 (6 free + 36 paid)
Input: ./screenshots
Output: results.csv

[1/35] analyzing logo_v2.png... done
[2/35] analyzing banner.png... done
[3/35] analyzing social.png... failed

Batch complete in 423.1s: 33 succeeded, 2 failed, 12 skipped
Results saved to results.csv
Credits remaining: 7 (0 free + 7 paid)
```

## Response Models

All API responses are typed Pydantic models:

- `FontMatchResult` — font identification results
  - `.results: list[TextResult]` — per-text-region matches
  - `.texts` — alias for `.results`
- `TextResult` — single text region
  - `.best_match` — most likely commercial font
  - `.commercial_alternatives` — close commercial alternatives
  - `.free_alternatives` — closest free alternatives
  - `.reasoning` — analysis reasoning
- `UrlScanResult` — URL scan results
  - `.fonts_detected: list[FontDetected]`
  - `.license_results: list[LicenseResult]`
  - `.compliance_summary: ComplianceSummary`
- `CreditBalance` — credit balance
  - `.total_credits` — free + paid
- `UsageHistory` — paginated usage logs
- `BatchStats` — batch processing summary

## Pricing

- **Free tier:** 10 credits/month
- **Subscription:** $75/month for 100 credits
- **Top-up:** $60 for 100 additional credits (subscribers only)
- Each `font_match` or `url_scan` call costs **1 credit**
- Failed jobs are automatically refunded

Get your API key at [lipi.ai/dashboard/api-keys](https://lipi.ai/dashboard/api-keys).

## Development

```bash
git clone https://github.com/lipi-ai/lipi-python.git
cd lipi-python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT
