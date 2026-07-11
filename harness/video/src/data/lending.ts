// Frozen, truthful copy for the Consumer Lending story. Values match the app's
// verified NPL-by-product answer (PR #14). Any dashboard KPI that is not a real
// governed query is flagged `illustrative`.

export const QUESTION = "How is our delinquency doing by product?";

export const AMBIGUITY = {
  prompt: "“Delinquency” is ambiguous. Which measure should I break down by product?",
  options: [
    { key: "dpd30", title: "30+ DPD ratio", sub: "early-warning portfolio delinquency" },
    { key: "npl", title: "NPL ratio", sub: "90+ DPD / non-performing loans" },
    { key: "fpd", title: "First-payment default rate", sub: "origination / vintage quality" },
  ],
  selected: 1, // NPL
};

// NPL ratio by product (ratios in [0,1]); the app's verified split.
export const NPL_BY_PRODUCT = {
  type: "hbar" as const,
  title: "NPL ratio by product",
  yFormat: "percent" as const,
  points: [
    { x: "Cash loan", y: 0.069 },
    { x: "CD installment", y: 0.011 },
    { x: "Credit card", y: 0.011 },
    { x: "Two-wheeler", y: 0.001 },
  ],
  asOf: "2025-12-31",
};

export const NPL_CAVEATS = [
  "Month-end snapshot metric — read at a single snapshot date, not summed across months.",
  "Written-off loans exit the snapshot, so NPL can fall mechanically after a write-off wave.",
];

export const NPL_READOUT =
  "Cash loans are the clear concern at 6.9% NPL — far above the other products.";

export const DENIAL = {
  headline: "I can't compute delinquency by partner for your role.",
  reason:
    "“Delinquency” maps to portfolio-risk metrics that read fact_loan_snapshots — a table the Partnerships role cannot read.",
  restricted: ["30+ DPD ratio", "NPL ratio", "First-payment default rate"],
  alternatives: [
    "Approval rate — underwriting funnel quality by partner",
    "Disbursement amount — total principal originated by partner",
    "Average ticket size — average principal per disbursed loan",
  ],
};

// Scene 5 dashboard. `real: true` values come from governed queries; the rest
// are illustrative and labelled as such on screen.
export const DASHBOARD_KPIS = [
  { label: "NPL ratio", value: "6.9%", delta: "-0.4%", up: false, real: true },
  { label: "Disbursed (YTD)", value: "₫1.84 tỷ", delta: "+8.1%", up: true, real: false },
  { label: "Collections rate", value: "92.4%", delta: "+1.2%", up: true, real: false },
  { label: "30+ DPD", value: "13.8%", delta: "-0.6%", up: false, real: false },
];
