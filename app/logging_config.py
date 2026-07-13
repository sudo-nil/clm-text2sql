"""Shared logging setup for every entry point (CLI, connectivity check, eval,
data generation).

This governs *operational* messages -- progress, retries, guardrail
rejections, repair attempts -- via the stdlib `logging` module, level
controlled by the `LOG_LEVEL` env var (default INFO).

It deliberately does not replace `print` everywhere: a tool's actual product
output (the CLI's answer rows, the eval scorecard, load_bq's verification
report) stays as `print`, since that's data meant to be read or piped, not a
log line about the program's own behavior.
"""
from __future__ import annotations

import logging
import os


# Third-party libraries that are chatty at INFO (HTTP request lines, SDK
# internals) and would otherwise drown out our own operational messages.
_QUIET_THIRD_PARTY = ["httpx", "google_genai", "urllib3"]


def configure_logging(level: str | None = None) -> None:
    logging.basicConfig(
        level=(level or os.environ.get("LOG_LEVEL", "INFO")).upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    for name in _QUIET_THIRD_PARTY:
        logging.getLogger(name).setLevel(logging.WARNING)
