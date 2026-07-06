"""Loads the table schemas, value hints, and few-shot examples that get fed
to the LLM from schemas/*.yaml, and renders them into prompt text.

Each table has its own YAML file (columns + table-specific rules); see
schemas/example.yaml for the file format this follows. Cross-table rules,
the foreign-key map, and the few-shot examples live in schemas/_dataset.yaml
since they aren't owned by any single table.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

TABLE_FILES = [
    "business_units.yaml",
    "users.yaml",
    "counterparties.yaml",
    "matters.yaml",
    "contracts.yaml",
    "clauses.yaml",
    "obligations.yaml",
    "renewals.yaml",
]
GLOBAL_FILE = "_dataset.yaml"


@lru_cache(maxsize=None)
def _load_yaml(filename: str) -> dict:
    with open(SCHEMAS_DIR / filename) as f:
        return yaml.safe_load(f)


def _clean(text: str) -> str:
    return " ".join(text.split())


def _render_table(table_def: dict) -> str:
    header = table_def["table"]
    description = table_def.get("description")
    if description:
        header = f"{header} ({_clean(description)})"
    lines = [header]
    for col in table_def.get("columns", []):
        desc = col.get("description")
        suffix = f"  -- {_clean(desc)}" if desc else ""
        lines.append(f"  {col['name']} {col['type']}{suffix}")
    return "\n".join(lines)


def build_tables_section() -> str:
    blocks = [_render_table(_load_yaml(fname)) for fname in TABLE_FILES]
    return "\n\n".join(blocks)


def build_foreign_keys_section() -> str:
    fks = _load_yaml(GLOBAL_FILE).get("foreign_keys", [])
    return "\n".join(fks)


def build_value_hints() -> str:
    hints: list[str] = []
    for fname in TABLE_FILES:
        hints.extend(_clean(rule) for rule in _load_yaml(fname).get("rules", []))
    return "\n\n".join(f"{i}. {hint}" for i, hint in enumerate(hints, start=1))


def build_few_shot_examples(dataset: str) -> str:
    examples = _load_yaml(GLOBAL_FILE).get("examples", [])
    blocks = []
    for i, example in enumerate(examples, start=1):
        sql = example["sql"].strip().format(dataset=dataset)
        blocks.append(f"-- Example {i}\nQuestion: {example['question']}\nSQL:\n{sql}")
    return "\n\n".join(blocks)


def build_schema_context(dataset: str) -> str:
    """Full schema context block inserted into the SQL-generation prompt."""
    return (
        f"BigQuery dataset: `{dataset}` (fully-qualify tables as `{dataset}.table_name`)\n\n"
        f"TABLES:\n{build_tables_section()}\n\n"
        f"FOREIGN KEYS:\n{build_foreign_keys_section()}\n\n"
        f"VALUE HINTS (read carefully -- these encode rules the schema alone doesn't show):\n"
        f"{build_value_hints()}"
    )
