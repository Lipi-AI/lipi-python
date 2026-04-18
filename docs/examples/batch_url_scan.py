"""Batch scan URLs for font compliance.

Create a urls.txt file with one URL per line:
    https://stripe.com
    https://github.com
    https://linear.app

Then run:
    python batch_url_scan.py
"""

from lipi import Client
from lipi.batch import batch_url_scan

client = Client()

stats = batch_url_scan(
    client,
    urls="urls.txt",
    output="scan_results.csv",
    on_progress=lambda idx, total, url, status: print(f"[{idx}/{total}] {url}: {status}"),
)

print(f"\nDone: {stats.succeeded} succeeded, {stats.failed} failed, {stats.skipped} skipped")
print(f"Results saved to scan_results.csv")
