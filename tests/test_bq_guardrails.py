import pytest

from app.bq import GuardrailViolation, add_default_limit, enforce_select_only


def test_select_and_cte_allowed():
    enforce_select_only("SELECT 1")
    enforce_select_only("WITH x AS (SELECT 1) SELECT * FROM x")


@pytest.mark.parametrize("sql", [
    "DELETE FROM clm.contracts",
    "DROP TABLE clm.contracts",
    "INSERT INTO clm.contracts VALUES (1)",
    "UPDATE clm.contracts SET total_value = 1",
    "SELECT 1; DROP TABLE clm.contracts",
])
def test_dml_ddl_and_multi_statement_rejected(sql):
    with pytest.raises(GuardrailViolation):
        enforce_select_only(sql)


def test_add_default_limit_appends_when_missing():
    out = add_default_limit("SELECT * FROM clm.contracts", limit=10)
    assert out.endswith("LIMIT 10")


def test_add_default_limit_noop_when_present():
    sql = "SELECT * FROM clm.contracts ORDER BY contract_id LIMIT 5"
    assert add_default_limit(sql, limit=10) == sql
