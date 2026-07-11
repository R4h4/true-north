"use client";

// Human-readable labels for the governed tools; the step timeline renders
// only tools listed here (render_chart / ask_user have their own renderers).
const TOOL_STEPS: Record<string, string> = {
  get_kg_schema: "Loading knowledge-graph schema",
  resolve_term: "Resolving business term",
  get_metric_context: "Loading metric context",
  check_metric_access: "Checking metric access",
  list_metrics: "Listing governed metrics",
  describe_metric: "Inspecting metric definition",
  query_warehouse: "Running governed query",
};

const ARG_KEYS = ["term", "metric_key", "metric_keys", "metric", "group_by", "time_grain", "filter", "start", "end"];

function argSummary(args: any): string {
  if (!args || typeof args !== "object") return "";
  const parts: string[] = [];
  for (const key of ARG_KEYS) {
    const v = args[key];
    if (v && String(v).trim()) parts.push(`${key}=${Array.isArray(v) ? v.join(",") : v}`);
  }
  return parts.join("  ");
}

function StepCheck() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <path d="M2.5 6.5 5 9l4.5-6" stroke="#259b6c" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// One row of the agent's visible act loop: tool choice + arguments, live.
export function ToolStep({ name, args, status }: { name: string; args: any; status: string }) {
  const label = TOOL_STEPS[name];
  if (!label) return <></>;
  return (
    <div className="tool-step">
      {status === "complete" ? <StepCheck /> : <span className="step-spinner" aria-label="running" />}
      <span className="step-label">{label}</span>
      <span className="step-args">{argSummary(args)}</span>
    </div>
  );
}
