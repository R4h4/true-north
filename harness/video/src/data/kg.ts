// KG node/edge layouts for the scenes (percent coords within the KG pane).
import type { KgNode, KgEdge } from "../chrome/KgPanel";

// Scene 2 — the delinquency ambiguity: three concept variants each measured by
// one metric.
// Three concept→metric pairs, one per row, so the long names get full width in
// the narrow pane instead of colliding across a single top band.
export const KG_AMBIGUITY: { nodes: KgNode[]; edges: KgEdge[] } = {
  nodes: [
    { id: "c-early", type: "Concept", name: "Early delinquency", x: 30, y: 20 },
    { id: "m-dpd", type: "Metric", name: "30+ DPD ratio", x: 76, y: 20 },
    { id: "c-port", type: "Concept", name: "Portfolio delinquency", x: 30, y: 50 },
    { id: "m-npl", type: "Metric", name: "NPL ratio", x: 76, y: 50 },
    { id: "c-npl", type: "Concept", name: "Non-performing loans", x: 30, y: 80 },
    { id: "m-fpd", type: "Metric", name: "FPD rate", x: 76, y: 80 },
  ],
  edges: [
    { from: "c-early", to: "m-dpd", label: "MEASURED_BY" },
    { from: "c-port", to: "m-npl", label: "MEASURED_BY" },
    { from: "c-npl", to: "m-fpd", label: "MEASURED_BY" },
  ],
};

// Scene 3 — provenance of the chosen NPL metric.
export const KG_PROVENANCE: { nodes: KgNode[]; edges: KgEdge[] } = {
  nodes: [
    { id: "c-npl", type: "Concept", name: "Non-performing loans", x: 50, y: 12 },
    { id: "m-npl", type: "Metric", name: "NPL ratio", x: 50, y: 33 },
    { id: "d-product", type: "Dimension", name: "Product", x: 25, y: 57 },
    { id: "d-prov", type: "Dimension", name: "Customer province", x: 75, y: 57 },
    { id: "k-writeoff", type: "Constraint", name: "write_off_exits", x: 30, y: 80 },
    { id: "t-snap", type: "Table", name: "fact_loan_snapshots", x: 62, y: 92 },
  ],
  edges: [
    { from: "c-npl", to: "m-npl", label: "MEASURED_BY" },
    { from: "m-npl", to: "d-product", label: "HAS_DIMENSION" },
    { from: "m-npl", to: "d-prov" },
    { from: "m-npl", to: "k-writeoff", label: "CONSTRAINS" },
    { from: "m-npl", to: "t-snap", label: "COMPUTED_FROM" },
  ],
};
export const KG_PROVENANCE_HL = ["c-npl", "m-npl", "d-product", "k-writeoff", "t-snap"];

// Scene 4 — Partnerships denial: the delinquency metrics + their table are
// restricted for this role.
export const KG_DENIED: { nodes: KgNode[]; edges: KgEdge[] } = {
  nodes: [
    { id: "m-dpd", type: "Metric", name: "30+ DPD ratio", x: 30, y: 26, locked: true },
    { id: "m-npl", type: "Metric", name: "NPL ratio", x: 30, y: 50, locked: true },
    { id: "m-fpd", type: "Metric", name: "FPD rate", x: 30, y: 74, locked: true },
    { id: "t-snap", type: "Table", name: "fact_loan_snapshots", x: 72, y: 50, locked: true },
  ],
  edges: [
    { from: "m-dpd", to: "t-snap" },
    { from: "m-npl", to: "t-snap" },
    { from: "m-fpd", to: "t-snap" },
  ],
};
