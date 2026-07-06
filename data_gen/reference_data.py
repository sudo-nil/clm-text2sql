"""Static reference lists / weights used by the synthetic data generator.

Keeping these in one place makes the deliberate "traps" (fuzzy contract
types, ALL-CAPS legal names, clause-presence correlation) easy to audit.
"""

SEED = 42

# --- business units --------------------------------------------------------
DEPARTMENTS = [
    "Sales", "Engineering", "Procurement", "HR", "Marketing", "Finance",
    "IT", "Legal", "Operations", "Customer Success", "Product", "R&D",
    "Facilities", "Compliance",
]
REGIONS = ["NA", "EMEA", "APAC"]

# --- users ------------------------------------------------------------------
USER_ROLES = ["Legal Counsel", "Contract Manager", "Paralegal", "Procurement Lead"]
USER_ROLE_WEIGHTS = [0.20, 0.30, 0.25, 0.25]

# --- counterparties -----------------------------------------------------------
# entity_type -> (legal suffix used in legal_name, countries it's plausible for)
ENTITY_TYPES = {
    "LLC": {"suffix": "LLC", "countries": ["United States"]},
    "Inc.": {"suffix": "INC.", "countries": ["United States"]},
    "GmbH": {"suffix": "GMBH", "countries": ["Germany"]},
    "Ltd.": {"suffix": "LTD.", "countries": ["United Kingdom", "Canada", "Australia", "India"]},
    "PLC": {"suffix": "PLC", "countries": ["United Kingdom"]},
    "S.A.": {"suffix": "S.A.", "countries": ["France", "Spain", "Switzerland"]},
}
ENTITY_TYPE_NAMES = list(ENTITY_TYPES.keys())
ENTITY_TYPE_WEIGHTS = [0.32, 0.18, 0.10, 0.20, 0.08, 0.12]

US_STATES = [
    "California", "Delaware", "New York", "Texas", "Washington", "Illinois",
    "Massachusetts", "Colorado", "Georgia", "Florida",
]

INDUSTRIES = [
    "Technology", "Manufacturing", "Healthcare", "Financial Services",
    "Retail", "Energy", "Telecommunications", "Logistics", "Media",
    "Pharmaceuticals",
]

RISK_TIERS = ["Low", "Medium", "High"]
RISK_TIER_WEIGHTS = [0.50, 0.35, 0.15]

# Guaranteed "Acme" brand family so the counterparty-normalization trap
# deterministically returns multiple matching entities/contracts.
ACME_COUNTERPARTIES = [
    {"name": "Acme Global", "entity_type": "LLC", "country": "United States"},
    {"name": "Acme Solutions", "entity_type": "Inc.", "country": "United States"},
    {"name": "Acme Europe", "entity_type": "GmbH", "country": "Germany"},
]

# --- contracts ----------------------------------------------------------------
# canonical contract_type -> weight, plus a minority of rows stored under a
# realistic synonym instead of the canonical label (the "fuzzy type" trap).
CONTRACT_TYPES = [
    "NDA", "SOW", "MSA", "SaaS Subscription", "DPA", "License",
    "Reseller", "Employment", "Lease", "Amendment",
]
CONTRACT_TYPE_WEIGHTS = [0.28, 0.20, 0.15, 0.14, 0.05, 0.07, 0.03, 0.03, 0.03, 0.02]

CONTRACT_TYPE_SYNONYMS = {
    "NDA": ["Mutual NDA", "Confidentiality Agreement"],
}
# fraction of rows of a type that get rewritten to a synonym label
SYNONYM_RATE = {"NDA": 0.18}

CONTRACT_STATUSES = ["Draft", "In Review", "Executed", "Active", "Expired", "Terminated"]
CONTRACT_STATUS_WEIGHTS = [0.08, 0.07, 0.10, 0.55, 0.12, 0.08]

GOVERNING_LAW_OPTIONS = [
    "California", "Delaware", "New York", "Texas", "Washington",
    "England & Wales", "Germany", "Ireland", "Singapore",
]
GOVERNING_LAW_WEIGHTS = [0.22, 0.18, 0.14, 0.08, 0.06, 0.14, 0.08, 0.05, 0.05]

