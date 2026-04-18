"""Async font identification with AsyncClient.

Requires: pip install lipi[async]
"""

import asyncio

from lipi import AsyncClient


async def main():
    async with AsyncClient() as client:
        # Check credits first
        credits = await client.get_credits()
        print(f"Credits: {credits.total_credits}")

        # Identify fonts
        result = await client.font_match("screenshot.png")
        for text in result.texts:
            print(f'"{text.text}" → {text.best_match}')

        # Scan a URL
        scan = await client.url_scan("https://example.com")
        print(f"\nURL risk: {scan.compliance_summary.overall_risk}")
        for font in scan.fonts_detected:
            print(f"  {font.family}: {', '.join(font.weights)}")


asyncio.run(main())
