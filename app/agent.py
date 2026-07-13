"""Text-to-SQL agent: generate -> validate (dry-run) -> repair -> execute.

The generate/validate/repair loop is a LangGraph StateGraph (app/agent.py's
_build_graph). Execution is a plain call after the graph produces valid SQL,
kept outside the graph so callers (the eval harness in particular) can
dry-run-validate without paying for execution, or execute with different
guardrail options.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.bq import BigQueryExecutor, ExecutionResult
from app.config import Settings
from app.llm import LLM, GeminiLLM
from app.schema import build_few_shot_examples, build_schema_context

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """
You are a meticulous BigQuery SQL analyst for an in-house legal team's Contract
Lifecycle Management (CLM) system. Translate the user's question into a single
BigQuery Standard SQL query.

{schema_context}

FEW-SHOT EXAMPLES:
{few_shot_examples}

RULES:
- Output ONLY the SQL query. No prose, no explanation, no markdown code fences.
- SELECT-only. Never write DML/DDL (no INSERT/UPDATE/DELETE/CREATE/DROP/MERGE).
- Always fully-qualify table names as `{dataset}.table_name`.
- Apply the VALUE HINTS above wherever relevant -- they exist because the literal
  schema is not enough to answer correctly.

Question: {question}
SQL:
""".strip()

REPAIR_PROMPT_TEMPLATE = """
The following BigQuery Standard SQL query failed validation.

SQL:
{sql}

Error from BigQuery:
{error}

{schema_context}

Fix the SQL so it is valid BigQuery Standard SQL and still answers the original
question: "{question}"

Output ONLY the corrected SQL. No prose, no explanation, no markdown code fences.
""".strip()

_SQL_FENCE_RE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def build_prompt(question: str, dataset: str) -> str:
    return PROMPT_TEMPLATE.format(
        schema_context=build_schema_context(dataset),
        few_shot_examples=build_few_shot_examples(dataset),
        dataset=dataset,
        question=question,
    )


def extract_sql(raw_text: str) -> str:
    return _SQL_FENCE_RE.sub("", raw_text.strip()).strip()


@dataclass
class GenerationResult:
    sql: str
    attempts: int
    dry_run_bytes: int
    repaired: bool
    repair_history: list[str] = field(default_factory=list)


class AgentState(TypedDict, total=False):
    question: str
    sql: str
    attempts: int
    dry_run_error: Optional[str]
    dry_run_bytes: int
    repair_history: list[str]


class Text2SqlAgent:
    def __init__(
        self,
        llm: LLM | None = None,
        settings: Settings | None = None,
        executor: BigQueryExecutor | None = None,
        max_repair_attempts: int = 2,
    ) -> None:
        self.settings = settings or Settings.load()
        self.llm = llm or GeminiLLM(self.settings)
        self.executor = executor or BigQueryExecutor(self.settings)
        self.max_repair_attempts = max_repair_attempts
        self.graph = self._build_graph()

    def generate_sql(self, question: str) -> str:
        prompt = build_prompt(question, self.settings.dataset)
        raw = self.llm.generate(prompt)
        return extract_sql(raw)

    def _repair(self, question: str, sql: str, error: str) -> str:
        prompt = REPAIR_PROMPT_TEMPLATE.format(
            sql=sql,
            error=error,
            schema_context=build_schema_context(self.settings.dataset),
            question=question,
        )
        raw = self.llm.generate(prompt)
        return extract_sql(raw)

    # --- LangGraph nodes -----------------------------------------------------

    def _node_generate(self, state: AgentState) -> dict:
        return {"sql": self.generate_sql(state["question"]), "attempts": 1, "repair_history": []}

    def _node_validate(self, state: AgentState) -> dict:
        dry_run = self.executor.dry_run(state["sql"])
        if dry_run.valid:
            return {"dry_run_error": None, "dry_run_bytes": dry_run.total_bytes_processed}
        return {"dry_run_error": dry_run.error or "unknown error"}

    def _node_repair(self, state: AgentState) -> dict:
        logger.warning(
            "Dry-run validation failed (attempt %d): %s", state["attempts"], state["dry_run_error"]
        )
        sql = self._repair(state["question"], state["sql"], state["dry_run_error"])
        history = [*state.get("repair_history", []), state["dry_run_error"]]
        return {"sql": sql, "attempts": state["attempts"] + 1, "repair_history": history}

    def _node_fail(self, state: AgentState) -> dict:
        logger.error(
            "Giving up after %d attempt(s), question=%r, last error=%s",
            state["attempts"], state["question"], state["dry_run_error"],
        )
        raise RuntimeError(
            f"SQL failed validation after {state['attempts']} attempt(s): {state['dry_run_error']}\n"
            f"Last SQL:\n{state['sql']}"
        )

    def _route_after_validate(self, state: AgentState) -> str:
        if state.get("dry_run_error") is None:
            return "ok"
        if state["attempts"] > self.max_repair_attempts:
            return "fail"
        return "repair"

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("generate", self._node_generate)
        graph.add_node("validate", self._node_validate)
        graph.add_node("repair", self._node_repair)
        graph.add_node("fail", self._node_fail)
        graph.set_entry_point("generate")
        graph.add_edge("generate", "validate")
        graph.add_conditional_edges(
            "validate",
            self._route_after_validate,
            {"ok": END, "repair": "repair", "fail": "fail"},
        )
        graph.add_edge("repair", "validate")
        graph.add_edge("fail", END)
        return graph.compile()

    # --- public API ------------------------------------------------------------

    def generate_validated_sql(self, question: str) -> GenerationResult:
        """Run the generate -> validate -> repair graph to a valid SQL query."""
        final_state = self.graph.invoke({"question": question})
        return GenerationResult(
            sql=final_state["sql"],
            attempts=final_state["attempts"],
            dry_run_bytes=final_state.get("dry_run_bytes", 0),
            repaired=bool(final_state.get("repair_history")),
            repair_history=final_state.get("repair_history", []),
        )

    def answer(self, question: str) -> tuple[ExecutionResult, GenerationResult]:
        generation = self.generate_validated_sql(question)
        execution = self.executor.execute(generation.sql)
        return execution, generation