CURRENCIES = ["USD", "EUR", "GBP"]
CURRENCY_WEIGHTS = [0.80, 0.12, 0.08]

NOTICE_PERIODS = [30, 60, 90]
RENEWAL_TERMS_MONTHS = [12, 24, 36]

# contract types that are conventionally perpetual / no fixed expiration
PERPETUAL_TYPES = {"NDA", "Employment"}
PERPETUAL_RATE = 0.35  # share of those types with no expiration_date

# --- clauses --------------------------------------------------------------
CLAUSE_TYPES = [
    "Limitation of Liability", "Indemnification", "Confidentiality",
    "Termination for Convenience", "Auto-Renewal", "Governing Law",
    "Data Protection", "Non-Compete", "Assignment", "Force Majeure",
    "Arbitration", "Most Favored Nation", "Exclusivity",
]

# contract_type -> {clause_type: probability of presence}
CLAUSE_PRESENCE_BY_TYPE = {
    "MSA": {
        "Limitation of Liability": 0.92, "Indemnification": 0.90,
        "Confidentiality": 0.70, "Termination for Convenience": 0.65,
        "Governing Law": 0.80, "Assignment": 0.55, "Force Majeure": 0.45,
        "Auto-Renewal": 0.25, "Arbitration": 0.20,
    },
    "SOW": {
        "Confidentiality": 0.35, "Governing Law": 0.30,
        "Limitation of Liability": 0.20, "Indemnification": 0.15,
    },
    "NDA": {
        "Confidentiality": 0.97, "Governing Law": 0.55,
        "Non-Compete": 0.08, "Limitation of Liability": 0.04,
        "Indemnification": 0.03,
    },
    "SaaS Subscription": {
        "Auto-Renewal": 0.70, "Limitation of Liability": 0.85,
        "Data Protection": 0.75, "Termination for Convenience": 0.50,
        "Governing Law": 0.75, "Indemnification": 0.55,
    },
    "DPA": {
        "Data Protection": 0.98, "Confidentiality": 0.60,
        "Governing Law": 0.55, "Indemnification": 0.35,
    },
    "License": {
        "Limitation of Liability": 0.80, "Indemnification": 0.65,
        "Exclusivity": 0.30, "Most Favored Nation": 0.15,
        "Governing Law": 0.60, "Assignment": 0.30,
    },
    "Reseller": {
        "Exclusivity": 0.45, "Most Favored Nation": 0.25,
        "Termination for Convenience": 0.55, "Indemnification": 0.60,
        "Governing Law": 0.50,
    },
    "Employment": {
        "Non-Compete": 0.70, "Confidentiality": 0.85, "Governing Law": 0.60,
    },
    "Lease": {
        "Force Majeure": 0.60, "Governing Law": 0.65, "Assignment": 0.40,
    },
    "Amendment": {
        "Governing Law": 0.20,
    },
}

# Types for which a CA-governed contract deliberately drops the
# Limitation of Liability clause at an elevated rate (the anti-join trap).
LOL_DROP_TYPES = {"MSA", "SaaS Subscription", "License", "Reseller", "DPA"}
LOL_DROP_RATE_IN_CA = 0.45

NONSTANDARD_RATE = 0.08

# --- obligations ------------------------------------------------------------
OBLIGATION_TYPES = ["Payment", "Deliverable", "Reporting", "Renewal Notice", "Audit"]
OBLIGATION_TYPE_WEIGHTS = [0.35, 0.30, 0.15, 0.12, 0.08]
OBLIGATION_STATUSES = ["Open", "Completed", "Overdue", "Waived"]

# --- renewals -----------------------------------------------------------------
RENEWAL_TYPES = ["Auto", "Negotiated", "Non-Renewed"]

# --- matters ------------------------------------------------------------------
MATTER_TYPES = ["Vendor Onboarding", "M&A", "Litigation", "Financing", "Real Estate"]
MATTER_STATUSES = ["Open", "Closed"]
MATTER_STATUS_WEIGHTS = [0.55, 0.45]
