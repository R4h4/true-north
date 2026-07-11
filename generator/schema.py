"""Single source of truth for the true_north (Phong Vu) demo warehouse schema.

Every table is a list of Column(name, dtype, description) in physical order. Both the
headers-only CSV writer (``write_headers.py``) and the data generator (``generate.py``)
import ``TABLES`` from here — column lists are never duplicated elsewhere.

``dtype`` is a logical type string consumed by the parquet writer to build an explicit
Arrow schema:

    string      -> pa.string()
    int32       -> pa.int32()   (nullable ints allowed; nulls encoded as Arrow nulls)
    int64       -> pa.int64()
    double      -> pa.float64()
    date        -> pa.date32()  (calendar date, no time)
    timestamp   -> pa.timestamp("us")
    bool        -> pa.bool_()

Amounts are VND stored as ``int64`` (no sub-unit currency in VND; management talks in
"tỷ" = billions — see data/TRAPS.md trap 8).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    dtype: str
    description: str


# ---------------------------------------------------------------------------
# Canonical value vocabularies (documented so the value-format traps are precise)
# ---------------------------------------------------------------------------

# Trap 7: channel is stored snake_case; business language says "offline"/"online".
CHANNELS = ("in_store", "web", "app", "b2b")

# Trap 7: province stored in one canonical long form. "HCMC" / "Saigon" / "HN" are NOT used.
CANONICAL_PROVINCES = (
    # North
    "Ha Noi",
    "Thai Nguyen",
    "Bac Ninh",
    # Central
    "Da Nang",
    "Thanh Hoa",
    "Nghe An",
    "Thua Thien Hue",
    "Khanh Hoa",
    "Dak Lak",
    "Gia Lai",
    # South
    "Ho Chi Minh City",
    "Binh Duong",
    "Dong Nai",
    "Ba Ria - Vung Tau",
    "Long An",
    "Tien Giang",
    "Can Tho",
    "Tay Ninh",
)

REGION_BY_PROVINCE = {
    "Ha Noi": "North",
    "Thai Nguyen": "North",
    "Bac Ninh": "North",
    "Da Nang": "Central",
    "Thanh Hoa": "Central",
    "Nghe An": "Central",
    "Thua Thien Hue": "Central",
    "Khanh Hoa": "Central",
    "Dak Lak": "Central",
    "Gia Lai": "Central",
    "Ho Chi Minh City": "South",
    "Binh Duong": "South",
    "Dong Nai": "South",
    "Ba Ria - Vung Tau": "South",
    "Long An": "South",
    "Tien Giang": "South",
    "Can Tho": "South",
    "Tay Ninh": "South",
}

STORE_FORMATS = ("flagship_showroom", "showroom", "online")
CUSTOMER_TYPES = ("retail", "b2b")
CUSTOMER_TIERS = ("standard", "silver", "gold", "platinum")
PROMO_MECHANICS = ("discount", "voucher", "installment_0pct", "trade_in", "bundle")
PROMO_FUNDERS = ("retailer", "supplier")
RETURN_REASONS = (
    "defective",          # DOA / faulty on arrival
    "incompatible",       # component doesn't fit the build (high for components)
    "changed_mind",
    "wrong_item",
    "warranty_exchange",
)

# Category -> subcategories. Brands and price bands live in generate.py; this is the
# categorical vocabulary the schema promises.
CATEGORIES = {
    "Laptop": ("Ultrabook", "Gaming Laptop", "Business Laptop", "MacBook"),
    "Desktop PC": ("Gaming PC", "Office PC", "Custom Build", "Workstation"),
    "Monitor": ("Office Monitor", "Gaming Monitor", "Professional Monitor"),
    "PC Component": ("CPU", "GPU", "RAM", "SSD", "Mainboard", "PSU", "Cooling"),
    "Gaming Gear": ("Mechanical Keyboard", "Gaming Mouse", "Headset", "Gaming Chair"),
    "Accessory": ("Keyboard & Mouse", "Webcam", "Dock & Cable", "Bag & Sleeve"),
    "Phone & Tablet": ("Smartphone", "Tablet", "Phone Accessory"),
    "Office Equipment": ("Printer", "Scanner", "Projector"),
    "Networking": ("Router", "Switch", "Access Point"),
    "Home Appliance": ("Air Purifier", "Robot Vacuum", "Small Appliance"),
}


# ---------------------------------------------------------------------------
# Table definitions (physical column order)
# ---------------------------------------------------------------------------

TABLES: dict[str, list[Column]] = {
    "dim_store": [
        Column("store_id", "string", "Surrogate store key, e.g. 'S001'."),
        Column("store_name", "string", "Human-readable showroom name."),
        Column("format", "string", f"Store format, one of {STORE_FORMATS}."),
        Column("region", "string", "North / Central / South."),
        Column("province", "string", "Canonical province name (see CANONICAL_PROVINCES)."),
        Column("opened_date", "date", "Date the store opened."),
        Column("closed_date", "date", "Date the store closed; NULL if still open."),
        Column("selling_area_sqm", "int32", "Selling-floor area in square metres."),
    ],
    "dim_sku": [
        Column("sku_id", "string", "Surrogate SKU key, e.g. 'K000123'."),
        Column("sku_name", "string", "Product name (brand + model)."),
        Column("category", "string", "Top-level category (see CATEGORIES)."),
        Column("subcategory", "string", "Subcategory within the category."),
        Column("brand", "string", "Manufacturer brand."),
        Column("supplier_id", "string", "Surrogate supplier key, e.g. 'SUP01'."),
        Column("unit_cost", "int64", "List landed cost to Phong Vu, in VND (list value; actual COGS on the fact differs)."),
        Column("list_price", "int64", "List selling price in VND (before any discount; transacted price differs)."),
        Column("is_private_label", "bool", "Whether the SKU is a Phong Vu house brand (always false in this dataset)."),
        Column("launch_date", "date", "Date the SKU was first sellable."),
    ],
    "dim_customer": [
        Column("customer_id", "string", "Surrogate loyalty-member key, e.g. 'C0000123'. Loyalty members only."),
        Column("customer_type", "string", f"One of {CUSTOMER_TYPES}."),
        Column("joined_date", "date", "Date the customer joined the loyalty programme."),
        Column("tier", "string", f"Loyalty tier, one of {CUSTOMER_TIERS}."),
        Column("province", "string", "Customer's canonical province."),
        Column("birth_year", "int32", "Year of birth; NULL for b2b customers (organisations)."),
    ],
    "dim_promotion": [
        Column("promo_id", "string", "Surrogate promotion key, e.g. 'P012'."),
        Column("promo_name", "string", "Campaign name."),
        Column("mechanic", "string", f"Promotion mechanic, one of {PROMO_MECHANICS}."),
        Column("start_date", "date", "Promotion start date (inclusive)."),
        Column("end_date", "date", "Promotion end date (inclusive)."),
        Column("funded_by", "string", f"Who funds the discount, one of {PROMO_FUNDERS}."),
    ],
    "fact_sales_lines": [
        Column("basket_id", "string", "Basket / order id; groups lines of one transaction."),
        Column("line_id", "int32", "Line number within the basket (1-based)."),
        Column("ts", "timestamp", "Transaction timestamp (local time, us precision)."),
        Column("store_id", "string", "FK to dim_store."),
        Column("sku_id", "string", "FK to dim_sku."),
        Column("customer_id", "string", "FK to dim_customer; NULL for non-loyalty walk-ins (trap 3)."),
        Column("channel", "string", f"Sales channel, one of {CHANNELS} (trap 7: snake_case, not 'offline'/'online')."),
        Column("qty", "int32", "Units sold on this line."),
        Column("gross_amount", "int64", "qty * effective unit price before discount, VND."),
        Column("discount_amount", "int64", "Discount applied to this line, VND (>= 0)."),
        Column("net_amount", "int64", "gross_amount - discount_amount, VND (revenue booked before returns, trap 1/2)."),
        Column("cost_amount", "int64", "qty * actual unit cost, VND (COGS)."),
        Column("promo_id", "string", "FK to dim_promotion; NULL if no promotion applied."),
    ],
    "fact_returns": [
        Column("return_id", "string", "Surrogate return key, e.g. 'R0000123'."),
        Column("orig_basket_id", "string", "Basket id of the original sale (FK into fact_sales_lines.basket_id)."),
        Column("return_date", "date", "Date the return was processed."),
        Column("sku_id", "string", "FK to dim_sku (the returned product)."),
        Column("qty", "int32", "Units returned."),
        Column("refund_amount", "int64", "Amount refunded, VND (positive; subtract from revenue for net, trap 2)."),
        Column("reason", "string", f"Return reason, one of {RETURN_REASONS}."),
    ],
    "fact_inventory": [
        Column("store_id", "string", "FK to dim_store."),
        Column("sku_id", "string", "FK to dim_sku."),
        Column("snapshot_date", "date", "Snapshot date; WEEKLY grain (trap 5: do not sum across weeks)."),
        Column("on_hand_qty", "int32", "Units on hand at the store at snapshot time."),
        Column("in_transit_qty", "int32", "Units in transit toward the store at snapshot time."),
    ],
    "fact_traffic": [
        Column("store_id", "string", "FK to dim_store."),
        Column("date", "date", "Calendar date (daily grain)."),
        Column("footfall", "int32", "Number of visitors that entered the store."),
        Column("transaction_count", "int32", "Number of completed baskets that day."),
    ],
}


def column_names(table: str) -> list[str]:
    """Ordered column names for a table."""
    return [c.name for c in TABLES[table]]


def table_names() -> list[str]:
    return list(TABLES.keys())
