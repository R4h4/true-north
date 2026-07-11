# Trap Registry

The `true_north` dataset deliberately plants traps that a naive text-to-SQL agent falls
into. Each trap is an instance of a failure-mode class and later becomes an eval question.
The generator (`generator/generate.py`) is designed so every trap below actually holds in
the produced data at all scales (`tiny` / `small` / `full`).

Canonical conventions the traps depend on:

- **Amounts** are in **VND**, stored as `int64`. Management speaks in **tỷ** (billions of VND).
- **Channel** values are snake_case: `in_store`, `web`, `app`, `b2b`. There is no `offline`/`online` column.
- **Province** is stored in one canonical long form (`Ho Chi Minh City`, never `HCMC`/`Saigon`; `Ha Noi`, never `HN`).
- **Revenue** as booked on `fact_sales_lines.net_amount` is *before* returns. Returns live in a separate table.

---

## 1. Metric polysemy

- **Failure-mode class:** ambiguous business metric mapped to a single naive SQL expression.
- **Affected tables/columns:** `fact_sales_lines.gross_amount` / `net_amount` / `qty`, `fact_returns.refund_amount`, `fact_sales_lines.channel = 'b2b'`.
- **Three distinct polysemies:**
  - **GMV gross vs net of returns** — "revenue" / "GMV" can mean `SUM(net_amount)` (booked) or that minus `SUM(fact_returns.refund_amount)` (net of returns). They differ materially because return rates are high for components.
  - **"Basket size"** — item count (`SUM(qty)` per basket) vs value (`SUM(net_amount)` per basket). B2B baskets have huge value but the *count* story is different.
  - **"Revenue" retail-only vs incl. B2B** — B2B baskets (`channel = 'b2b'`) are a few, very large orders that dominate total value. "Store revenue" in Phong Vũ language usually means retail; including B2B skews averages, per-store comparisons, and growth.
- **Wrong answer a naive agent gives:** `SELECT SUM(net_amount) FROM fact_sales_lines` and calls it "revenue" / "GMV" — silently gross-of-returns and B2B-inclusive.
- **Correct handling:** ask which definition; for GMV net-of-returns subtract `fact_returns`; for retail metrics filter `channel <> 'b2b'`; distinguish basket item-count from basket value.

## 2. Separate returns table

- **Failure-mode class:** relevant fact split across tables; naive query ignores the second table.
- **Affected tables/columns:** `fact_returns` (whole table) vs `fact_sales_lines.net_amount`; `fact_returns.reason`, `dim_sku.category`.
- **Design guarantee:** return rate is category-dependent — **high for `PC Component`** (DOA / `incompatible`), **low for `Accessory`**. So category-level net revenue and return-rate rankings differ from gross.
- **Wrong answer a naive agent gives:** revenue/units overstated because refunds are never subtracted; "top category by revenue" wrong when a high-return category is gross-inflated.
- **Correct handling:** net revenue = `SUM(net_amount)` − `SUM(refund_amount)`; join/aggregate `fact_returns` and compute return rate per category.

## 3. Nullable customer_id

- **Failure-mode class:** nullable FK breaks denominators / joins silently.
- **Affected tables/columns:** `fact_sales_lines.customer_id` (nullable), `dim_customer`.
- **Design guarantee:** **B2B lines always have a `customer_id`** (organisations are loyalty members); **walk-in retail is often NULL** (non-loyalty). A meaningful fraction of `in_store` retail lines have NULL customer.
- **Wrong answer a naive agent gives:** "loyalty penetration" = distinct customers / total lines, or an inner join to `dim_customer` that silently drops walk-ins — both wrong; also "sales per customer" divides by the wrong denominator.
- **Correct handling:** loyalty penetration = lines (or baskets) with non-NULL `customer_id` over *all* lines; use LEFT JOIN; state whether walk-ins are in or out of the denominator.

## 4. Same-store comparability

