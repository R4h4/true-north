# Research Report: OSS for harness → dynamic charts, dashboards, and multi-format reports

Date: 2026-07-11 · 3 web searches (Databricks, Microsoft Research, arXiv/VegaChat, McKinsey/Vizro, Evidence.dev, Streamlit)

## Executive Summary

**Recommendation: don't adopt a dashboard *product* — adopt a chart *grammar*.** The 2026 consensus for LLM-generated visualization (Databricks multi-agent blog, VegaChat paper, Microsoft's new Flint language which itself compiles to Vega-Lite) is: have the model emit a **declarative Vega-Lite JSON spec**, validate it against the schema, render natively. Streamlit (already our UI) renders it with one call — `st.vega_lite_chart`. Everything else (dashboard, exports for humans/BI/analytics tools) is composable from what we already have, in ~100 lines total. Framework products (Vizro, Evidence.dev) drag in a second web stack and fight our `tn`-only data path the same way WrenAI did.

Fit with our stack is unusually good: `tn query` already returns `columns[]: {name, type, unit}` + `rows` — that's exactly what a Vega-Lite encoding needs; and spec-validation-with-retry is the same self-correction pattern the contract already teaches the agent (`METRIC_NOT_FOUND.candidates`, `did_you_mean`).

## Key Findings

### 1. Charts: agent-emitted Vega-Lite spec (Tier 1 — do this)

- Add a `render_chart` **function tool**: model passes `{vega_lite_spec, title}` — spec WITHOUT data; harness injects the last query result's rows as inline `values` (saves tokens, prevents the model inventing numbers).
- Validate spec against the Vega-Lite JSON schema before render; on failure, return the validation error as the tool result — model self-corrects in one turn (VegaChat's finding: error-correction loop nearly eliminates invalid charts vs LIDA-style one-shot).
- Render: `st.vega_lite_chart(spec_with_data)`. Zero new services; one pip dep (`jsonschema`, optional).
- Why not LLM-generated Plotly/matplotlib code: executing generated code is a risk + failure mode; declarative JSON avoids both (2026 best practice per Databricks/Microsoft).
- Watch (not adopt): Microsoft **Flint** + `flint-chart-mcp` — higher-level chart language compiling to Vega-Lite; brand-new, MCP plumbing not worth it this week.

### 2. Dashboard: pin-to-dashboard in Streamlit (Tier 1)

- "📌 Pin" button per rendered chart → append `{spec, data, title, persona, provenance}` to `st.session_state.dashboard` → second tab/page lays them out in a grid. Dynamic dashboard with zero new infra.
- Persona-scoped by construction: pinned charts carry the `applied_permissions` of the query that made them — a governance demo beat for free ("Đức's dashboard only shows South").

### 3. Reports: one result object, three serializations (Tier 1)

From the same `{columns, rows}` + `metadata` envelope, via pandas:

| Audience | Format | How |
|---|---|---|
| Human | Markdown report: agent narrative + chart + caveats/constraints + `applied_permissions` + `provenance.compiled_sql` appendix | agent writes it; `st.download_button`; (PDF later via any md→pdf if ever needed) |
| BI tools | CSV / **XLSX** | `df.to_csv()` / `df.to_excel()` (openpyxl) download buttons |
| Analytics tools | **Parquet** | `df.to_parquet()` (pyarrow) — typed, unit metadata in column names or a sidecar sheet |

~50 lines total, all Apache/BSD-licensed deps.

### 4. Tier 2 (only if time remains)

- **streamlit-pivot-table** (official Streamlit component): interactive pivoting, drill-down, subtotals, built-in Excel/CSV export — a strong "analyst persona" beat with one dependency.

### 5. Rejected

| Option | Why not |
|---|---|
| **Vizro / Vizro-AI** (McKinsey) | Vizro-AI dashboard generation officially no longer developed (superseded by Vizro-MCP, which targets Claude-Desktop/Cursor-style clients, not an embedded agent); Vizro is Dash-based — a second web framework beside Streamlit. |
| **Evidence.dev** | Nice BI-as-code, but a Node build-step static-site generator whose data model is SQL-against-sources — conflicts with the `tn`-only path; wrong shape for a chat agent. |
| **Superset / Metabase / Lightdash** | Full BI servers; same fatal pattern as WrenAI (own the semantic layer + direct DB access), plus heavy on the t3.xlarge. |

## Implementation sketch (phase-3/phase-6 sized)

```python
# tools.py addition
RENDER_CHART = {
  "type": "function", "name": "render_chart",
  "description": "Render a Vega-Lite chart of the LAST query result. Spec must NOT include data.",
  "parameters": {"type": "object", "properties": {
      "title": {"type": "string"},
      "vega_lite_spec": {"type": "object"}}, "required": ["vega_lite_spec"]}}

def handle_render_chart(spec, last_result):
    df_cols = [c["name"] for c in last_result["columns"]]
    spec["data"] = {"values": [dict(zip(df_cols, r)) for r in last_result["rows"]]}
    errors = validate_vega_lite(spec)          # jsonschema; return errors → model retries
    return errors or {"status": "rendered"}    # harness stores spec for st.vega_lite_chart
```

## Next Steps

1. Add `render_chart` tool + spec validation to phase-3 scope (small; same session).
2. Add pin-to-dashboard tab + 3 download buttons (md/xlsx/parquet) to phase-6 demo polish.
3. Skip Flint/Vizro/Evidence; revisit streamlit-pivot-table only after trap evals pass.

## Unresolved Questions

- None blocking. Minor: whether GPT-5.5 needs few-shot Vega-Lite examples in the system prompt (test on stub fixtures; VegaChat suggests schema-validation retry matters more than few-shots).

## Sources

- [Databricks: Visualizations in multi-agent systems with Vega-Lite](https://www.databricks.com/blog/bringing-visualizations-life-multi-agent-systems-vega-lite)
- [VegaChat: LLM chart generation + assessment (arXiv 2026)](https://arxiv.org/html/2601.15385v1) · [Vega-Lite](https://vega.github.io/vega-lite/)
- [Microsoft Flint (compiles to Vega-Lite) + flint-chart-mcp](https://www.microsoft.com/en-us/research/blog/flint-a-visualization-language-for-the-ai-era/)
- [Vizro repo](https://github.com/mckinsey/vizro) (README: Vizro-AI dashboard gen superseded by Vizro-MCP)
- [Evidence.dev](https://evidence.dev/) · [streamlit-pivot-table](https://github.com/streamlit/streamlit-pivot-table)
