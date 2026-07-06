"""Create the `clm` BigQuery dataset and load the generated Parquet tables.

Idempotent: tables are dropped and recreated from an explicit schema on every
run, then loaded fresh (WRITE_TRUNCATE).

Run: python -m data_gen.load_bq
"""
from __future__ import annotations

import os

from google.cloud import bigquery

from app.config import Settings
from data_gen.bq_schema import CLUSTERING_FIELDS, LOAD_ORDER, TABLES
from data_gen.generate import OUTPUT_DIR

SHOWCASE_QUERIES = {
    "missing_lol_in_ca": """
        SELECT c.contract_id, c.title, c.governing_law, c.status
        FROM `{dataset}.contracts` c
        WHERE c.governing_law = 'California'
          AND NOT EXISTS (
            SELECT 1 FROM `{dataset}.clauses` cl
            WHERE cl.contract_id = c.contract_id
              AND cl.clause_type = 'Limitation of Liability'
          )
        LIMIT 10
    """,
    "acme_name_normalization": """
        SELECT cp.name, cp.legal_name, COUNT(*) AS contract_count
        FROM `{dataset}.contracts` c
        JOIN `{dataset}.counterparties` cp USING (counterparty_id)
        WHERE UPPER(cp.legal_name) LIKE '%ACME%'
        GROUP BY cp.name, cp.legal_name
        ORDER BY contract_count DESC
    """,
    "auto_renew_next_90_days": """
        SELECT contract_id, title, contract_type, expiration_date, notice_period_days
        FROM `{dataset}.contracts`
        WHERE auto_renew
          AND expiration_date IS NOT NULL
          AND expiration_date BETWEEN CURRENT_DATE() AND DATE_ADD(CURRENT_DATE(), INTERVAL 90 DAY)
        ORDER BY expiration_date
        LIMIT 10
    """,
}


def ensure_dataset(client: bigquery.Client, settings: Settings) -> None:
    dataset_ref = bigquery.DatasetReference(settings.project, settings.dataset)
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = settings.location
    client.create_dataset(dataset, exists_ok=True)
    print(f"[dataset] {settings.project}.{settings.dataset} ready in {settings.location}")


def recreate_table(client: bigquery.Client, settings: Settings, table_name: str) -> bigquery.TableReference:
    table_ref = bigquery.DatasetReference(settings.project, settings.dataset).table(table_name)
    client.delete_table(table_ref, not_found_ok=True)
    table = bigquery.Table(table_ref, schema=TABLES[table_name])
    if table_name in CLUSTERING_FIELDS:
        table.clustering_fields = CLUSTERING_FIELDS[table_name]
    client.create_table(table)
    return table_ref


def load_table(client: bigquery.Client, table_ref: bigquery.TableReference, table_name: str) -> int:
    path = os.path.join(OUTPUT_DIR, f"{table_name}.parquet")
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        schema=TABLES[table_name],
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    with open(path, "rb") as f:
        job = client.load_table_from_file(f, table_ref, job_config=job_config)
    job.result()
    table = client.get_table(table_ref)
    return table.num_rows


def run_verification(client: bigquery.Client, settings: Settings) -> None:
    dataset = f"{settings.project}.{settings.dataset}"
    print("\n=== Row counts ===")
    for name in LOAD_ORDER:
        rows = list(client.query(f"SELECT COUNT(*) AS n FROM `{dataset}.{name}`").result())
        print(f"  {name:>15}: {rows[0].n}")

    for name in ("contracts", "clauses"):
        print(f"\n=== Sample rows: {name} ===")
        rows = client.query(f"SELECT * FROM `{dataset}.{name}` LIMIT 5").result()
        for row in rows:
            print(f"  {dict(row)}")

    print("\n=== Showcase queries ===")
    for query_name, sql_template in SHOWCASE_QUERIES.items():
        sql = sql_template.format(dataset=dataset)
        rows = list(client.query(sql).result())
        print(f"  {query_name}: {len(rows)} row(s) {'OK' if rows else 'EMPTY -- unexpected'}")


def main() -> None:
    settings = Settings.load()
    client = bigquery.Client(project=settings.project)

    ensure_dataset(client, settings)
    for table_name in LOAD_ORDER:
        table_ref = recreate_table(client, settings, table_name)
        n = load_table(client, table_ref, table_name)
        print(f"[load] {table_name}: {n} rows")

    run_verification(client, settings)


if __name__ == "__main__":
    main()
