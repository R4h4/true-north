"""Single source of truth for the true_north Shinhan Finance (consumer-lending) schema.

Every table is a list of Column(name, dtype, description) in physical order. Both the
headers-only CSV writer and the data generator (``generate.py``) import ``TABLES`` from
here — column lists are never duplicated elsewhere.

``dtype`` is a logical type string consumed by the parquet writer to build an explicit
Arrow schema:

    string      -> pa.string()
    int32       -> pa.int32()   (nullable ints allowed; nulls encoded as Arrow nulls)
    int64       -> pa.int64()
    double      -> pa.float64()
    date        -> pa.date32()  (calendar date, no time)
    timestamp   -> pa.timestamp("us")
    bool        -> pa.bool_()

Amounts are VND stored as ``int64`` in full đồng (no thousands scaling) — see
data/TRAPS.md trap 7.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    dtype: str
    description: str


# ---------------------------------------------------------------------------
# Canonical value vocabularies
# ---------------------------------------------------------------------------

SEGMENTS = ("mass", "emerging_affluent")
INCOME_BANDS = ("under_10m", "10m_to_25m", "over_25m")
RISK_GRADES = ("A", "B", "C", "D", "E")
GENDERS = ("male", "female")

# Reused canonical province vocabulary (same long-form convention as the retail
# tenant). At least 1/3 of dim_customer rows are HCMC + Ha Noi (spec).
CANONICAL_PROVINCES = (
    "Ho Chi Minh City",
    "Ha Noi",
    "Da Nang",
    "Binh Duong",
    "Dong Nai",
    "Can Tho",
    "Hai Phong",
    "Khanh Hoa",
    "Long An",
    "Thanh Hoa",
    "Nghe An",
    "Bac Ninh",
)

PRODUCT_KEYS = ("cash_loan", "cd_installment", "two_wheeler_loan", "credit_card_loan")

CHANNELS = ("digital_app", "pos_partner", "dsa", "telesales")

PARTNER_CATEGORIES = ("electronics", "mobile", "motorbike", "appliances")

APPLICATION_DECISIONS = ("approved", "rejected", "cancelled")

DPD_BUCKETS = ("current", "dpd_1_29", "dpd_30_59", "dpd_60_89", "dpd_90_plus")

LOAN_STATUSES = ("active", "closed", "written_off")


# ---------------------------------------------------------------------------
# Table definitions (physical column order)
# ---------------------------------------------------------------------------

TABLES: dict[str, list[Column]] = {
    "dim_customer": [
        Column("customer_id", "string", "Surrogate customer key, e.g. 'SH0000123'."),
        Column("segment", "string", f"Customer segment, one of {SEGMENTS}."),
        Column("province", "string", "Canonical province name (see CANONICAL_PROVINCES)."),
        Column("income_band", "string", f"Self-reported monthly income band, one of {INCOME_BANDS}."),
        Column("risk_grade", "string", f"Risk grade AT ORIGINATION (customer-level), one of {RISK_GRADES}."),
        Column("birth_year", "int32", "Year of birth."),
        Column("gender", "string", f"One of {GENDERS}."),
    ],
    "dim_product": [
        Column("product_key", "string", f"Product key, one of {PRODUCT_KEYS}."),
        Column("name", "string", "Human-readable product name."),
        Column("is_secured", "bool", "Whether the product is collateral-secured (true only for two_wheeler_loan)."),
        Column("max_tenor_months", "int32", "Maximum tenor offered for the product, in months."),
    ],
    "dim_channel": [
        Column("channel_key", "string", f"Channel key, one of {CHANNELS}."),
        Column("name", "string", "Human-readable channel name."),
    ],
    "dim_partner": [
        Column("partner_id", "string", "Surrogate POS partner key, e.g. 'PTR001'."),
        Column("partner_name", "string", "Partner store/chain name."),
        Column("category", "string", f"Partner category, one of {PARTNER_CATEGORIES}."),
        Column("province", "string", "Partner's canonical province."),
    ],
    "fact_applications": [
        Column("app_id", "string", "Surrogate application key, e.g. 'APP0000123'."),
        Column("ts", "timestamp", "Application timestamp (local time, us precision)."),
        Column("customer_id", "string", "FK to dim_customer."),
        Column("product_key", "string", "FK to dim_product."),
        Column("channel", "string", "FK to dim_channel.channel_key."),
        Column("partner_id", "string", "FK to dim_partner; NULL for every non-pos_partner channel (trap 5)."),
        Column("requested_amount", "int64", "Amount requested by the applicant, VND."),
        Column("decision", "string", f"One of {APPLICATION_DECISIONS}."),
        Column("decision_ts", "timestamp", "Timestamp the decision was made."),
        Column("approved_amount", "int64", "Approved amount, VND; NULL unless decision = 'approved'."),
        Column("risk_grade", "string", f"Risk grade assigned at underwriting for this application, one of {RISK_GRADES}."),
    ],
    "fact_disbursements": [
        Column("loan_id", "string", "Surrogate loan key, e.g. 'LN0000123'."),
        Column("app_id", "string", "FK to fact_applications.app_id (the approved application that funded this loan)."),
        Column("disbursed_date", "date", "Date the loan was disbursed."),
        Column("customer_id", "string", "FK to dim_customer."),
        Column("product_key", "string", "FK to dim_product."),
        Column("channel", "string", "FK to dim_channel.channel_key (carried from the application)."),
        Column("partner_id", "string", "FK to dim_partner; NULL for every non-pos_partner channel (trap 5)."),
        Column("principal", "int64", "Disbursed principal, VND."),
        Column("tenor_months", "int32", "Loan tenor in months."),
        Column("annual_rate", "double", "Annual interest rate (decimal, e.g. 0.32 for 32%)."),
        Column("monthly_installment", "int64", "Scheduled monthly installment, VND."),
    ],
    "fact_loan_snapshots": [
        Column("snapshot_month", "date", "Month-end snapshot date (last calendar day of the month)."),
        Column("loan_id", "string", "FK to fact_disbursements.loan_id."),
        Column("outstanding_principal", "int64", "Outstanding principal balance at snapshot, VND."),
        Column("dpd", "int32", "Days past due at snapshot (integer, >= 0)."),
        Column("dpd_bucket", "string", f"One of {DPD_BUCKETS}, derived from dpd."),
        Column("status", "string", f"One of {LOAN_STATUSES}. Written-off loans have no rows in months after write-off (trap 2)."),
        Column("is_restructured", "bool", "Whether the loan was restructured (DPD reset to 0) as of this snapshot."),
    ],
    "fact_collections": [
        Column("month", "date", "Collections month (first calendar day of the month)."),
        Column("loan_id", "string", "FK to fact_disbursements.loan_id."),
        Column("amount_due", "int64", "Scheduled amount due in the month, VND."),
        Column("amount_collected", "int64", "Amount actually collected in the month, VND."),
        Column(
            "bucket_at_due",
            "string",
            f"DPD bucket as of the START of the month (one of {DPD_BUCKETS}) — NOT the "
            "snapshot's month-end bucket; the two differ by bucket migration during the "
            "month (trap 8).",
        ),
    ],
}


def column_names(table: str) -> list[str]:
    """Ordered column names for a table."""
    return [c.name for c in TABLES[table]]


def table_names() -> list[str]:
    return list(TABLES.keys())
