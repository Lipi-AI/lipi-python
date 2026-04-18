"""Shared polling logic for font-match and url-scan jobs."""

from __future__ import annotations

import time
from typing import Callable, Optional, TypeVar

from lipi.exceptions import TimeoutError

T = TypeVar("T")

DEFAULT_POLL_INTERVAL = 2.5  # seconds
DEFAULT_TIMEOUT = 120  # seconds


def poll_until_done(
    fetch_fn: Callable[[], T],
    is_terminal: Callable[[T], bool],
    job_id: str,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    timeout: float = DEFAULT_TIMEOUT,
    on_poll: Optional[Callable[[T], None]] = None,
) -> T:
    """Poll a job until it reaches a terminal state.

    Args:
        fetch_fn: Callable that fetches the current job state.
        is_terminal: Callable that returns True when the job is done.
        job_id: Job ID for error messages.
        poll_interval: Seconds between polls.
        timeout: Max seconds to wait before raising TimeoutError.
        on_poll: Optional callback invoked after each poll with the current state.

    Returns:
        The final job state.

    Raises:
        TimeoutError: If the job doesn't complete within the timeout.
    """
    start = time.monotonic()

    while True:
        result = fetch_fn()

        if on_poll:
            on_poll(result)

        if is_terminal(result):
            return result

        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            raise TimeoutError(
                f"Job {job_id} did not complete within {timeout}s", job_id=job_id
            )

        time.sleep(poll_interval)
