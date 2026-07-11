"""Deterministic synthetic-data generator for the true_north Shinhan Finance
(consumer-lending) warehouse.

    uv run python -m generator.generate --scale {tiny,small,full} --seed 42

Everything is deterministic from ``--seed`` (a single numpy Generator). CSVs are written
to ``data/csv/`` (overwriting the header-only files) and then converted to Parquet in
``data/parquet/`` with an explicit Arrow schema derived from ``schema.py``.

Design goals (see data/TRAPS.md — every trap must actually hold in the output):
  1 snapshot double-counting (fact_loan_snapshots / ENR, active_loans)
  2 write-off wave 2025-06 -> NPL ratio "improves" 2025-07 with no real quality change
  3 restructuring campaign 2025-03..05 -> 30+ DPD understated unless is_restructured surfaced
  4 approval rate: cancelled excluded from the denominator
  5 partner_id NULL outside pos_partner channel
  6 bad telesales vintage 2025-01/02 -> ~2x FPD, invisible in calendar-month DPD
  7 VND unit trap (full dong, no /1000 scaling)
  8 bucket_at_due (collections) != month-end dpd_bucket (snapshots) — bucket migration
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from generator import schema
from generator.schema import (
    CANONICAL_PROVINCES,
    CHANNELS,
    DPD_BUCKETS,
    GENDERS,
    INCOME_BANDS,
    PARTNER_CATEGORIES,
    PRODUCT_KEYS,
    RISK_GRADES,
    SEGMENTS,
    TABLES,
    column_names,
)

ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = ROOT / "data" / "csv"
PARQUET_DIR = ROOT / "data" / "parquet"

HISTORY_START = date(2024, 1, 1)
HISTORY_END = date(2025, 12, 31)

WRITE_OFF_MONTH = date(2025, 6, 30)  # write-off wave (trap 2)
RESTRUCTURE_MONTHS = (date(2025, 3, 31), date(2025, 4, 30), date(2025, 5, 31))  # trap 3
BAD_VINTAGE_MONTHS = (date(2025, 1, 1), date(2025, 2, 1))  # trap 6, telesales only


# ---------------------------------------------------------------------------
# Scale presets
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Scale:
    name: str
    n_customers: int
    n_partners: int
    apps_per_day: float


SCALES = {
    "tiny": Scale("tiny", n_customers=150, n_partners=8, apps_per_day=3.0),
    "small": Scale("small", n_customers=4_000, n_partners=25, apps_per_day=25.0),
    "full": Scale("full", n_customers=8_000, n_partners=40, apps_per_day=41.0),
}


PRODUCT_DEFS = {
    "cash_loan": {"name": "iShinhan Cash Loan", "is_secured": False, "max_tenor_months": 36,
                  "amount_band": (5_000_000, 300_000_000), "rate_band": (0.28, 0.42)},
    "cd_installment": {"name": "Consumer Durable Installment", "is_secured": False, "max_tenor_months": 24,
                        "amount_band": (2_000_000, 60_000_000), "rate_band": (0.20, 0.35)},
    "two_wheeler_loan": {"name": "Two-Wheeler Loan", "is_secured": True, "max_tenor_months": 36,
                          "amount_band": (10_000_000, 80_000_000), "rate_band": (0.18, 0.28)},
    "credit_card_loan": {"name": "FIRST Credit Card Installment", "is_secured": False, "max_tenor_months": 12,
                          "amount_band": (1_000_000, 40_000_000), "rate_band": (0.25, 0.38)},
}

# Relative demand weight per product (drives application volume mix).
PRODUCT_WEIGHT = {
    "cash_loan": 0.42,
    "cd_installment": 0.30,
    "two_wheeler_loan": 0.13,
    "credit_card_loan": 0.15,
}

# Which channels each product is reachable through (weights).
PRODUCT_CHANNEL_WEIGHT = {
    "cash_loan": {"digital_app": 0.55, "dsa": 0.20, "telesales": 0.20, "pos_partner": 0.05},
    "cd_installment": {"pos_partner": 0.85, "digital_app": 0.10, "dsa": 0.05, "telesales": 0.0},
    "two_wheeler_loan": {"pos_partner": 0.70, "dsa": 0.25, "digital_app": 0.05, "telesales": 0.0},
    "credit_card_loan": {"digital_app": 0.50, "telesales": 0.30, "dsa": 0.15, "pos_partner": 0.05},
}

PARTNER_NAME_STEMS = {
    "electronics": ["Phong Vu", "The Gioi Dien May", "Dien May Xanh", "Nguyen Kim", "HC Home Center"],
    "mobile": ["The Gioi Di Dong", "FPT Shop", "CellphoneS", "Viettel Store"],
    "motorbike": ["Honda Head", "Yamaha Town", "Piaggio Store", "Motor Viet"],
    "appliances": ["Dien May Cho Lon", "Sieu Thi Dien May", "Home Center Appliances"],
}

PARTNER_CATEGORY_WEIGHT = {"electronics": 0.55, "mobile": 0.20, "motorbike": 0.15, "appliances": 0.10}


# ---------------------------------------------------------------------------
# Seasonality (trap-adjacent, not a trap itself): pre-Tet (Jan) and Sep peaks.
# ---------------------------------------------------------------------------
def _tet_windows() -> list[tuple[date, date]]:
    return [
        (date(2024, 1, 10), date(2024, 2, 8)),
        (date(2025, 1, 6), date(2025, 1, 28)),
    ]


def _day_multiplier(d: date) -> float:
    m = 1.0
    for s, e in _tet_windows():
        if s <= d <= e:
            m *= 1.9
    if date(2024, 9, 1) <= d <= date(2024, 9, 30) or date(2025, 9, 1) <= d <= date(2025, 9, 30):
        m *= 1.5  # back-to-school / September installment peak
    is_weekend = d.weekday() >= 5
    m *= 0.55 if is_weekend else 1.08  # lending is a weekday-heavy business (branches, DSAs)
    return m


def _month_end(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, 1)


def _month_ends(start: date, end: date) -> list[date]:
    out = []
    cur = _month_end(start)
    while cur <= end:
        out.append(cur)
        cur = _month_end(_add_months(cur, 1))
    return out


def _month_starts(start: date, end: date) -> list[date]:
    out = []
    cur = _month_start(start)
    while cur <= end:
        out.append(cur)
        cur = _add_months(cur, 1)
    return out


# ---------------------------------------------------------------------------
# Dimension builders
# ---------------------------------------------------------------------------
def build_customers(rng: np.random.Generator, scale: Scale) -> list[dict]:
    customers: list[dict] = []
    seg_p = np.array([0.72, 0.28])
    income_p = np.array([0.45, 0.40, 0.15])
    grade_p = np.array([0.10, 0.25, 0.35, 0.22, 0.08])  # A..E
    # Ensure >=1/3 in HCMC + Ha Noi.
    hub_provinces = ("Ho Chi Minh City", "Ha Noi")
    other_provinces = [p for p in CANONICAL_PROVINCES if p not in hub_provinces]
    for i in range(scale.n_customers):
        if rng.random() < 0.38:
            prov = hub_provinces[int(rng.integers(len(hub_provinces)))]
        else:
            prov = other_provinces[int(rng.integers(len(other_provinces)))]
        customers.append(
            {
                "customer_id": f"SH{i + 1:07d}",
                "segment": SEGMENTS[int(rng.choice(len(SEGMENTS), p=seg_p))],
                "province": prov,
                "income_band": INCOME_BANDS[int(rng.choice(len(INCOME_BANDS), p=income_p))],
                "risk_grade": RISK_GRADES[int(rng.choice(len(RISK_GRADES), p=grade_p))],
                "birth_year": int(rng.integers(1965, 2006)),
                "gender": GENDERS[int(rng.integers(len(GENDERS)))],
            }
        )
    return customers


def build_products() -> list[dict]:
    return [
        {"product_key": key, "name": d["name"], "is_secured": d["is_secured"], "max_tenor_months": d["max_tenor_months"]}
        for key, d in PRODUCT_DEFS.items()
    ]


def build_channels() -> list[dict]:
    names = {
        "digital_app": "iShinhan Digital App",
        "pos_partner": "POS Partner (in-store)",
        "dsa": "Direct Sales Agent",
        "telesales": "Telesales",
    }
    return [{"channel_key": c, "name": names[c]} for c in CHANNELS]


def build_partners(rng: np.random.Generator, scale: Scale) -> list[dict]:
    partners: list[dict] = []
    cats = list(PARTNER_CATEGORIES)
    cat_w = np.array([PARTNER_CATEGORY_WEIGHT[c] for c in cats])
    cat_w = cat_w / cat_w.sum()
    for i in range(scale.n_partners):
        cat = cats[int(rng.choice(len(cats), p=cat_w))]
        stem = PARTNER_NAME_STEMS[cat][int(rng.integers(len(PARTNER_NAME_STEMS[cat])))]
        prov = CANONICAL_PROVINCES[int(rng.integers(len(CANONICAL_PROVINCES)))]
        partners.append(
            {
                "partner_id": f"PTR{i + 1:03d}",
                "partner_name": f"{stem} {prov.split()[0]} #{i + 1}",
                "category": cat,
                "province": prov,
            }
        )
    return partners


# ---------------------------------------------------------------------------
# Fact generation
# ---------------------------------------------------------------------------
def _pick_product(rng: np.random.Generator) -> str:
    keys = list(PRODUCT_KEYS)
    w = np.array([PRODUCT_WEIGHT[k] for k in keys])
    w = w / w.sum()
    return keys[int(rng.choice(len(keys), p=w))]


def _pick_channel(rng: np.random.Generator, product_key: str) -> str:
    weights = PRODUCT_CHANNEL_WEIGHT[product_key]
    keys = [k for k, v in weights.items() if v > 0]
    w = np.array([weights[k] for k in keys])
    w = w / w.sum()
    return keys[int(rng.choice(len(keys), p=w))]


def _pick_partner(rng: np.random.Generator, partners: list[dict], category_pref: str | None) -> dict:
    """Pick a POS partner; top-5 electronics partners get concentration weight (trap: partner concentration)."""
    if category_pref is None:
        return partners[int(rng.integers(len(partners)))]
    pool = [p for p in partners if p["category"] == category_pref] or partners
    electronics_top5 = [p for p in partners if p["category"] == "electronics"][:5]
    if category_pref == "electronics" and electronics_top5 and rng.random() < 0.24:
        return electronics_top5[int(rng.integers(len(electronics_top5)))]
    return pool[int(rng.integers(len(pool)))]


def _category_for_product(product_key: str) -> str | None:
    return {
        "cd_installment": "electronics",
        "two_wheeler_loan": "motorbike",
        "credit_card_loan": None,
        "cash_loan": None,
    }.get(product_key)


def _approval_prob(risk_grade: str, channel: str) -> float:
    base = {"A": 0.92, "B": 0.82, "C": 0.68, "D": 0.50, "E": 0.30}[risk_grade]
    # telesales / dsa slightly looser underwriting narrative-wise, digital tightest.
    adj = {"digital_app": 0.0, "pos_partner": 0.02, "dsa": 0.03, "telesales": 0.05}[channel]
    return min(0.97, max(0.05, base + adj))


def generate_applications(rng: np.random.Generator, scale: Scale, customers: list[dict], partners: list[dict]):
    apps: list[dict] = []
    days = []
    d = HISTORY_START
    while d <= HISTORY_END:
        days.append(d)
        d += timedelta(days=1)

    app_counter = 0
    for d in days:
        exp = scale.apps_per_day * _day_multiplier(d)
        n = int(rng.poisson(max(0.0, exp)))
        for _ in range(n):
            app_counter += 1
            app_id = f"APP{app_counter:08d}"
            cust = customers[int(rng.integers(len(customers)))]
            product_key = _pick_product(rng)
            channel = _pick_channel(rng, product_key)
            partner_id = None
            if channel == "pos_partner":
                cat_pref = _category_for_product(product_key)
                partner = _pick_partner(rng, partners, cat_pref)
                partner_id = partner["partner_id"]

            band_lo, band_hi = PRODUCT_DEFS[product_key]["amount_band"]
            requested = int(round(float(np.exp(rng.uniform(np.log(band_lo), np.log(band_hi)))) / 100_000) * 100_000)

            risk_grade = cust["risk_grade"]
            ts = datetime.combine(d, datetime.min.time()) + timedelta(
                hours=int(rng.integers(8, 20)), minutes=int(rng.integers(0, 60))
            )
            decision_lag_hours = int(rng.integers(1, 72))
            decision_ts = ts + timedelta(hours=decision_lag_hours)

            r = rng.random()
            if r < 0.08:
                decision = "cancelled"
            else:
                approve_p = _approval_prob(risk_grade, channel)
                decision = "approved" if rng.random() < approve_p else "rejected"

            approved_amount = None
            if decision == "approved":
                take_frac = float(rng.uniform(0.75, 1.0))
                approved_amount = int(round(requested * take_frac / 100_000) * 100_000)

            apps.append(
                {
                    "app_id": app_id,
                    "ts": ts,
                    "customer_id": cust["customer_id"],
                    "product_key": product_key,
                    "channel": channel,
                    "partner_id": partner_id,
                    "requested_amount": requested,
                    "decision": decision,
                    "decision_ts": decision_ts,
                    "approved_amount": approved_amount,
                    "risk_grade": risk_grade,
                }
            )
    return apps


def generate_disbursements(rng: np.random.Generator, apps: list[dict]):
    disbursements: list[dict] = []
    loan_counter = 0
    for app in apps:
        if app["decision"] != "approved":
            continue
        # Small non-take-up gap: some approved apps never disburse.
        if rng.random() < 0.06:
            continue
        loan_counter += 1
        loan_id = f"LN{loan_counter:08d}"
        product_key = app["product_key"]
        rate_lo, rate_hi = PRODUCT_DEFS[product_key]["rate_band"]
        annual_rate = round(float(rng.uniform(rate_lo, rate_hi)), 4)
        max_tenor = PRODUCT_DEFS[product_key]["max_tenor_months"]
        min_tenor = 6 if product_key != "credit_card_loan" else 3
        tenor_months = int(rng.integers(min_tenor, max_tenor + 1))
        principal = app["approved_amount"]
        monthly_rate = annual_rate / 12.0
        if monthly_rate > 0:
            installment = principal * monthly_rate / (1 - (1 + monthly_rate) ** (-tenor_months))
        else:
            installment = principal / tenor_months
        disbursed_date = min(HISTORY_END, app["decision_ts"].date() + timedelta(days=int(rng.integers(0, 4))))

        disbursements.append(
            {
                "loan_id": loan_id,
                "app_id": app["app_id"],
                "disbursed_date": disbursed_date,
                "customer_id": app["customer_id"],
                "product_key": product_key,
                "channel": app["channel"],
                "partner_id": app["partner_id"],
                "principal": principal,
                "tenor_months": tenor_months,
                "annual_rate": annual_rate,
                "monthly_installment": int(round(installment / 1000) * 1000),
            }
        )
    return disbursements


def _dpd_bucket(dpd: int) -> str:
    if dpd <= 0:
        return "current"
    if dpd < 30:
        return "dpd_1_29"
    if dpd < 60:
        return "dpd_30_59"
    if dpd < 90:
        return "dpd_60_89"
    return "dpd_90_plus"


def _vintage_month(disbursed_date: date) -> date:
    return date(disbursed_date.year, disbursed_date.month, 1)


def generate_snapshots_and_collections(rng: np.random.Generator, disbursements: list[dict]):
    """Month-end loan snapshots + monthly collections.

    Delinquency trajectory per loan is a simple Markov-ish random walk on dpd, seeded by
    product risk (two-wheeler lowest, cash_loan highest — pattern 5) and boosted for the
    bad 2025-01/02 telesales vintage (pattern 3 / trap 6).
    """
    snapshots: list[dict] = []
    collections: list[dict] = []

    product_risk = {"two_wheeler_loan": 0.55, "cd_installment": 0.85, "credit_card_loan": 1.05, "cash_loan": 1.25}

    for loan in disbursements:
        disb_date = loan["disbursed_date"]
        first_month_end = _month_end(disb_date)
        month_ends = [m for m in _month_ends(first_month_end, HISTORY_END)]
        if not month_ends:
            continue

        is_bad_vintage = (
            loan["channel"] == "telesales"
            and _vintage_month(disb_date) in BAD_VINTAGE_MONTHS
        )
        risk_mult = product_risk[loan["product_key"]] * (2.0 if is_bad_vintage else 1.0)

        principal = loan["principal"]
        tenor = loan["tenor_months"]
        installment = loan["monthly_installment"]
        outstanding = float(principal)
        dpd = 0
        prior_dpd = 0
        status = "active"
        written_off = False
        restructured = False
        months_elapsed = 0

        for m_end in month_ends:
            months_elapsed += 1
            if written_off:
                break  # trap 2 mechanism: no rows after write-off month

            # amortize outstanding balance roughly linearly with a floor at 0
            if months_elapsed >= tenor:
                outstanding = 0.0
            else:
                outstanding = max(0.0, principal * (1 - months_elapsed / tenor))

            if outstanding <= 0:
                status = "closed"
                snapshots.append(
                    {
                        "snapshot_month": m_end,
                        "loan_id": loan["loan_id"],
                        "outstanding_principal": 0,
                        "dpd": 0,
                        "dpd_bucket": "current",
                        "status": "closed",
                        "is_restructured": restructured,
                    }
                )
                break

            # delinquency random walk
            delinquency_p = 0.10 * risk_mult
            cure_p = 0.28 / max(risk_mult, 0.4)
            if rng.random() < delinquency_p:
                dpd += int(rng.integers(15, 45))
            elif dpd > 0 and rng.random() < cure_p:
                dpd = max(0, dpd - int(rng.integers(20, 40)))
            else:
                dpd += int(rng.integers(0, 3)) if dpd > 0 else 0

            dpd = max(0, dpd)

            # Restructuring campaign 2025-03..05: ~4% of 30-89 DPD loans get reset (pattern 2/trap 3).
            if m_end in RESTRUCTURE_MONTHS and 30 <= dpd < 90 and rng.random() < 0.04:
                dpd = 0
                restructured = True

            # Write-off wave 2025-06: loans that are dpd_90_plus at that snapshot write off (pattern 1/trap 2).
            if m_end == WRITE_OFF_MONTH and dpd >= 90 and rng.random() < 0.55:
                snapshots.append(
                    {
                        "snapshot_month": m_end,
                        "loan_id": loan["loan_id"],
                        "outstanding_principal": int(round(outstanding)),
                        "dpd": dpd,
                        "dpd_bucket": _dpd_bucket(dpd),
                        "status": "written_off",
                        "is_restructured": restructured,
                    }
                )
                written_off = True
                status = "written_off"
                # collections row for this month still recorded below before break check next loop
            else:
                snapshots.append(
                    {
                        "snapshot_month": m_end,
                        "loan_id": loan["loan_id"],
                        "outstanding_principal": int(round(outstanding)),
                        "dpd": dpd,
                        "dpd_bucket": _dpd_bucket(dpd),
                        "status": "active",
                        "is_restructured": restructured,
                    }
                )

            # ---- Collections for this month ----
            # bucket_at_due = bucket implied by dpd at the START of the month (trap 8):
            # the PRIOR snapshot's dpd (0 for the first month).
            bucket_at_due = _dpd_bucket(prior_dpd)
            amount_due = installment if not written_off else 0
            if amount_due > 0:
                collect_p = {"current": 0.97, "dpd_1_29": 0.85, "dpd_30_59": 0.55, "dpd_60_89": 0.30, "dpd_90_plus": 0.10}[bucket_at_due]
                collected = amount_due * float(rng.uniform(max(0.0, collect_p - 0.1), min(1.0, collect_p + 0.1)))
                collections.append(
                    {
                        "month": _month_start(m_end),
                        "loan_id": loan["loan_id"],
                        "amount_due": int(round(amount_due)),
                        "amount_collected": int(round(max(0.0, collected))),
                        "bucket_at_due": bucket_at_due,
                    }
                )

            prior_dpd = dpd

    return snapshots, collections


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
_ARROW = {
    "string": pa.string(),
    "int32": pa.int32(),
    "int64": pa.int64(),
    "double": pa.float64(),
    "date": pa.date32(),
    "timestamp": pa.timestamp("us"),
    "bool": pa.bool_(),
}


def _arrow_schema(table: str) -> pa.schema:
    return pa.schema([(c.name, _ARROW[c.dtype]) for c in TABLES[table]])


def _csv_cell(value, dtype: str) -> str:
    if value is None:
        return ""
    if dtype in ("date", "timestamp"):
        return value.isoformat() if not isinstance(value, str) else value
    if dtype == "bool":
        return "true" if value else "false"
    return str(value)


def write_csv(table: str, rows: list[dict]) -> Path:
    cols = column_names(table)
    dtypes = {c.name: c.dtype for c in TABLES[table]}
    path = CSV_DIR / f"{table}.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for row in rows:
            w.writerow([_csv_cell(row.get(c), dtypes[c]) for c in cols])
    return path


def write_parquet(table: str, rows: list[dict]) -> Path:
    cols = column_names(table)
    arrays = {c: [row.get(c) for row in rows] for c in cols}
    pa_table = pa.table(arrays, schema=_arrow_schema(table))
    path = PARQUET_DIR / f"{table}.parquet"
    pq.write_table(pa_table, path)
    return path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def generate(scale_name: str, seed: int) -> dict[str, list[dict]]:
    scale = SCALES[scale_name]
    rng = np.random.default_rng(seed)

    CSV_DIR.mkdir(parents=True, exist_ok=True)
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)

    customers = build_customers(rng, scale)
    products = build_products()
    channels = build_channels()
    partners = build_partners(rng, scale)

    apps = generate_applications(rng, scale, customers, partners)
    disbursements = generate_disbursements(rng, apps)
    snapshots, collections = generate_snapshots_and_collections(rng, disbursements)

    data = {
        "dim_customer": customers,
        "dim_product": products,
        "dim_channel": channels,
        "dim_partner": partners,
        "fact_applications": apps,
        "fact_disbursements": disbursements,
        "fact_loan_snapshots": snapshots,
        "fact_collections": collections,
    }
    for table, rows in data.items():
        write_csv(table, rows)
        write_parquet(table, rows)
    return data


def _summary(data: dict[str, list[dict]]) -> None:
    print("\n=== Generation summary ===")
    for table, rows in data.items():
        line = f"{table:22s} rows={len(rows):>10,}"
        for col in ("ts", "disbursed_date", "snapshot_month", "month", "decision_ts"):
            if rows and col in rows[0]:
                vals = [r[col] for r in rows if r.get(col) is not None]
                if vals:
                    lo = min(vals)
                    hi = max(vals)
                    lo = lo.date() if hasattr(lo, "date") else lo
                    hi = hi.date() if hasattr(hi, "date") else hi
                    line += f"  {col}[{lo}..{hi}]"
                break
        print(line)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the true_north Shinhan Finance demo dataset.")
    ap.add_argument("--scale", choices=list(SCALES), default="small")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print(f"Generating scale={args.scale} seed={args.seed} ...")
    data = generate(args.scale, args.seed)
    _summary(data)
    print(f"\nCSV   -> {CSV_DIR}")
    print(f"Parquet -> {PARQUET_DIR}")


if __name__ == "__main__":
    main()
