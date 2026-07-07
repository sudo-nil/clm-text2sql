"""Loads the table schemas, value hints, and few-shot examples that get fed
to the LLM, and renders them into prompt text.

Schemas are organized per dataset: everything for dataset `<name>` lives in
`schemas/<name>/`. Each table has its own YAML file (columns + table-specific
rules); see `schemas/example.yaml` for the file format. Cross-table rules, the
foreign-key map, the few-shot examples, and an optional table ordering live in
`schemas/<name>/_dataset.yaml` since they aren't owned by any single table.

Generate the per-dataset folder from a live BigQuery dataset with
`python -m tools.create_schema`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
GLOBAL_FILE = "_dataset.yaml"


def _dataset_dir(dataset: str) -> Path:
    path = SCHEMAS_DIR / dataset
    if not path.is_dir():
        raise FileNotFoundError(
            f"No schema folder for dataset '{dataset}': expected {path}. "
            f"Generate one with `python -m tools.create_schema --datasets {dataset}`."
        )
    return path


@lru_cache(maxsize=None)
def _load_yaml(dataset: str, filename: str) -> dict:
    with open(_dataset_dir(dataset) / filename) as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=None)
def _table_files(dataset: str) -> tuple[str, ...]:
    """Table YAML filenames for a dataset, honoring an explicit `tables:` order
    in `_dataset.yaml` and falling back to alphabetical for anything unlisted."""
    present = sorted(
        p.name for p in _dataset_dir(dataset).glob("*.yaml") if p.name != GLOBAL_FILE
    )
    order = _load_yaml(dataset, GLOBAL_FILE).get("tables") if _has_global(dataset) else None
    if not order:
        return tuple(present)

    ordered = [f"{name}.yaml" for name in order if f"{name}.yaml" in present]
    remaining = [name for name in present if name not in ordered]
    return tuple(ordered + remaining)


def _has_global(dataset: str) -> bool:
    return (_dataset_dir(dataset) / GLOBAL_FILE).is_file()


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


def build_tables_section(dataset: str) -> str:
    blocks = [_render_table(_load_yaml(dataset, fname)) for fname in _table_files(dataset)]
    return "\n\n".join(blocks)


def build_foreign_keys_section(dataset: str) -> str:
    if not _has_global(dataset):
        return ""
    fks = _load_yaml(dataset, GLOBAL_FILE).get("foreign_keys", [])
    return "\n".join(fks)


def build_value_hints(dataset: str) -> str:
    hints: list[str] = []
    for fname in _table_files(dataset):
        hints.extend(_clean(rule) for rule in _load_yaml(dataset, fname).get("rules", []))
    return "\n\n".join(f"{i}. {hint}" for i, hint in enumerate(hints, start=1))


def build_few_shot_examples(dataset: str) -> str:
    if not _has_global(dataset):
        return ""
    examples = _load_yaml(dataset, GLOBAL_FILE).get("examples", [])
    blocks = []
    for i, example in enumerate(examples, start=1):
        sql = example["sql"].strip().format(dataset=dataset)
        blocks.append(f"-- Example {i}\nQuestion: {example['question']}\nSQL:\n{sql}")
    return "\n\n".join(blocks)


def build_schema_context(dataset: str) -> str:
    """Full schema context block inserted into the SQL-generation prompt."""
    return (
        f"BigQuery dataset: `{dataset}` (fully-qualify tables as `{dataset}.table_name`)\n\n"
        f"TABLES:\n{build_tables_section(dataset)}\n\n"
        f"FOREIGN KEYS:\n{build_foreign_keys_section(dataset)}\n\n"
        f"VALUE HINTS (read carefully -- these encode rules the schema alone doesn't show):\n"
        f"{build_value_hints(dataset)}"
    )
