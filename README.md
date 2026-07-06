# clm-text2sql

A text-to-SQL agent for a synthetic **Contract Lifecycle Management (CLM)**
database on BigQuery. Ask a natural-language question about contracts,
clauses, obligations, and renewals; get back an answer table and the exact
SQL that produced it, as a citation.

The centerpiece is the schema itself and the evaluation harness: the
synthetic data deliberately bakes in the messy realities of a real CLM
system (fuzzy contract-type naming, inconsistent legal-entity casing, a
non-calendar fiscal year, a clause-presence model instead of boolean flags)
so that "getting the SQL right" actually means something.

## Architecture

```
schemas/    one YAML per table (columns + table-specific value hints) + _dataset.yaml
            (foreign keys + few-shot examples) -- see schemas/example.yaml for the format
data_gen/   synthetic CLM data generator (Faker + numpy, seeded) -> Parquet -> BigQuery
app/
  config.py     env-driven settings (project/location/dataset/model)
  schema.py     loads schemas/*.yaml, renders schema description + value hints
  llm.py        swappable LLM interface (Vertex AI Gemini via google-genai)
  bq.py         BigQuery execution layer: guardrails, dry-run, execute
  agent.py      LangGraph StateGraph: generate -> dry-run validate -> self-repair
  cli.py        `python -m app.cli "question"`
eval/
  questions.yaml   {id, question, gold_sql, tier}
  run.py           execution-accuracy scorer, per-tier scorecard
tests/      pure-function unit tests (guardrails, prompt building, eval comparison)
```

**Schema as data**: every table's columns and "gotcha" rules (fiscal year,
clause-presence anti-join, fuzzy NDA types, ...) live in `schemas/*.yaml`
rather than in Python -- `app/schema.py` is just a loader/renderer. Add or
edit a table by editing its YAML file; no code changes needed.

**Agent loop** (`app/agent.py`) is a LangGraph `StateGraph` with four nodes:

```
generate -> validate -> [ok: END | repair: back to validate | fail: raise]
```

1. `generate`: build a prompt from the schema YAML (description + value
   hints + a few tiered few-shot examples: filter, join, anti-join) and ask
   Gemini for SQL.
2. `validate`: a BigQuery **dry run** (catches bad columns/joins, estimates
   bytes scanned) plus the guardrails below.
3. On failure, `repair` feeds the BigQuery error back to the model and loops
   back to `validate`, up to `max_repair_attempts` (default 2) before the
   `fail` node raises.
4. Execution happens after the graph returns valid SQL (kept outside the
   graph so the eval harness can dry-run-validate without executing, or
   execute with different guardrail options) -- returns rows + the final SQL
   + bytes billed.

**Guardrails** (enforced in code, not just prompted for): SELECT-only /
single-statement only; every referenced table must live in the configured
`project.dataset`; a `maximum_bytes_billed` cap on every job; a default
`LIMIT` appended to exploratory queries that don't already have one.

## Prerequisites

- A GCP project with the **BigQuery API** and **Vertex AI API** enabled.
- `gcloud auth application-default login` run once, so both `google-cloud-bigquery`
  and `google-genai` (Vertex AI mode) pick up the same Application Default
  Credentials. There is no separate API key -- one project, one login.
