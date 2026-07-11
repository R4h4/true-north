import * as React from "react";
import { ToolStep } from "true-north-ui";

// A finished governed-tool timeline, exactly as a completed turn shows it.
export const CompletedTimeline = () => (
  <div>
    <ToolStep name="get_kg_schema" args={{}} status="complete" />
    <ToolStep name="resolve_term" args={{ term: "margin" }} status="complete" />
    <ToolStep name="get_metric_context" args={{ metric_key: "gross_margin" }} status="complete" />
    <ToolStep
      name="query_warehouse"
      args={{ metric: "gross_margin", group_by: "category" }}
      status="complete"
    />
  </div>
);

// Mid-run: earlier steps done, the query still spinning.
export const RunningStep = () => (
  <div>
    <ToolStep name="resolve_term" args={{ term: "net revenue" }} status="complete" />
    <ToolStep
      name="query_warehouse"
      args={{ metric: "net_revenue", group_by: "region", time_grain: "month" }}
      status="running"
    />
  </div>
);
