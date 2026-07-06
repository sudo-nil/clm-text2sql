"""Explicit BigQuery table schemas for the `clm` dataset.

Column order/types here must match the Parquet output of data_gen/generate.py.
"""
from google.cloud import bigquery

SchemaField = bigquery.SchemaField

TABLES: dict[str, list[SchemaField]] = {
    "business_units": [
        SchemaField("business_unit_id", "STRING", mode="REQUIRED"),
        SchemaField("name", "STRING", mode="REQUIRED"),
        SchemaField("region", "STRING", mode="REQUIRED"),
    ],
    "users": [
        SchemaField("user_id", "STRING", mode="REQUIRED"),
        SchemaField("full_name", "STRING", mode="REQUIRED"),
        SchemaField("role", "STRING", mode="REQUIRED"),
        SchemaField("email", "STRING", mode="REQUIRED"),
    ],
    "counterparties": [
        SchemaField("counterparty_id", "STRING", mode="REQUIRED"),
        SchemaField("name", "STRING", mode="REQUIRED"),
        SchemaField("legal_name", "STRING", mode="REQUIRED"),
        SchemaField("entity_type", "STRING", mode="REQUIRED"),
        SchemaField("jurisdiction", "STRING", mode="REQUIRED"),
        SchemaField("country", "STRING", mode="REQUIRED"),
        SchemaField("industry", "STRING", mode="REQUIRED"),
        SchemaField("risk_tier", "STRING", mode="REQUIRED"),
    ],
    "matters": [
        SchemaField("matter_id", "STRING", mode="REQUIRED"),
        SchemaField("name", "STRING", mode="REQUIRED"),
        SchemaField("matter_type", "STRING", mode="REQUIRED"),
        SchemaField("lead_counsel_user_id", "STRING", mode="REQUIRED"),
        SchemaField("status", "STRING", mode="REQUIRED"),
    ],
    "contracts": [
        SchemaField("contract_id", "STRING", mode="REQUIRED"),
        SchemaField("title", "STRING", mode="REQUIRED"),
        SchemaField("contract_type", "STRING", mode="REQUIRED"),
        SchemaField("counterparty_id", "STRING", mode="REQUIRED"),
        SchemaField("business_unit_id", "STRING", mode="REQUIRED"),
        SchemaField("owner_user_id", "STRING", mode="REQUIRED"),
        SchemaField("matter_id", "STRING", mode="NULLABLE"),
        SchemaField("status", "STRING", mode="REQUIRED"),
        SchemaField("governing_law", "STRING", mode="REQUIRED"),
        SchemaField("effective_date", "DATE", mode="REQUIRED"),
        SchemaField("execution_date", "DATE", mode="NULLABLE"),
        SchemaField("expiration_date", "DATE", mode="NULLABLE"),
        SchemaField("total_value", "NUMERIC", mode="NULLABLE"),
        SchemaField("currency", "STRING", mode="REQUIRED"),
        SchemaField("auto_renew", "BOOL", mode="REQUIRED"),
        SchemaField("renewal_term_months", "INT64", mode="NULLABLE"),
        SchemaField("notice_period_days", "INT64", mode="NULLABLE"),
        SchemaField("fiscal_year", "INT64", mode="REQUIRED"),
        SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    ],
    "clauses": [
        SchemaField("clause_id", "STRING", mode="REQUIRED"),
        SchemaField("contract_id", "STRING", mode="REQUIRED"),
        SchemaField("clause_type", "STRING", mode="REQUIRED"),
        SchemaField("is_nonstandard", "BOOL", mode="REQUIRED"),
        SchemaField("summary", "STRING", mode="REQUIRED"),
    ],
    "obligations": [
        SchemaField("obligation_id", "STRING", mode="REQUIRED"),
        SchemaField("contract_id", "STRING", mode="REQUIRED"),
        SchemaField("obligation_type", "STRING", mode="REQUIRED"),
        SchemaField("description", "STRING", mode="REQUIRED"),
        SchemaField("owner_user_id", "STRING", mode="REQUIRED"),
        SchemaField("due_date", "DATE", mode="REQUIRED"),
        SchemaField("status", "STRING", mode="REQUIRED"),
        SchemaField("amount", "NUMERIC", mode="NULLABLE"),
    ],
    "renewals": [
        SchemaField("renewal_id", "STRING", mode="REQUIRED"),
        SchemaField("contract_id", "STRING", mode="REQUIRED"),
        SchemaField("renewal_date", "DATE", mode="REQUIRED"),
        SchemaField("renewal_type", "STRING", mode="REQUIRED"),
        SchemaField("new_expiration_date", "DATE", mode="NULLABLE"),
        SchemaField("value_change", "NUMERIC", mode="NULLABLE"),
    ],
}

# Load order matters for readability/debugging only; BigQuery does not
# enforce FK constraints, so this is not required for correctness.
LOAD_ORDER = [
    "business_units", "users", "counterparties", "matters",
    "contracts", "clauses", "obligations", "renewals",
]

CLUSTERING_FIELDS = {
    "contracts": ["contract_type", "counterparty_id"],
}
