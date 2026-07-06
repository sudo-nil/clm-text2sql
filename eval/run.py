"""Execution-accuracy eval harness.

Loads eval/questions.yaml, runs both gold_sql and agent-generated SQL for each
question, and compares result sets (order-insensitive unless gold_sql has an
explicit ORDER BY). Prints a per-tier scorecard plus failure diffs.

Run: python -m eval.run
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import yaml

from app.agent import Text2SqlAgent
from app.bq import BigQueryExecutor
from app.config import Settings

QUESTIONS_PATH = Path(__file__).parent / "questions.yaml"
TIER_ORDER = ["filters", "joins", "advanced", "traps"]

_ORDER_BY_RE = re.compile(r"\border\s+by\b", re.IGNORECASE)


def _has_top_level_order_by(sql: str) -> bool:
    """True only if `sql` has an ORDER BY in its outermost query.

    A naive substring match also fires on ORDER BY inside subqueries and
    window functions (e.g. ROW_NUMBER() OVER (... ORDER BY ...)), which would
    wrongly force an order-sensitive comparison on a result set that has no
    defined row order. We only care about a trailing, top-level ORDER BY, so
    we require the match to sit at parenthesis depth 0.
    """
    depths = []
    depth = 0
    for ch in sql:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        depths.append(depth)
    return any(depths[m.start()] == 0 for m in _ORDER_BY_RE.finditer(sql))


@dataclass
class QuestionResult:
    id: str
    tier: str
    question: str
    passed: bool
    error: str | None = None
    generated_sql: str = ""
    gold_sql: str = ""
    expected: list = field(default_factory=list)
    actual: list = field(default_factory=list)


def load_questions() -> list[dict]:
    with open(QUESTIONS_PATH) as f:
        return yaml.safe_load(f)["questions"]


def _project(rows: list[dict], cols: list[str]) -> list[tuple]:
    return [tuple(row[c] for c in cols) for row in rows]


def _tuples_match(expected: list[tuple], actual: list[tuple], order_sensitive: bool) -> bool:
    if order_sensitive:
        return expected == actual
    key = lambda t: [str(v) for v in t]  # noqa: E731
    return sorted(expected, key=key) == sorted(actual, key=key)


def rows_equal(expected: list[dict], actual: list[dict], order_sensitive: bool) -> bool:
    """Compare result sets by VALUES, tolerant of extra/reordered columns in `actual`.

    The agent may reasonably select more descriptive columns than gold_sql
    (e.g. adding `title` alongside `contract_id`) without being wrong, so we
    only require that *some* same-sized subset of actual's columns reproduces
    gold's value multiset -- not that the column list matches exactly.
    """
    if not expected and not actual:
        return True
    if not expected or not actual:
        return False

    gold_cols = list(expected[0].keys())
    actual_cols = list(actual[0].keys())
    n = len(gold_cols)
    if len(actual_cols) < n:
        return False

    gold_tuples = _project(expected, gold_cols)

    same_named = [c for c in gold_cols if c in actual_cols]
    if len(same_named) == n and _tuples_match(gold_tuples, _project(actual, same_named), order_sensitive):
        return True

    if len(actual_cols) == n:
        return _tuples_match(gold_tuples, _project(actual, actual_cols), order_sensitive)

    return any(
        _tuples_match(gold_tuples, _project(actual, list(combo)), order_sensitive)
        for combo in combinations(actual_cols, n)
    )


def run_eval() -> list[QuestionResult]:
    settings = Settings.load()
    agent = Text2SqlAgent(settings=settings)
    executor = BigQueryExecutor(settings=settings)

    results = []
    for q in load_questions():
        gold_sql = q["gold_sql"].format(dataset=settings.dataset)
        order_sensitive = _has_top_level_order_by(gold_sql)

        try:
            gold_result = executor.execute(gold_sql, apply_default_limit=False)
        except Exception as e:
            results.append(QuestionResult(
                id=q["id"], tier=q["tier"], question=q["question"],
                passed=False, error=f"gold_sql failed: {e}", gold_sql=gold_sql,
            ))
            continue

        try:
            generation = agent.generate_validated_sql(q["question"])
            gen_result = executor.execute(generation.sql, apply_default_limit=False)
            passed = rows_equal(gold_result.rows, gen_result.rows, order_sensitive)
            results.append(QuestionResult(
                id=q["id"], tier=q["tier"], question=q["question"], passed=passed,
                generated_sql=generation.sql, gold_sql=gold_sql,
                expected=gold_result.rows, actual=gen_result.rows,
            ))
        except Exception as e:
            results.append(QuestionResult(
                id=q["id"], tier=q["tier"], question=q["question"],
                passed=False, error=str(e), gold_sql=gold_sql,
            ))
    return results


def print_scorecard(results: list[QuestionResult]) -> None:
    by_tier: dict[str, list[QuestionResult]] = {}
    for r in results:
        by_tier.setdefault(r.tier, []).append(r)

    print("=" * 70)
    print("EXECUTION ACCURACY SCORECARD")
    print("=" * 70)
    total_pass = sum(r.passed for r in results)
    print(f"Overall: {total_pass}/{len(results)} ({total_pass / len(results):.1%})\n")

    for tier in TIER_ORDER:
        tier_results = by_tier.get(tier, [])
        if not tier_results:
            continue
        passed = sum(r.passed for r in tier_results)
        print(f"  {tier:>10}: {passed}/{len(tier_results)} ({passed / len(tier_results):.1%})")

    failures = [r for r in results if not r.passed]
    if failures:
        print("\n" + "=" * 70)
        print("FAILURES")
        print("=" * 70)
        for r in failures:
            print(f"\n[{r.tier}] {r.id}: {r.question}")
            if r.error:
                print(f"  ERROR: {r.error}")
            else:
                print(f"  gold_sql:      {' '.join(r.gold_sql.split())}")
                print(f"  generated_sql: {' '.join(r.generated_sql.split())}")
                print(f"  expected ({len(r.expected)} rows): {r.expected[:5]}")
                print(f"  actual   ({len(r.actual)} rows): {r.actual[:5]}")


def main() -> None:
    results = run_eval()
    print_scorecard(results)


if __name__ == "__main__":
    main()
