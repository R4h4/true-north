import * as React from "react";
import { KgPanel } from "true-north-ui";

// Subgraph as the agent accumulates it during a real governed turn:
// resolved concept -> metric, its dimensions and source tables — plus a
// locked metric (exists in the graph, denied to this persona's role).
export const ResolvedWithLockedMetric = () => (
  <KgPanel
    graph={{
      nodes: [
        { id: "Concept:customer-retention", label: "Concept", name: "Customer Retention", locked: false, new: false },
        { id: "Metric:repeat_purchase_rate_90d", label: "Metric", name: "Repeat-purchase rate (90d)", locked: false, new: true },
        { id: "Metric:gross_margin", label: "Metric", name: "Gross margin", locked: true, new: false },
        { id: "Dimension:channel", label: "Dimension", name: "Sales channel", locked: false, new: false },
        { id: "Dimension:region", label: "Dimension", name: "Region", locked: false, new: false },
        { id: "Table:fact_sales_lines", label: "Table", name: "fact_sales_lines", locked: false, new: false },
      ],
      edges: [
        { source: "Concept:customer-retention", target: "Metric:repeat_purchase_rate_90d", label: "MEASURED_BY" },
        { source: "Metric:repeat_purchase_rate_90d", target: "Dimension:channel", label: "HAS_DIMENSION" },
        { source: "Metric:repeat_purchase_rate_90d", target: "Dimension:region", label: "HAS_DIMENSION" },
        { source: "Metric:repeat_purchase_rate_90d", target: "Table:fact_sales_lines", label: "COMPUTED_FROM" },
        { source: "Metric:gross_margin", target: "Table:fact_sales_lines", label: "COMPUTED_FROM" },
      ],
    }}
  />
);

export const EmptyState = () => <KgPanel />;
