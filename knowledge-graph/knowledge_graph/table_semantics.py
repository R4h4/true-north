"""Table node semantics (grain, freshness_note, node description) per physical table.

schema.py is the source of truth for columns but does not carry a table-level grain or
freshness note; those are the Table-node properties CONTRACT §4.1 requires. This map
supplies them, drawn from schema.py column docs + source/data/TRAPS.md. Keys must be a
subset of schema.TABLES; the compiler asserts every table it emits has an entry.

`description` here is the Table node's `description` property (short, node-facing);
where a fixture pins it (fact_sales_lines, fact_returns) the wording matches.
"""

from __future__ import annotations

TABLE_SEMANTICS: dict[str, dict[str, str]] = {
    "dim_store": {
        "description": "Stores; opened_date/closed_date drive same-store comparability.",
        "grain": "store",
        "freshness_note": "slowly changing dimension",
    },
    "dim_sku": {
        "description": "Products; unit_cost/list_price are list values, not transacted.",
        "grain": "sku",
        "freshness_note": "slowly changing dimension",
    },
    "dim_customer": {
        "description": "Loyalty customers; walk-ins are not present.",
        "grain": "customer",
        "freshness_note": "refreshed daily",
    },
    "dim_promotion": {
        "description": "Promotions; mechanic and funder of each campaign.",
        "grain": "promotion",
        "freshness_note": "slowly changing dimension",
    },
    "fact_sales_lines": {
        "description": "One row per basket line; net_amount is booked (gross of returns).",
        "grain": "sales line",
        "freshness_note": "refreshed daily",
    },
    "fact_returns": {
        "description": "Refunds; refund_amount reduces net revenue. Separate table from sales.",
        "grain": "return line",
        "freshness_note": "refreshed daily",
    },
    "fact_inventory": {
        "description": "Weekly on-hand snapshot per store×sku; never sum on_hand across weeks.",
        "grain": "store × sku × week (snapshot)",
        "freshness_note": "weekly snapshot; latest lags ~1 week behind sales",
    },
    "fact_traffic": {
        "description": "Daily store footfall and completed-basket counts.",
        "grain": "store × day",
        "freshness_note": "refreshed daily",
    },
}
