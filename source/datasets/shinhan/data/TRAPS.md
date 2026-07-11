# Trap Registry

The `shinhan` dataset deliberately plants traps that a naive text-to-SQL agent falls into.
Each trap is an instance of a failure-mode class and later becomes an eval question. The
generator (`generator/generate.py`) is designed so every trap below actually holds in the
produced data at all scales (`tiny` / `small` / `full`).

Canonical conventions the traps depend on:

- **Amounts** are in **VND**, stored as `int64`, full đồng. Management speaks in **tỷ**
  (billions of VND).
- **Channel** values are snake_case: `digital_app`, `pos_partner`, `dsa`, `telesales`.
- **DPD bucket** values are snake_case: `current`, `dpd_1_29`, `dpd_30_59`, `dpd_60_89`,
  `dpd_90_plus`.
- `fact_loan_snapshots` is a MONTH-END periodic snapshot (one row per loan per month);
  `fact_collections` is a monthly transaction fact keyed the same way but on a different
  bucket convention (see trap 8).

---

## 1. Snapshot grain (double-counting)

- **Failure-mode class:** periodic-snapshot fact summed as if it were a transaction fact.
- **Affected tables/columns:** `fact_loan_snapshots` (month-end grain), `outstanding_principal`, `loan_id`, `snapshot_month`.
- **Design guarantee:** one row per loan **per month**. Summing `outstanding_principal` or counting `loan_id` across `snapshot_month` values double-counts the same loan/balance once per month it appears.
- **Wrong answer a naive agent gives:** `SELECT SUM(outstanding_principal) FROM fact_loan_snapshots` as "current portfolio size" — inflated by the number of snapshot months in scope.
- **Correct handling:** restrict to a single `snapshot_month` (typically the latest) before summing or counting.

## 2. Write-off wave

- **Failure-mode class:** silent exit from a fact table misread as improvement.
- **Affected tables/columns:** `fact_loan_snapshots.status = 'written_off'`, `npl_ratio`.
- **Design guarantee:** a board-approved write-off wave is planted in **2025-06** — loans that were `dpd_90_plus` at that snapshot are written off and **stop appearing in fact_loan_snapshots the month after**. `npl_ratio` computed naively drops sharply in **2025-07** even though no loan actually improved.
- **Wrong answer a naive agent gives:** "NPL ratio improved in July" — treats the absence of written-off loans as risk resolution.
- **Correct handling:** check for a write-off event before reading a period-over-period NPL improvement as real; state that write-offs remove loans from the denominator and numerator alike, not just the numerator.

## 3. Restructuring reset

- **Failure-mode class:** a remediation action silently launders a quality metric.
- **Affected tables/columns:** `fact_loan_snapshots.is_restructured`, `dpd`, `dpd_bucket`, `dpd30_plus_ratio`.
- **Design guarantee:** a restructuring campaign is planted **2025-03..2025-05** — ~4% of loans at 30-89 DPD during those months get `is_restructured = true` and `dpd` reset to 0, landing them back in `current`.
- **Wrong answer a naive agent gives:** "early delinquency improved after the restructuring push" without noting the loans didn't actually cure — they were reclassified.
- **Correct handling:** surface `is_restructured` alongside `dpd30_plus_ratio`; filter to or split out restructured loans before crediting a drop in 30+ DPD to real repayment improvement.

## 4. Approval rate denominator

- **Failure-mode class:** ambiguous business metric mapped to a single naive SQL expression.
- **Affected tables/columns:** `fact_applications.decision` (`approved` / `rejected` / `cancelled`).
- **Design guarantee:** ~8% of applications are `cancelled` (applicant withdrawal, not an underwriting decision). `approval_rate` = approved / (approved + rejected); cancelled is excluded from the denominator.
- **Wrong answer a naive agent gives:** `approved_count / total_count` — includes cancelled in the denominator, understating the true approval rate.
- **Correct handling:** filter `decision IN ('approved', 'rejected')` for the denominator.

## 5. Partner NULL outside POS channel

- **Failure-mode class:** nullable FK breaks joins/groupings silently.
- **Affected tables/columns:** `fact_applications.partner_id`, `fact_disbursements.partner_id` (nullable).
- **Design guarantee:** `partner_id` is set **only** for `channel = 'pos_partner'` loans. It is NULL for `digital_app`, `dsa`, and `telesales` — the majority of cash-loan volume.
- **Wrong answer a naive agent gives:** an INNER JOIN to `dim_partner`, or "disbursements by partner" without a NULL bucket — silently drops all non-POS-partner volume (most cash loans, all telesales/DSA loans).
- **Correct handling:** LEFT JOIN to `dim_partner`; report a "no partner (direct channel)" bucket explicitly when grouping by partner.

## 6. Bad telesales vintage

- **Failure-mode class:** as-of/cohort skew hidden by calendar aggregation.
- **Affected tables/columns:** `fact_disbursements.disbursed_date`, `channel = 'telesales'`, `fpd_rate`.
- **Design guarantee:** loans disbursed via `telesales` in **2025-01** and **2025-02** have roughly **2x** the first-payment-default rate of other vintages — a bad origination cohort (planted, matching a real telesales-quality narrative). This is visible ONLY when `fpd_rate` is grouped by `vintage_month` (disbursement month); it is invisible in calendar-month DPD aggregation, which blends the bad cohort into a larger, more seasoned population.
- **Wrong answer a naive agent gives:** "FPD looks fine" when aggregating delinquency by the calendar month it was observed rather than the month the loan was disbursed.
- **Correct handling:** always bind `fpd_rate` to `vintage_month`; never substitute a calendar observation month.

## 7. Unit trap

- **Failure-mode class:** unit / scale mismatch.
- **Affected tables/columns:** all VND amount columns (`fact_applications.requested_amount`/`approved_amount`, `fact_disbursements.principal`/`monthly_installment`, `fact_loan_snapshots.outstanding_principal`, `fact_collections.amount_due`/`amount_collected`).
- **Design guarantee:** amounts are raw **VND** (e.g. `50_000_000` for a 50M-VND loan), full đồng, no thousands scaling. Management reports in **tỷ** (billions): a figure of `2_500_000_000_000` VND is "2,500 tỷ".
- **Wrong answer a naive agent gives:** reports a raw VND number as if it were already in tỷ (off by 1e9), or silently divides by 1,000 assuming thousands-scaled storage.
- **Correct handling:** divide VND by 1e9 to express in tỷ when the user speaks in billions; never assume a pre-existing thousands scale.

## 8. Bucket migration (collections vs. snapshot)

- **Failure-mode class:** two facts describe related state with different as-of semantics; naive join misreads them as the same value.
- **Affected tables/columns:** `fact_collections.bucket_at_due` vs. `fact_loan_snapshots.dpd_bucket` for the same `loan_id` and calendar month.
- **Design guarantee:** `bucket_at_due` is the DPD bucket at the **start** of the collections month; `dpd_bucket` on the snapshot is the bucket at **month-end**. A loan can migrate buckets (cure or worsen) during the month, so the two values legitimately differ for the same loan/month.
- **Wrong answer a naive agent gives:** joins `fact_collections` and `fact_loan_snapshots` on the same month and treats `bucket_at_due` and `dpd_bucket` as interchangeable — misstates roll rates (the share of loans that move from one bucket to a worse one).
- **Correct handling:** state explicitly which bucket convention (start-of-month vs. end-of-month) is being used; compute roll rate as bucket-at-due (this month) vs. dpd_bucket (this month, end) or dpd_bucket (prior month) vs. dpd_bucket (this month) — never mix the two conventions as if equivalent.
