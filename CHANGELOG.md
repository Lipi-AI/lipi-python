# Changelog

## 0.1.0 (2026-04-18)

Initial release.

- Sync client (`lipi.Client`) with built-in polling
- Async client (`lipi.AsyncClient`) via `pip install lipi[async]`
- Font identification from images (`client.font_match()`)
- URL font scanning (`client.url_scan()`)
- Credit balance and usage history
- Batch processing with crash recovery (`lipi.batch.batch_font_match()`)
- CLI tool (`lipi font-match`, `lipi batch`, `lipi url-scan`, etc.)
- Pydantic models for all API responses
- Comprehensive error handling with typed exceptions