- [`uv`](https://docs.astral.sh/uv/) (or a venv + pip) and Python 3.11+.

## Setup

```bash
uv sync --extra dev            # installs pinned deps into .venv
cp .env.example .env           # then fill in your project/location
```


Verify connectivity (BigQuery `SELECT 1` + a Gemini smoke call, both under ADC):

```bash
uv run python -m app.check_connectivity
```

## Generate and load the data

```bash
uv run python -m data_gen.generate   # synthetic CLM data -> data_gen/output/*.parquet
uv run python -m data_gen.load_bq    # (re)creates the `clm` dataset/tables, loads them
```

Both steps are deterministic (seeded) and idempotent -- `load_bq` drops and
recreates each table from an explicit schema every run, so it always
reproduces the same ~2,000 contracts / ~5,000 clauses / ~4,000 obligations /
~1,200 renewals across ~700 counterparties. `load_bq` finishes by printing row
counts, 5 sample rows from `contracts` and `clauses`, and confirming three
showcase queries (the anti-join, the name-normalization join, and the
near-expiry auto-renewal filter) return non-empty results.

Re-run `data_gen.generate` any time you want a fresh "now" anchor (the ~7% of
contracts expiring in the next 90 days, and the fiscal-year distribution, are
computed relative to the day you generate).

## Ask a question

```bash
uv run python -m app.cli "Which NDAs auto-renew in the next 90 days?"
```

Prints the row count, bytes billed, the final SQL used (including any
self-repair), and up to 50 rows.

## Run the eval

```bash
uv run python -m eval.run
```

Runs every question in `eval/questions.yaml` through both `gold_sql` and the
agent, and compares result sets (order-insensitive unless `gold_sql` has an
explicit `ORDER BY`; tolerant of the agent selecting extra descriptive
columns beyond what gold selected). Prints an overall + per-tier scorecard,
plus expected-vs-actual diffs for anything that fails. Current scorecard:
**13/13 (100%)** across `filters`, `joins`, `advanced`, and `traps`.

Add more questions to `eval/questions.yaml` to expand coverage -- each just
needs `{id, question, gold_sql, tier}`, and `gold_sql` should use
`CURRENT_DATE()` rather than a hardcoded date for anything time-relative,
since the data is regenerated "now"-anchored.

## Tests

```bash
uv run pytest
```

## Failure modes: the six traps

A naive text-to-SQL model gets each of these wrong in a specific,
predictable way. Here's what breaks, and how the schema/prompt/agent handles
it.

**1. Missing-clause anti-join** -- *"Which active contracts are missing an
indemnification clause?"* `clauses` only has a row when a clause is
*present*; there's no boolean flag. The naive mistake is
`clause_type != 'Indemnification'`, which returns contracts that have a
*different* clause, not contracts lacking it. Fix: the rule in
`schemas/clauses.yaml` spells out the anti-join (`NOT EXISTS` / `LEFT JOIN
... IS NULL`), reinforced by a few-shot example in `schemas/_dataset.yaml`
using exactly that pattern.

**2. Counterparty name normalization** -- *"How many contracts do we have
with Acme?"* `legal_name` is stored ALL-CAPS with an entity suffix
("ACME GLOBAL LLC"), so a literal `name = 'Acme'` matches nothing. Worse, a
brand can span multiple `counterparty_id` rows (regional entities -- the
dataset seeds "Acme Global", "Acme Solutions", "Acme Europe" on purpose).
Fix: the rules in `schemas/counterparties.yaml` tell the model to match
case-insensitively against either `name` or `legal_name`, and not to assume
a 1:1 name-to-ID mapping.

**3. Fiscal year** -- *"Total contract value signed last fiscal year."* The
company FY runs Feb 1 - Jan 31 and is labeled by the year it *ends* in, not
the calendar year. Fix: `contracts.fiscal_year` is precomputed at generation
time using this exact rule, and the fiscal-year rule in
`schemas/contracts.yaml` tells the model to prefer that column over deriving
FY itself from `effective_date`/`execution_date`.

**4. Notice window** -- *"Which auto-renewing contracts do we need to act on
in the next 30 days to stop renewal?"* The actionable deadline is
`expiration_date - notice_period_days`, not `expiration_date` itself. Fix:
the notice-window rule in `schemas/contracts.yaml` gives the exact
`DATE_SUB(expiration_date, INTERVAL notice_period_days DAY)` expression.

**5. Computed "active"** -- *"How many active contracts are there?"*
`status` can lag behind reality (a row can say `Active` while
`expiration_date` has quietly passed, or vice versa in messy real systems).
Fix: the "active contracts" rule in `schemas/contracts.yaml` defines it as a
combination of `status` and `expiration_date >= CURRENT_DATE()`, not
`status` alone.

**6. Fuzzy contract type** -- *"How many NDAs are there?"* ~18% of NDA rows
are stored under a realistic synonym ("Mutual NDA", "Confidentiality
Agreement") instead of the literal string "NDA". Fix: the fuzzy-type rule in
`schemas/contracts.yaml` lists the synonym set and tells the model to match
all of them for an "NDA" question.

All six are covered by dedicated `traps` tier questions in
`eval/questions.yaml`, scored separately from `filters`/`joins`/`advanced` so
regressions in trap-handling are visible even if overall accuracy looks
fine.

## Guardrails vs. self-repair -- what each layer catches

- **Guardrails** (`app/bq.py`) are hard stops: DML/DDL, multi-statement
  input, and out-of-dataset table references are rejected before ever
  reaching BigQuery, regardless of what the model produces.
- **Dry-run validation** catches anything BigQuery itself would reject --
  bad column names, malformed joins, type errors -- without spending query
  bytes.
- **Self-repair** feeds the exact BigQuery error back to the model (same
  schema context, same question) and asks for a fix, up to 2 retries. This
  is what recovers from typos and minor join mistakes without giving up on
  the first failure.

None of these layers catch *semantic* mistakes (a syntactically valid query
that answers the wrong question) -- that's what the eval harness's
execution-accuracy comparison against `gold_sql` is for.
