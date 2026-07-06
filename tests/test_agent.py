from app.agent import build_prompt, extract_sql


def test_extract_sql_strips_code_fences():
    raw = "```sql\nSELECT 1\n```"
    assert extract_sql(raw) == "SELECT 1"


def test_extract_sql_passthrough_when_no_fences():
    assert extract_sql("SELECT 1") == "SELECT 1"


def test_build_prompt_includes_question_and_value_hints():
    prompt = build_prompt("How many NDAs?", "clm")
    assert "How many NDAs?" in prompt
    assert "FISCAL YEAR" in prompt
    assert "clm.contracts" in prompt
