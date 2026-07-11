"""Deterministic synthetic-data generator for the true_north (Phong Vu) warehouse.

    uv run python -m generator.generate --scale {tiny,small,full} --seed 42

Everything is deterministic from ``--seed`` (a single numpy Generator plus a seeded Faker).
CSVs are written to ``data/csv/`` (overwriting the header-only files) and then converted to
Parquet in ``data/parquet/`` with an explicit Arrow schema derived from ``schema.py``.

Design goals (see data/TRAPS.md — every trap must actually hold in the output):
  1 metric polysemy (gross/net, item/value, retail/B2B)
  2 separate returns table, category-dependent return rate (components high, accessories low)
  3 nullable customer_id (B2B always set, walk-in retail often NULL)
  4 same-store comparability (>=2 stores open mid-history, 1 closes)
  5 weekly inventory snapshot grain
  6 inventory staleness (latest snapshot ~1 week behind latest sales)
  7 value-format (snake_case channels, canonical provinces)
  8 unit trap (VND ints; list vs transacted amounts)
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
from faker import Faker

from generator import schema
from generator.schema import (
    CANONICAL_PROVINCES,
    CATEGORIES,
    REGION_BY_PROVINCE,
    TABLES,
    column_names,
)

ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = ROOT / "data" / "csv"
PARQUET_DIR = ROOT / "data" / "parquet"

# History window: ~2 years ending at a fixed date (deterministic, not "today").
HISTORY_END = date(2025, 12, 31)
HISTORY_START = date(2024, 1, 1)


# ---------------------------------------------------------------------------
# Scale presets
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Scale:
    name: str
    n_stores: int
    n_skus: int
    n_customers: int
    # avg retail baskets per store per day (drives total sales-line volume)
    retail_baskets_per_store_day: float


SCALES = {
    "tiny": Scale("tiny", n_stores=4, n_skus=40, n_customers=200, retail_baskets_per_store_day=1.5),
    "small": Scale("small", n_stores=12, n_skus=180, n_customers=6_000, retail_baskets_per_store_day=6.0),
    "full": Scale("full", n_stores=30, n_skus=1_500, n_customers=120_000, retail_baskets_per_store_day=45.0),
}


# ---------------------------------------------------------------------------
# Brands & price bands (VND). Ranges chosen to be realistic per category.
# unit_cost is derived from list_price via a category margin band.
# ---------------------------------------------------------------------------
CATEGORY_BRANDS = {
    "Laptop": ["Asus", "Dell", "HP", "Lenovo", "Acer", "MSI", "Apple", "LG"],
    "Desktop PC": ["Asus", "Dell", "HP", "Lenovo", "MSI", "Phong Vu Build"],
    "Monitor": ["Dell", "LG", "Samsung", "Asus", "ViewSonic", "Gigabyte"],
    "PC Component": ["Intel", "AMD", "Nvidia", "Asus", "Gigabyte", "MSI", "Kingston", "Corsair", "Samsung", "WD"],
    "Gaming Gear": ["Logitech", "Razer", "Corsair", "SteelSeries", "Asus", "HyperX"],
    "Accessory": ["Logitech", "Anker", "Ugreen", "Microsoft", "Baseus"],
    "Phone & Tablet": ["Apple", "Samsung", "Xiaomi", "Oppo"],
    "Office Equipment": ["Canon", "HP", "Epson", "Brother"],
    "Networking": ["TP-Link", "Asus", "Ubiquiti", "Cisco"],
    "Home Appliance": ["Xiaomi", "Philips", "Samsung", "LG"],
}

# (list_price low, list_price high) in VND per category.
CATEGORY_PRICE_BAND = {
    "Laptop": (12_000_000, 60_000_000),
    "Desktop PC": (10_000_000, 80_000_000),
    "Monitor": (2_500_000, 25_000_000),
    "PC Component": (1_200_000, 45_000_000),
    "Gaming Gear": (500_000, 8_000_000),
    "Accessory": (150_000, 3_500_000),
    "Phone & Tablet": (4_000_000, 45_000_000),
    "Office Equipment": (2_000_000, 30_000_000),
    "Networking": (400_000, 20_000_000),
    "Home Appliance": (1_500_000, 25_000_000),
}

# Gross margin band (on list price) per category -> derives unit_cost.
CATEGORY_MARGIN = {
    "Laptop": (0.06, 0.12),
    "Desktop PC": (0.08, 0.16),
    "Monitor": (0.10, 0.20),
    "PC Component": (0.05, 0.11),
    "Gaming Gear": (0.20, 0.38),
    "Accessory": (0.25, 0.45),
    "Phone & Tablet": (0.04, 0.09),
    "Office Equipment": (0.12, 0.22),
    "Networking": (0.15, 0.30),
    "Home Appliance": (0.12, 0.25),
}

# Trap 2: category-dependent return rate (fraction of sold lines returned).
CATEGORY_RETURN_RATE = {
    "PC Component": 0.11,     # high: DOA / incompatible
    "Desktop PC": 0.06,
    "Laptop": 0.045,
    "Phone & Tablet": 0.05,
    "Monitor": 0.04,
    "Gaming Gear": 0.03,
    "Office Equipment": 0.03,
    "Networking": 0.03,
    "Home Appliance": 0.035,
    "Accessory": 0.012,       # low
}

# Relative popularity weight per category (retail demand mix).
CATEGORY_WEIGHT = {
    "Laptop": 0.22,
    "Accessory": 0.20,
    "PC Component": 0.14,
    "Monitor": 0.10,
    "Gaming Gear": 0.10,
    "Phone & Tablet": 0.09,
    "Desktop PC": 0.05,
    "Office Equipment": 0.04,
    "Networking": 0.03,
    "Home Appliance": 0.03,
}


# ---------------------------------------------------------------------------
# Seasonality
# ---------------------------------------------------------------------------
def _tet_windows() -> list[tuple[date, date]]:
    # Approximate Lunar New Year peak windows for the history years.
    return [
        (date(2024, 1, 25), date(2024, 2, 12)),
        (date(2025, 1, 18), date(2025, 2, 4)),
    ]


def _event_windows() -> list[tuple[date, date, float]]:
    """(start, end, multiplier) shopping-event windows besides Tet."""
    w: list[tuple[date, date, float]] = []
    for y in (2024, 2025):
        w.append((date(y, 11, 8), date(y, 11, 12), 2.3))    # 11.11
        w.append((date(y, 11, 18), date(y, 12, 1), 1.8))     # Black Friday window
        w.append((date(y, 12, 10), date(y, 12, 13), 2.1))    # 12.12
        w.append((date(y, 7, 15), date(y, 9, 15), 1.5))      # back-to-school (laptop season)
    return w


def _day_multiplier(d: date, channel_is_b2b: bool) -> float:
    """Seasonality + weekly pattern multiplier for a given day."""
    m = 1.0
    # Tet spike
    for s, e in _tet_windows():
        if s <= d <= e:
            m *= 2.6
    # Other events
    for s, e, mult in _event_windows():
        if s <= d <= e:
            m *= mult
    # Weekly pattern: retail lifts on weekends; B2B lifts on weekdays.
    is_weekend = d.weekday() >= 5
    if channel_is_b2b:
        m *= 0.6 if is_weekend else 1.15
    else:
        m *= 1.35 if is_weekend else 0.9
    return m


def _online_share(d: date) -> float:
    """Trap-realism: online (web+app) share of retail grows over the 2 years."""
    frac = (d - HISTORY_START).days / max(1, (HISTORY_END - HISTORY_START).days)
    return 0.20 + 0.25 * frac  # 20% -> 45%


# ---------------------------------------------------------------------------
# Dimension builders
# ---------------------------------------------------------------------------
def _to_iso(d: date | None) -> str:
    return "" if d is None else d.isoformat()


def build_stores(rng: np.random.Generator, scale: Scale) -> list[dict]:
    """Build dim_store. Trap 4: >=2 stores open mid-history, exactly 1 closes."""
    stores: list[dict] = []
    provinces = list(CANONICAL_PROVINCES)
    # Ensure geographic spread; sample provinces with replacement beyond the canonical count.
    for i in range(scale.n_stores):
        prov = provinces[i] if i < len(provinces) else provinces[rng.integers(len(provinces))]
        region = REGION_BY_PROVINCE[prov]
        # Store 0 is a flagship; a few flagships in bigger scales; one pure-online store.
        if i == scale.n_stores - 1:
            fmt = "online"
        elif i == 0 or (scale.n_stores >= 12 and i in (1, 6)):
            fmt = "flagship_showroom"
        else:
            fmt = "showroom"

        opened = HISTORY_START - timedelta(days=int(rng.integers(200, 1600)))
        closed: date | None = None
        stores.append(
            {
                "store_id": f"S{i + 1:03d}",
                "store_name": f"Phong Vu {prov}"
                + ("" if i < len(provinces) else f" {i + 1}")
                + (" Flagship" if fmt == "flagship_showroom" else (" Online" if fmt == "online" else "")),
                "format": fmt,
                "region": region,
                "province": prov,
                "opened_date": opened,
                "closed_date": closed,
                "selling_area_sqm": (
                    0 if fmt == "online"
                    else int(rng.integers(800, 2200)) if fmt == "flagship_showroom"
                    else int(rng.integers(150, 700))
                ),
            }
        )

    # Trap 4: force two stores to open mid-history and one to close mid-history.
    # Pick distinct showroom stores (not the online one).
    showroom_idx = [i for i, s in enumerate(stores) if s["format"] != "online"]
    # Two mid-history openings.
    for j, days_in in enumerate((150, 400)):
        idx = showroom_idx[j % len(showroom_idx)]
        stores[idx]["opened_date"] = HISTORY_START + timedelta(days=days_in)
    # One mid-history closure (a different store, opened before history start).
    close_idx = showroom_idx[-1]
    stores[close_idx]["opened_date"] = HISTORY_START - timedelta(days=500)
    stores[close_idx]["closed_date"] = HISTORY_START + timedelta(days=520)
    return stores


def build_suppliers(rng: np.random.Generator, n: int = 12) -> list[str]:
    return [f"SUP{i + 1:02d}" for i in range(n)]


def build_skus(rng: np.random.Generator, scale: Scale, suppliers: list[str]) -> list[dict]:
    skus: list[dict] = []
    cats = list(CATEGORIES.keys())
    cat_weights = np.array([CATEGORY_WEIGHT[c] for c in cats])
    cat_weights = cat_weights / cat_weights.sum()
    for i in range(scale.n_skus):
        cat = cats[int(rng.choice(len(cats), p=cat_weights))]
        sub = CATEGORIES[cat][int(rng.integers(len(CATEGORIES[cat])))]
        brand = CATEGORY_BRANDS[cat][int(rng.integers(len(CATEGORY_BRANDS[cat])))]
        lo, hi = CATEGORY_PRICE_BAND[cat]
        # log-uniform price within band, rounded to 1000 VND
        list_price = int(round(float(np.exp(rng.uniform(np.log(lo), np.log(hi)))) / 1000.0) * 1000)
        mlo, mhi = CATEGORY_MARGIN[cat]
        margin = float(rng.uniform(mlo, mhi))
        unit_cost = int(round(list_price * (1.0 - margin) / 1000.0) * 1000)
        launch = HISTORY_START - timedelta(days=int(rng.integers(0, 1200)))
        skus.append(
            {
                "sku_id": f"K{i + 1:06d}",
                "sku_name": f"{brand} {sub} {1000 + i}",
                "category": cat,
                "subcategory": sub,
                "brand": brand,
                "supplier_id": suppliers[int(rng.integers(len(suppliers)))],
                "unit_cost": unit_cost,
                "list_price": list_price,
                "is_private_label": False,
                "launch_date": launch,
            }
        )
    return skus


def build_customers(rng: np.random.Generator, scale: Scale) -> list[dict]:
    customers: list[dict] = []
    n_b2b = max(3, scale.n_customers // 40)  # B2B is a small minority of loyalty members
    tiers = list(schema.CUSTOMER_TIERS)
    tier_p = np.array([0.55, 0.25, 0.15, 0.05])
    for i in range(scale.n_customers):
        is_b2b = i < n_b2b
        prov = CANONICAL_PROVINCES[int(rng.integers(len(CANONICAL_PROVINCES)))]
        joined = HISTORY_START - timedelta(days=int(rng.integers(0, 1400)))
        if is_b2b:
            ctype = "b2b"
            tier = "platinum" if rng.random() < 0.6 else "gold"
            birth_year = None
        else:
            ctype = "retail"
            tier = tiers[int(rng.choice(len(tiers), p=tier_p))]
            birth_year = int(rng.integers(1965, 2006))
        customers.append(
            {
                "customer_id": f"C{i + 1:07d}",
                "customer_type": ctype,
                "joined_date": joined,
                "tier": tier,
                "province": prov,
                "birth_year": birth_year,
            }
        )
    return customers


def build_promotions(rng: np.random.Generator) -> list[dict]:
    """Named seasonal campaigns spanning the history; mechanics per research."""
    promos: list[dict] = []
    pid = 1

    def add(name, mechanic, start, end, funded):
        nonlocal pid
        promos.append(
            {
                "promo_id": f"P{pid:03d}",
                "promo_name": name,
                "mechanic": mechanic,
                "start_date": start,
                "end_date": end,
                "funded_by": funded,
            }
        )
        pid += 1

    for y in (2024, 2025):
        add(f"Tet Sale {y}", "discount", date(y, 1, 15), date(y, 2, 12), "retailer")
        add(f"Back To School {y}", "voucher", date(y, 7, 15), date(y, 9, 15), "retailer")
        add(f"11.11 {y}", "discount", date(y, 11, 8), date(y, 11, 12), "supplier")
        add(f"Black Friday {y}", "discount", date(y, 11, 18), date(y, 12, 1), "supplier")
        add(f"12.12 {y}", "bundle", date(y, 12, 10), date(y, 12, 13), "retailer")
        add(f"Tra Gop 0pct {y}", "installment_0pct", date(y, 1, 1), date(y, 12, 31), "retailer")
        add(f"Thu Cu Doi Moi {y}", "trade_in", date(y, 1, 1), date(y, 12, 31), "retailer")
    return promos


# ---------------------------------------------------------------------------
# Fact generation
# ---------------------------------------------------------------------------
def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _promo_for_day(promos: list[dict], d: date, mechanic_pref: tuple[str, ...], rng) -> dict | None:
    active = [
        p for p in promos
        if p["start_date"] <= d <= p["end_date"] and p["mechanic"] in mechanic_pref
    ]
    if not active:
        return None
    return active[int(rng.integers(len(active)))]


def generate_facts(
    rng: np.random.Generator,
    scale: Scale,
    stores: list[dict],
    skus: list[dict],
    customers: list[dict],
    promos: list[dict],
):
    """Return (sales_lines, returns, inventory, traffic) as lists of dicts."""
    sales: list[dict] = []
    returns: list[dict] = []
    traffic: list[dict] = []

    retail_customers = [c for c in customers if c["customer_type"] == "retail"]
    b2b_customers = [c for c in customers if c["customer_type"] == "b2b"]

    # SKU sampling weights by category popularity.
    sku_weights = np.array([CATEGORY_WEIGHT[s["category"]] for s in skus])
    sku_weights = sku_weights / sku_weights.sum()

    basket_counter = 0
    return_counter = 0

    days = list(_daterange(HISTORY_START, HISTORY_END))

    for store in stores:
        s_open = store["opened_date"]
        s_close = store["closed_date"] or (HISTORY_END + timedelta(days=1))
        is_online_store = store["format"] == "online"

        for d in days:
            if d < s_open or d >= s_close:
                continue

            # ---- Retail traffic & baskets ----
            retail_mult = _day_multiplier(d, channel_is_b2b=False)
            base = scale.retail_baskets_per_store_day * (0.0 if is_online_store else 1.0)
            # Online store gets its own web/app volume even with no footfall.
            online_base = scale.retail_baskets_per_store_day * (1.4 if is_online_store else 0.0)
            exp_retail_baskets = (base + online_base) * retail_mult
            n_retail_baskets = int(rng.poisson(max(0.0, exp_retail_baskets)))

            online_share = _online_share(d)
            footfall_transactions = 0

            for _ in range(n_retail_baskets):
                basket_counter += 1
                basket_id = f"B{basket_counter:09d}"
                # Channel choice
                r = rng.random()
                if is_online_store:
                    channel = "app" if rng.random() < 0.5 else "web"
                elif r < online_share:
                    channel = "app" if rng.random() < 0.45 else "web"
                else:
                    channel = "in_store"
                    footfall_transactions += 1

                # customer_id: trap 3 — walk-in retail often NULL.
                if channel == "in_store":
                    cust = retail_customers[int(rng.integers(len(retail_customers)))] if (
                        retail_customers and rng.random() < 0.45
                    ) else None
                else:
                    # online retail more often identified but still can be null
                    cust = retail_customers[int(rng.integers(len(retail_customers)))] if (
                        retail_customers and rng.random() < 0.75
                    ) else None

                n_lines = 1 + int(rng.geometric(0.6)) - 1  # mostly 1-2 lines
                n_lines = max(1, min(n_lines, 5))
                ts = datetime.combine(d, datetime.min.time()) + timedelta(
                    hours=int(rng.integers(8, 22)), minutes=int(rng.integers(0, 60))
                )
                _emit_basket(
                    sales, returns, rng, skus, sku_weights, promos, store, cust,
                    basket_id, ts, d, channel, n_lines, is_b2b=False,
                    return_counter_ref=lambda: None,
                )

            # ---- B2B baskets: few, large, weekday-leaning, always identified ----
            b2b_mult = _day_multiplier(d, channel_is_b2b=True)
            # B2B roughly one order every few days per (non-online) store.
            exp_b2b = (0.0 if is_online_store else 0.12) * b2b_mult * (scale.n_stores / 10.0)
            n_b2b_baskets = int(rng.poisson(max(0.0, exp_b2b)))
            for _ in range(n_b2b_baskets):
                if not b2b_customers:
                    break
                basket_counter += 1
                basket_id = f"B{basket_counter:09d}"
                cust = b2b_customers[int(rng.integers(len(b2b_customers)))]
                n_lines = int(rng.integers(8, 30))  # many lines
                ts = datetime.combine(d, datetime.min.time()) + timedelta(
                    hours=int(rng.integers(9, 18)), minutes=int(rng.integers(0, 60))
                )
                _emit_basket(
                    sales, returns, rng, skus, sku_weights, promos, store, cust,
                    basket_id, ts, d, channel="b2b", n_lines=n_lines, is_b2b=True,
                    return_counter_ref=lambda: None,
                )

            # ---- Daily traffic row (physical stores only) ----
            if not is_online_store:
                # footfall > transactions (browsers who don't buy)
                conv = float(rng.uniform(0.18, 0.35))
                footfall = int(max(footfall_transactions, round(footfall_transactions / conv))) if footfall_transactions else int(rng.integers(0, 30) * retail_mult)
                traffic.append(
                    {
                        "store_id": store["store_id"],
                        "date": d,
                        "footfall": footfall,
                        "transaction_count": footfall_transactions,
                    }
                )

    # Returns were appended inline via _emit_basket; renumber return_ids deterministically.
    for i, rrow in enumerate(returns, start=1):
        rrow["return_id"] = f"R{i:07d}"

    # Inventory: weekly snapshots (trap 5) with staleness (trap 6).
    inventory = _build_inventory(rng, scale, stores, skus, sales)

    return sales, returns, inventory, traffic


def _emit_basket(
    sales, returns, rng, skus, sku_weights, promos, store, cust,
    basket_id, ts, d, channel, n_lines, is_b2b, return_counter_ref,
):
    chosen = rng.choice(len(skus), size=n_lines, replace=False, p=sku_weights)
    for line_no, sidx in enumerate(chosen, start=1):
        sku = skus[int(sidx)]
        cat = sku["category"]
        if is_b2b:
            qty = int(rng.integers(3, 25))
        else:
            qty = 1 if rng.random() < 0.85 else int(rng.integers(2, 4))

        # Transacted unit price: jitter around list (trap 8: differs from list_price).
        price_jitter = float(rng.uniform(0.97, 1.03))
        unit_price = int(round(sku["list_price"] * price_jitter / 1000.0) * 1000)
        gross = unit_price * qty

        # Promotion & discount
        promo = _promo_for_day(promos, d, ("discount", "voucher", "bundle"), rng)
        if promo is not None and rng.random() < 0.6:
            disc_frac = float(rng.uniform(0.05, 0.30))
            promo_id = promo["promo_id"]
        elif rng.random() < 0.10:
            disc_frac = float(rng.uniform(0.02, 0.10))  # ad-hoc discount, no promo
            promo_id = None
        else:
            disc_frac = 0.0
            promo_id = None
        # B2B always gets negotiated discount
        if is_b2b:
            disc_frac = max(disc_frac, float(rng.uniform(0.06, 0.18)))
        discount = int(round(gross * disc_frac / 1000.0) * 1000)
        net = gross - discount

        # Actual cost jitter around list unit_cost (trap 8).
        cost_jitter = float(rng.uniform(0.98, 1.02))
        cost_amount = int(round(sku["unit_cost"] * cost_jitter / 1000.0) * 1000) * qty

        sales.append(
            {
                "basket_id": basket_id,
                "line_id": line_no,
                "ts": ts,
                "store_id": store["store_id"],
                "sku_id": sku["sku_id"],
                "customer_id": None if cust is None else cust["customer_id"],
                "channel": channel,
                "qty": qty,
                "gross_amount": gross,
                "discount_amount": discount,
                "net_amount": net,
                "cost_amount": cost_amount,
                "promo_id": promo_id,
            }
        )

        # Returns (trap 2): category-dependent rate; return happens 3-30 days later.
        rate = CATEGORY_RETURN_RATE[cat]
        if rng.random() < rate:
            ret_qty = qty if qty == 1 else int(rng.integers(1, qty + 1))
            refund = int(round(net * ret_qty / qty / 1000.0) * 1000)
            ret_date = d + timedelta(days=int(rng.integers(3, 31)))
            if ret_date <= HISTORY_END:
                reason = _return_reason(cat, rng)
                returns.append(
                    {
                        "return_id": "R_PENDING",
                        "orig_basket_id": basket_id,
                        "return_date": ret_date,
                        "sku_id": sku["sku_id"],
                        "qty": ret_qty,
                        "refund_amount": refund,
                        "reason": reason,
                    }
                )


def _return_reason(cat: str, rng) -> str:
    if cat == "PC Component":
        pool = ["incompatible", "defective", "defective", "wrong_item", "changed_mind"]
    elif cat == "Accessory":
        pool = ["changed_mind", "wrong_item", "defective"]
    else:
        pool = ["defective", "changed_mind", "warranty_exchange", "wrong_item"]
    return pool[int(rng.integers(len(pool)))]


def _build_inventory(rng, scale, stores, skus, sales) -> list[dict]:
    """Weekly on-hand snapshots per store x sku (trap 5), lagging sales by ~1 week (trap 6)."""
    inventory: list[dict] = []
    if not sales:
        return inventory
    max_sales_date = max(s["ts"].date() for s in sales)
    # Trap 6: last snapshot is ~1 week before the last sale.
    last_snapshot = max_sales_date - timedelta(days=8)

    # Weekly snapshot dates (Sundays) from history start up to last_snapshot.
    snap_dates: list[date] = []
    d = HISTORY_START
    # advance to first Sunday
    d += timedelta(days=(6 - d.weekday()) % 7)
    while d <= last_snapshot:
        snap_dates.append(d)
        d += timedelta(days=7)

    # To keep volume sane, snapshot only a subset of skus per store at full scale
    # (the traps concern grain/staleness, which hold for any covered store x sku).
    max_sku_per_store = min(len(skus), 60 if scale.name == "full" else len(skus))

    for store in stores:
        s_open = store["opened_date"]
        s_close = store["closed_date"] or (HISTORY_END + timedelta(days=1))
        if store["format"] == "online":
            continue  # online store has no physical on-hand
        sku_subset = skus[:max_sku_per_store]
        # baseline on-hand per sku for this store
        baseline = {sku["sku_id"]: int(rng.integers(2, 40)) for sku in sku_subset}
        for snap in snap_dates:
            if snap < s_open or snap >= s_close:
                continue
            for sku in sku_subset:
                sid = sku["sku_id"]
                on_hand = max(0, baseline[sid] + int(rng.integers(-6, 7)))
                in_transit = int(rng.integers(0, 12)) if rng.random() < 0.4 else 0
                inventory.append(
                    {
                        "store_id": store["store_id"],
                        "sku_id": sid,
                        "snapshot_date": snap,
                        "on_hand_qty": on_hand,
                        "in_transit_qty": in_transit,
                    }
                )
    return inventory


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
    Faker.seed(seed)
    _ = Faker("vi_VN")  # seeded; reserved for future name realism

    CSV_DIR.mkdir(parents=True, exist_ok=True)
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)

    stores = build_stores(rng, scale)
    suppliers = build_suppliers(rng)
    skus = build_skus(rng, scale, suppliers)
    customers = build_customers(rng, scale)
    promos = build_promotions(rng)
    sales, returns, inventory, traffic = generate_facts(rng, scale, stores, skus, customers, promos)

    data = {
        "dim_store": stores,
        "dim_sku": skus,
        "dim_customer": customers,
        "dim_promotion": promos,
        "fact_sales_lines": sales,
        "fact_returns": returns,
        "fact_inventory": inventory,
        "fact_traffic": traffic,
    }
    for table, rows in data.items():
        write_csv(table, rows)
        write_parquet(table, rows)
    return data


def _summary(data: dict[str, list[dict]]) -> None:
    print("\n=== Generation summary ===")
    for table, rows in data.items():
        line = f"{table:20s} rows={len(rows):>10,}"
        # date min/max where a date-ish column exists
        for col in ("ts", "return_date", "snapshot_date", "date", "opened_date"):
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
    ap = argparse.ArgumentParser(description="Generate the true_north Phong Vu demo dataset.")
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
