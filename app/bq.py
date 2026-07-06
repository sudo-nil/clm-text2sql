"""BigQuery execution layer: guardrails, dry-run validation, and execution.

Guardrails enforced here (not just prompted for in the LLM):
- SELECT-only: any DML/DDL keyword or multi-statement input is rejected.
- Dataset scope: every referenced table must live in the configured project.dataset.
- maximum_bytes_billed cap on every job, dry-run and real.
- A default row LIMIT is appended to exploratory queries that lack one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from google.api_core.exceptions import GoogleAPIError
from google.cloud import bigquery

from app.config import Settings

DEFAULT_MAX_BYTES_BILLED = 1_000_000_000  # 1 GB -- generous for this dataset's size
DEFAULT_ROW_LIMIT = 1000

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|CALL|EXPORT|LOAD)\b",
    re.IGNORECASE,
)
_LEADING_KEYWORD = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_TOP_LEVEL_LIMIT = re.compile(r"\bLIMIT\s+\d+\s*$", re.IGNORECASE)


class GuardrailViolation(Exception):
    """Raised when a query violates a guardrail (SELECT-only, dataset scope, ...)."""


@dataclass
class DryRunResult:
    valid: bool
    total_bytes_processed: int = 0
    error: str | None = None


@dataclass
class ExecutionResult:
    rows: list[dict] = field(default_factory=list)
    sql: str = ""
    total_bytes_processed: int = 0
    total_bytes_billed: int = 0


def enforce_select_only(sql: str) -> None:
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise GuardrailViolation("Multiple statements are not allowed.")
    if _FORBIDDEN_KEYWORDS.search(stripped):
        raise GuardrailViolation("Only SELECT queries are allowed (found a DML/DDL keyword).")
    if not _LEADING_KEYWORD.match(stripped):
        raise GuardrailViolation("Query must start with SELECT or WITH.")


def add_default_limit(sql: str, limit: int = DEFAULT_ROW_LIMIT) -> str:
    """Append a LIMIT to exploratory queries that don't already end with one.

    Appends rather than wraps in a subquery so an existing top-level ORDER BY
    is preserved (a subquery wrapper does not guarantee row order).
    """
    stripped = sql.strip().rstrip(";").rstrip()
    if _TOP_LEVEL_LIMIT.search(stripped):
        return stripped
    return f"{stripped}\nLIMIT {limit}"


class BigQueryExecutor:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()
        self.client = bigquery.Client(project=self.settings.project)

    def _job_config(self, dry_run: bool) -> bigquery.QueryJobConfig:
        return bigquery.QueryJobConfig(
            dry_run=dry_run,
            maximum_bytes_billed=DEFAULT_MAX_BYTES_BILLED,
        )

    def _check_dataset_scope(self, job: bigquery.QueryJob) -> None:
        allowed = (self.settings.project, self.settings.dataset)
        for table in job.referenced_tables or []:
            if (table.project, table.dataset_id) != allowed:
                raise GuardrailViolation(
                    f"Query references `{table.project}.{table.dataset_id}.{table.table_id}`, "
                    f"outside the allowed dataset `{allowed[0]}.{allowed[1]}`."
                )

    def dry_run(self, sql: str) -> DryRunResult:
        enforce_select_only(sql)
        try:
            job = self.client.query(sql, job_config=self._job_config(dry_run=True))
            self._check_dataset_scope(job)
        except GuardrailViolation as e:
            return DryRunResult(valid=False, error=str(e))
        except GoogleAPIError as e:
            return DryRunResult(valid=False, error=str(e))
        return DryRunResult(valid=True, total_bytes_processed=job.total_bytes_processed or 0)

    def execute(self, sql: str, apply_default_limit: bool = True) -> ExecutionResult:
        enforce_select_only(sql)
        final_sql = add_default_limit(sql) if apply_default_limit else sql
        job = self.client.query(final_sql, job_config=self._job_config(dry_run=False))
        result = job.result()
        rows = [dict(row) for row in result]
        return ExecutionResult(
            rows=rows,
            sql=final_sql,
            total_bytes_processed=job.total_bytes_processed or 0,
            total_bytes_billed=job.total_bytes_billed or 0,
        )
