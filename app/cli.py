"""CLI entry point.

Run: python -m app.cli "which NDAs auto-renew in the next 90 days?"
"""
from __future__ import annotations

import logging
import sys

from app.agent import Text2SqlAgent
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    if len(sys.argv) < 2:
        print('Usage: python -m app.cli "your question"', file=sys.stderr)
        raise SystemExit(1)
    question = sys.argv[1]

    agent = Text2SqlAgent()
    try:
        execution, generation = agent.answer(question)
    except Exception as e:  # surface a clean message instead of a raw traceback
        logger.error("Failed to answer question: %s", e)
        raise SystemExit(1)

    print(f"Question: {question}\n")
    print("SQL:")
    print(execution.sql)
    repaired_note = f", repaired after {generation.attempts - 1} attempt(s)" if generation.repaired else ""
    print(f"\n{len(execution.rows)} row(s), {execution.total_bytes_billed:,} bytes billed{repaired_note}\n")
    for row in execution.rows[:50]:
        print(row)
    if len(execution.rows) > 50:
        print(f"... ({len(execution.rows) - 50} more rows)")


if __name__ == "__main__":
    main()
