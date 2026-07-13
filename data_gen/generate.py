"""Generate synthetic Contract Lifecycle Management (CLM) data to Parquet.

Deterministic: Faker and numpy are both seeded, so re-running produces byte-
identical output (dates are anchored relative to the run date, see README).

Run: python -m data_gen.generate
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from decimal import Decimal

import numpy as np
import pandas as pd
from faker import Faker

from app.logging_config import configure_logging
from data_gen import reference_data as ref

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# Parquet DECIMAL logical type is required for BigQuery NUMERIC columns to
# load correctly (a plain DOUBLE column is rejected at load time).
MONEY_COLUMNS = {
    "contracts": ["total_value"],
    "obligations": ["amount"],
    "renewals": ["value_change"],
}


def to_money(value: float | None) -> Decimal | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return Decimal(str(round(value, 2)))

N_COUNTERPARTIES = 700
N_BUSINESS_UNITS = 40
N_USERS = 60
N_MATTERS = 120
N_CONTRACTS = 2000
FISCAL_YEARS_BACK = 5


def fiscal_year(d: dt.date) -> int:
    """Company FY runs Feb 1 - Jan 31, labeled by the calendar year it ends in.

    e.g. 2024-02-01 .. 2025-01-31 is FY2025.
    """
    return d.year if d.month == 1 else d.year + 1


def weighted_choice(rng: np.random.Generator, options: list, weights: list, size: int) -> np.ndarray:
    return rng.choice(np.array(options, dtype=object), size=size, p=np.array(weights) / sum(weights))


def random_dates(rng: np.random.Generator, start: dt.date, end: dt.date, size: int) -> list[dt.date]:
    span = (end - start).days
    offsets = rng.integers(0, max(span, 1), size=size)
    return [start + dt.timedelta(days=int(o)) for o in offsets]


def build_business_units(rng: np.random.Generator) -> pd.DataFrame:
    combos = [(dept, region) for dept in ref.DEPARTMENTS for region in ref.REGIONS]
    rng.shuffle(combos)
    combos = combos[:N_BUSINESS_UNITS]
    rows = []
    for i, (dept, region) in enumerate(combos, start=1):
        rows.append({
            "business_unit_id": f"BU-{i:04d}",
            "name": dept,
            "region": region,
        })
    return pd.DataFrame(rows)


def build_users(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    roles = weighted_choice(rng, ref.USER_ROLES, ref.USER_ROLE_WEIGHTS, N_USERS)
    rows = []
    for i in range(1, N_USERS + 1):
        name = fake.name()
        email = f"{name.lower().replace(' ', '.').replace(chr(39), '')}@clm-corp.com"
        rows.append({
            "user_id": f"U-{i:04d}",
            "full_name": name,
            "role": roles[i - 1],
            "email": email,
        })
    return pd.DataFrame(rows)


def build_counterparties(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    rows = []
    i = 0

    def make_row(idx: int, name: str, entity_type: str, country: str) -> dict:
        suffix = ref.ENTITY_TYPES[entity_type]["suffix"]
        legal_name = f"{name.upper()} {suffix}"
        if country == "United States":
            jurisdiction = rng.choice(ref.US_STATES)
        else:
            jurisdiction = country
        return {
            "counterparty_id": f"CP-{idx:06d}",
            "name": name,
            "legal_name": legal_name,
            "entity_type": entity_type,
            "jurisdiction": jurisdiction,
            "country": country,
            "industry": rng.choice(ref.INDUSTRIES),
            "risk_tier": weighted_choice(rng, ref.RISK_TIERS, ref.RISK_TIER_WEIGHTS, 1)[0],
        }

    # Deterministic "Acme" brand family for the name-normalization trap.
    for acme in ref.ACME_COUNTERPARTIES:
        i += 1
        rows.append(make_row(i, acme["name"], acme["entity_type"], acme["country"]))

    while i < N_COUNTERPARTIES:
        i += 1
        entity_type = weighted_choice(rng, ref.ENTITY_TYPE_NAMES, ref.ENTITY_TYPE_WEIGHTS, 1)[0]
        country = rng.choice(ref.ENTITY_TYPES[entity_type]["countries"])
        name = fake.company().replace(",", "").split(" LLC")[0].split(" Inc")[0].split(" Ltd")[0]
        rows.append(make_row(i, name, entity_type, country))

    return pd.DataFrame(rows)


def build_matters(rng: np.random.Generator, fake: Faker, users: pd.DataFrame) -> pd.DataFrame:
    counsel = users.loc[users["role"] == "Legal Counsel", "user_id"].to_numpy()
    rows = []
    for i in range(1, N_MATTERS + 1):
        rows.append({
            "matter_id": f"MAT-{i:04d}",
            "name": f"{fake.catch_phrase()} Matter",
            "matter_type": rng.choice(ref.MATTER_TYPES),
            "lead_counsel_user_id": rng.choice(counsel),
            "status": weighted_choice(rng, ref.MATTER_STATUSES, ref.MATTER_STATUS_WEIGHTS, 1)[0],
        })
    return pd.DataFrame(rows)


def build_contracts(
    rng: np.random.Generator,
    fake: Faker,
    counterparties: pd.DataFrame,
    business_units: pd.DataFrame,
    users: pd.DataFrame,
    matters: pd.DataFrame,
) -> pd.DataFrame:
    today = dt.date.today()
    window_start = today - dt.timedelta(days=365 * FISCAL_YEARS_BACK)

    # Weight counterparty selection so the "Acme" family and a handful of
    # other counterparties have noticeably more contracts than the long tail.
    cp_ids = counterparties["counterparty_id"].to_numpy()
    cp_weights = rng.uniform(0.5, 1.5, size=len(cp_ids))
    acme_ids = counterparties.loc[counterparties["name"].str.startswith("Acme"), "counterparty_id"]
    for aid in acme_ids:
        cp_weights[np.where(cp_ids == aid)[0][0]] *= 6.0
    cp_weights = cp_weights / cp_weights.sum()

    contract_types = weighted_choice(rng, ref.CONTRACT_TYPES, ref.CONTRACT_TYPE_WEIGHTS, N_CONTRACTS)
    statuses = weighted_choice(rng, ref.CONTRACT_STATUSES, ref.CONTRACT_STATUS_WEIGHTS, N_CONTRACTS)
    governing_laws = weighted_choice(rng, ref.GOVERNING_LAW_OPTIONS, ref.GOVERNING_LAW_WEIGHTS, N_CONTRACTS)
    currencies = weighted_choice(rng, ref.CURRENCIES, ref.CURRENCY_WEIGHTS, N_CONTRACTS)

    # ~7% of contracts get an expiration_date forced into the next 90 days.
    near_expiry_mask = rng.random(N_CONTRACTS) < 0.07

    rows = []
    for idx in range(N_CONTRACTS):
        n = idx + 1
        canonical_type = contract_types[idx]
        display_type = canonical_type
        if canonical_type in ref.SYNONYM_RATE and rng.random() < ref.SYNONYM_RATE[canonical_type]:
            display_type = rng.choice(ref.CONTRACT_TYPE_SYNONYMS[canonical_type])

        status = statuses[idx]
        is_unexecuted = status in ("Draft", "In Review")
        term_years = int(rng.choice([1, 2, 3, 5]))

        is_perpetual = canonical_type in ref.PERPETUAL_TYPES and rng.random() < ref.PERPETUAL_RATE
        if status == "Expired":
            is_perpetual = False  # can't have expired without an expiration date

        # Dates are generated per-status so the label and the date fields
        # never contradict each other (e.g. "Expired" always has a past
        # expiration_date; "Active" always has none or a future one).
        if is_unexecuted:
            effective_date = today + dt.timedelta(days=int(rng.integers(-30, 120)))
            execution_date = None
            expiration_date = None
        elif status in ("Expired", "Terminated"):
            if is_perpetual and status == "Terminated":
                expiration_date = None
                effective_date = random_dates(rng, window_start, today, 1)[0]
            else:
                expiration_date = today - dt.timedelta(days=int(rng.integers(1, 3 * 365)))
                effective_date = max(expiration_date - dt.timedelta(days=365 * term_years), window_start)
            execution_date = effective_date + dt.timedelta(days=int(rng.integers(0, 14)))
        else:  # Executed or Active
            effective_date = random_dates(rng, window_start, today, 1)[0]
            execution_date = effective_date + dt.timedelta(days=int(rng.integers(0, 14)))
            if is_perpetual:
                expiration_date = None
            elif near_expiry_mask[idx]:
                expiration_date = today + dt.timedelta(days=int(rng.integers(1, 91)))
            else:
                expiration_date = effective_date + dt.timedelta(days=365 * term_years)
                if expiration_date < today:
                    # still in force today: treat as having been renewed forward
                    expiration_date = today + dt.timedelta(days=int(rng.integers(30, 3 * 365)))

        auto_renew = bool(rng.random() < 0.35) and expiration_date is not None
        renewal_term_months = int(rng.choice(ref.RENEWAL_TERMS_MONTHS)) if auto_renew or rng.random() < 0.15 else None
        notice_period_days = int(rng.choice(ref.NOTICE_PERIODS)) if renewal_term_months is not None else None

        fy_basis = execution_date or effective_date
        total_value = float(np.round(rng.lognormal(mean=10.5, sigma=1.1), 2)) if rng.random() < 0.92 else None
        matter_id = rng.choice(matters["matter_id"].to_numpy()) if rng.random() < 0.4 else None

        created_at = dt.datetime.combine(effective_date, dt.time(hour=int(rng.integers(8, 18)))) - dt.timedelta(
            days=int(rng.integers(0, 5))
        )

        rows.append({
            "contract_id": f"CT-{n:06d}",
            "title": f"{display_type} - {fake.bs().title()}",
            "contract_type": display_type,
            "counterparty_id": rng.choice(cp_ids, p=cp_weights),
            "business_unit_id": rng.choice(business_units["business_unit_id"].to_numpy()),
            "owner_user_id": rng.choice(users["user_id"].to_numpy()),
            "matter_id": matter_id,
            "status": status,
            "governing_law": governing_laws[idx],
            "effective_date": effective_date,
            "execution_date": execution_date,
            "expiration_date": expiration_date,
            "total_value": total_value,
            "currency": currencies[idx],
            "auto_renew": auto_renew,
            "renewal_term_months": renewal_term_months,
            "notice_period_days": notice_period_days,
            "fiscal_year": fiscal_year(fy_basis),
            "created_at": created_at,
            "canonical_type": canonical_type,  # kept for clause generation, dropped before write
        })

    return pd.DataFrame(rows)


def build_clauses(rng: np.random.Generator, contracts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    clause_seq = 0
    for contract in contracts.itertuples():
        canonical_type = contract.canonical_type
        presence = ref.CLAUSE_PRESENCE_BY_TYPE.get(canonical_type, {})
        for clause_type, prob in presence.items():
            effective_prob = prob
            if (
                clause_type == "Limitation of Liability"
                and contract.governing_law == "California"
                and canonical_type in ref.LOL_DROP_TYPES
                and rng.random() < ref.LOL_DROP_RATE_IN_CA
            ):
                effective_prob = 0.0
            if rng.random() < effective_prob:
                clause_seq += 1
                rows.append({
                    "clause_id": f"CL-{clause_seq:06d}",
                    "contract_id": contract.contract_id,
                    "clause_type": clause_type,
                    "is_nonstandard": bool(rng.random() < ref.NONSTANDARD_RATE),
                    "summary": f"{clause_type} clause per standard playbook for {contract.contract_type}.",
                })
    return pd.DataFrame(rows)


def build_obligations(rng: np.random.Generator, fake: Faker, contracts: pd.DataFrame, users: pd.DataFrame) -> pd.DataFrame:
    today = dt.date.today()
    rows = []
    seq = 0
    user_ids = users["user_id"].to_numpy()
    for contract in contracts.itertuples():
        n_obligations = rng.poisson(2.0)
        base_date = contract.execution_date or contract.effective_date
        for _ in range(n_obligations):
            seq += 1
            obligation_type = weighted_choice(rng, ref.OBLIGATION_TYPES, ref.OBLIGATION_TYPE_WEIGHTS, 1)[0]
            due_date = base_date + dt.timedelta(days=int(rng.integers(-180, 540)))
            if due_date < today:
                status = weighted_choice(rng, ["Completed", "Overdue", "Waived"], [0.75, 0.18, 0.07], 1)[0]
            else:
                status = "Open"
            amount = float(np.round(rng.lognormal(mean=8.5, sigma=1.0), 2)) if obligation_type == "Payment" else None
            rows.append({
                "obligation_id": f"OB-{seq:06d}",
                "contract_id": contract.contract_id,
                "obligation_type": obligation_type,
                "description": f"{obligation_type} obligation: {fake.bs()}",
                "owner_user_id": rng.choice(user_ids),
                "due_date": due_date,
                "status": status,
                "amount": amount,
            })
    return pd.DataFrame(rows)


def build_renewals(rng: np.random.Generator, contracts: pd.DataFrame) -> pd.DataFrame:
    today = dt.date.today()
    rows = []
    seq = 0
    eligible = contracts[
        contracts["expiration_date"].notna()
        & (contracts["status"].isin(["Active", "Expired", "Terminated"]))
    ]
    sampled = eligible.sample(frac=0.85, random_state=int(rng.integers(0, 2**31 - 1)))
    for contract in sampled.itertuples():
        seq += 1
        renewal_date = contract.expiration_date - dt.timedelta(days=int(rng.integers(0, 30)))
        if renewal_date > today:
            renewal_date = today - dt.timedelta(days=int(rng.integers(1, 200)))
        if contract.auto_renew:
            renewal_type = weighted_choice(rng, ref.RENEWAL_TYPES, [0.7, 0.2, 0.1], 1)[0]
        else:
            renewal_type = weighted_choice(rng, ref.RENEWAL_TYPES, [0.1, 0.5, 0.4], 1)[0]
        new_expiration_date = None
        value_change = None
        if renewal_type != "Non-Renewed":
            term_months = contract.renewal_term_months
            term_months = int(term_months) if pd.notna(term_months) else 12
            new_expiration_date = contract.expiration_date + dt.timedelta(days=30 * term_months)
            value_change = float(np.round(rng.normal(loc=0, scale=5000), 2))
        rows.append({
            "renewal_id": f"REN-{seq:06d}",
            "contract_id": contract.contract_id,
            "renewal_date": renewal_date,
            "renewal_type": renewal_type,
            "new_expiration_date": new_expiration_date,
            "value_change": value_change,
        })
    return pd.DataFrame(rows)


def main() -> None:
    configure_logging()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    Faker.seed(ref.SEED)
    fake = Faker()
    rng = np.random.default_rng(ref.SEED)

    business_units = build_business_units(rng)
    users = build_users(rng, fake)
    counterparties = build_counterparties(rng, fake)
    matters = build_matters(rng, fake, users)
    contracts = build_contracts(rng, fake, counterparties, business_units, users, matters)
    clauses = build_clauses(rng, contracts)
    obligations = build_obligations(rng, fake, contracts, users)
    renewals = build_renewals(rng, contracts)

    contracts = contracts.drop(columns=["canonical_type"])
    contracts["renewal_term_months"] = contracts["renewal_term_months"].astype("Int64")
    contracts["notice_period_days"] = contracts["notice_period_days"].astype("Int64")

    tables = {
        "business_units": business_units,
        "users": users,
        "counterparties": counterparties,
        "matters": matters,
        "contracts": contracts,
        "clauses": clauses,
        "obligations": obligations,
        "renewals": renewals,
    }
    for name, df in tables.items():
        for col in MONEY_COLUMNS.get(name, []):
            df[col] = df[col].apply(to_money)
        path = os.path.join(OUTPUT_DIR, f"{name}.parquet")
        df.to_parquet(path, index=False)
        logger.info("%15s: %6d rows -> %s", name, len(df), path)


if __name__ == "__main__":
    main()
