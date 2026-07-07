"""Generate schema YAML files from live BigQuery datasets.

Reads the list of datasets from the `BQ_DATASETS` env var (a JSON array, e.g.
`["clm", "other_project.sales"]`), introspects each one via the BigQuery API,
and writes one `<table>.yaml` per table into `schemas/<dataset>/`, matching the
hand-authored format in `schemas/example.yaml` (table / description / columns).

Column and table `description`s are pulled from BigQuery metadata when present;
otherwise they're omitted so you can fill them in by hand. The valuable
hand-authored parts of a schema file -- `rules`, `value_hints`, and richer
descriptions -- are never clobbered: existing files are skipped unless you pass
`--overwrite`. A `_dataset.yaml` stub (empty `foreign_keys` / `examples`) is
created per dataset so the folder is ready to hand-edit.

Run:
  python -m tools.create_schema                 # all datasets in BQ_DATASETS
  python -m tools.create_schema --datasets clm  # override the list
  python -m tools.create_schema --overwrite     # regenerate existing files
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from google.cloud import bigquery

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"

load_dotenv(REPO_ROOT / ".env")

# BigQuery reports legacy type names; normalize to the standard-SQL spellings
# the rest of the repo's schema files use.
TYPE_MAP = {
    "INTEGER": "INT64",
    "FLOAT": "FLOAT64",
    "BOOLEAN": "BOOL",
}


class _Dumper(yaml.SafeDumper):
    """Emit multi-line strings as block scalars and indent block sequences,
    matching the hand-authored schema files (`  - name:` under `columns:`)."""

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


def _str_representer(dumper: yaml.SafeDumper, data: str):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str_representer)


def parse_datasets(raw: str | None) -> list[str]:
    """Parse BQ_DATASETS, accepting either a JSON array or a comma-separated list."""
    if not raw or not raw.strip():
        return []
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, str):
            return [parsed]
        return [str(d).strip() for d in parsed if str(d).strip()]
    except json.JSONDecodeError:
        return [part.strip() for part in raw.split(",") if part.strip()]


def resolve_ref(entry: str, default_project: str) -> tuple[str, str]:
    """Map a dataset entry to (project, dataset_id). `project.dataset` or bare id."""
    if "." in entry:
        project, dataset_id = entry.split(".", 1)
        return project, dataset_id
    return default_project, entry


def _column_type(field: bigquery.SchemaField) -> str:
    base = TYPE_MAP.get(field.field_type, field.field_type)
    if field.field_type in ("RECORD", "STRUCT"):
        base = "STRUCT"
    if field.mode == "REPEATED":
        return f"ARRAY<{base}>"
    return base


def _column_entry(field: bigquery.SchemaField) -> dict:
    entry: dict = {"name": field.name, "type": _column_type(field)}
    notes = []
    if field.description:
        notes.append(field.description.strip())
    if field.field_type in ("RECORD", "STRUCT") and field.fields:
        notes.append("nested fields: " + ", ".join(f.name for f in field.fields))
    if notes:
        entry["description"] = " -- ".join(notes)
    return entry


def render_table_yaml(table: bigquery.Table) -> str:
    header: dict = {"table": f"{table.dataset_id}.{table.table_id}"}
    if table.description:
        header["description"] = table.description.strip()
    columns = [_column_entry(f) for f in table.schema]

    head_text = yaml.dump(
        header, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100
    )
    cols_text = yaml.dump(
        {"columns": columns}, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100
    )
    return f"{head_text}\n{cols_text}"


DATASET_STUB = (
    "# Cross-table rules, foreign keys, and few-shot examples for this dataset.\n"
    "# Auto-generated stub -- fill these in by hand (introspection can't infer\n"
    "# foreign keys or good examples reliably).\n\n"
    "foreign_keys: []\n\n"
    "examples: []\n"
)


def _write(path: Path, content: str, overwrite: bool) -> str:
    if path.exists() and not overwrite:
        return "skipped (exists)"
    path.write_text(content)
    return "wrote"


def create_for_dataset(
    client: bigquery.Client, project: str, dataset_id: str, overwrite: bool
) -> None:
    ref = bigquery.DatasetReference(project, dataset_id)
    out_dir = SCHEMAS_DIR / dataset_id
    out_dir.mkdir(parents=True, exist_ok=True)

    tables = list(client.list_tables(ref))
    print(f"\n[{project}.{dataset_id}] {len(tables)} table(s) -> {out_dir.relative_to(REPO_ROOT)}/")

    for item in tables:
        table = client.get_table(item.reference)
        path = out_dir / f"{table.table_id}.yaml"
        action = _write(path, render_table_yaml(table), overwrite)
        print(f"  {table.table_id:<24} {action}")

    stub_action = _write(out_dir / "_dataset.yaml", DATASET_STUB, overwrite)
    print(f"  {'_dataset.yaml':<24} {stub_action}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--datasets",
        help="Comma-separated dataset list, overriding the BQ_DATASETS env var.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate files that already exist (default: skip them).",
    )
    args = parser.parse_args()

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        sys.exit("Missing required environment variable: GOOGLE_CLOUD_PROJECT")

    datasets = parse_datasets(args.datasets or os.environ.get("BQ_DATASETS"))
    if not datasets:
        sys.exit(
            "No datasets to process. Set BQ_DATASETS in .env (e.g. BQ_DATASETS=[\"clm\"]) "
            "or pass --datasets."
        )

    client = bigquery.Client(project=project)
    for entry in datasets:
        ds_project, dataset_id = resolve_ref(entry, project)
        create_for_dataset(client, ds_project, dataset_id, args.overwrite)

    print("\nDone.")


if __name__ == "__main__":
    main()