- **Failure-mode class:** composition change over time invalidates a naive time comparison.
- **Affected tables/columns:** `dim_store.opened_date`, `dim_store.closed_date` (nullable), `fact_sales_lines.ts`.
- **Design guarantee:** **≥2 stores open mid-history and 1 closes** during the ~2-year window. Same-store (like-for-like) growth requires restricting to stores open for the full comparison period (≥13 months open, and not closed).
- **Wrong answer a naive agent gives:** YoY / MoM total revenue growth counting new and closed stores — attributes footprint change to organic growth.
- **Correct handling:** for same-store growth, restrict to stores with `opened_date` ≤ (period start − 13 months) and (`closed_date` IS NULL OR `closed_date` > period end).

## 5. Snapshot grain (double-counting)

- **Failure-mode class:** periodic-snapshot fact summed as if it were a transaction fact.
- **Affected tables/columns:** `fact_inventory` (weekly grain), `on_hand_qty`, `in_transit_qty`, `snapshot_date`.
- **Design guarantee:** one row per store×sku **per week**. Summing `on_hand_qty` across weeks double- (52×-) counts the same physical stock.
- **Wrong answer a naive agent gives:** `SELECT SUM(on_hand_qty) FROM fact_inventory` as "current inventory" — inflated by the number of snapshots.
- **Correct handling:** take the latest `snapshot_date` per store×sku (or a specific week) before summing; never sum on-hand across snapshot dates.

## 6. Staleness

- **Failure-mode class:** as-of skew between two facts with different refresh cadence.
- **Affected tables/columns:** `fact_inventory.snapshot_date` vs `fact_sales_lines.ts`.
- **Design guarantee:** the **latest inventory snapshot lags ~1 week behind the latest sales timestamp**. `MAX(snapshot_date) < MAX(DATE(ts))`.
- **Wrong answer a naive agent gives:** "sell-through since last restock" / "days of cover as of today" using today's sales against an inventory number that predates them, without noting the lag.
- **Correct handling:** align sales to the inventory as-of date; report the snapshot date explicitly; don't imply inventory is current to the latest sale.

## 7. Value-format trap

- **Failure-mode class:** business vocabulary ≠ stored codes; string form mismatch.
- **Affected tables/columns:** `fact_sales_lines.channel`, `*.province` / `dim_store.region`.
- **Design guarantee:** channel stored snake_case (`in_store`, `web`, `app`, `b2b`) — business says "offline" (= `in_store`, and sometimes `b2b`) and "online" (= `web` + `app`). Province stored one canonical way only: **`Ho Chi Minh City`** (not `HCMC`/`Saigon`/`TP HCM`), **`Ha Noi`** (not `Hanoi`/`HN`).
- **Wrong answer a naive agent gives:** `WHERE channel = 'offline'` or `WHERE province = 'HCMC'` → zero rows, silently; or maps "online" to only `web`, dropping `app`.
- **Correct handling:** map "offline"→`in_store` (decide B2B in/out), "online"→(`web`,`app`); use the canonical province spelling. Canonical vocab is enumerated in `generator/schema.py`.

## 8. Unit trap

- **Failure-mode class:** unit / scale mismatch, and list vs transacted price.
- **Affected tables/columns:** all VND amount columns; `dim_sku.unit_cost`, `dim_sku.list_price` vs `fact_sales_lines.gross_amount` / `net_amount` / `cost_amount`.
- **Design guarantee (two parts):**
  - Amounts are raw **VND** (e.g. 25_000_000 for a 25M-VND laptop). Management reports in **tỷ** (billions): a figure of `1_500_000_000_000` VND is "1,500 tỷ".
  - `dim_sku.list_price` / `unit_cost` are **list** values. The actual transacted amounts on `fact_sales_lines` differ because of discounts (and promo pricing), so `gross_amount / qty` ≠ `list_price` in general and `cost_amount / qty` ≠ `unit_cost` exactly.
- **Wrong answer a naive agent gives:** reports a raw VND number as if it were tỷ (off by 1e9), or computes "revenue" from `qty * dim_sku.list_price` instead of the fact's `net_amount`.
- **Correct handling:** divide VND by 1e9 to express in tỷ when the user speaks in billions; always use the fact's transacted amounts (`net_amount`, `cost_amount`), never `dim_sku` list values, for realized revenue/margin.
