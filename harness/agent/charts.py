"""Chart tool: the model never touches row data.

render_chart reads the rows from the LAST successful query_warehouse envelope
(stashed in the per-run cache), so the numbers in a chart are always the
governed numbers - the model only chooses chart type and title. The tool
result streams to the UI as a tool-call event; the frontend renders it as an
inline SVG chart.
"""

from strands import tool

from agent.tools import _run_cache

_FORMATS = {"ratio": "percent", "VND": "vnd"}


def _column_format(col: dict) -> str:
    return _FORMATS.get(col.get("unit") or "", _FORMATS.get(col.get("type") or "", "number"))


@tool
def render_chart(chart_type: str, title: str) -> dict:
    """Visualize the rows of your MOST RECENT successful query_warehouse call
    as an inline chart. Call this once after any query that returns 2 or more
    rows, BEFORE narrating the numbers. chart_type: 'bar' for categorical
    breakdowns, 'line' for time series. The data comes from the governed
    envelope - you never pass numbers."""
    if chart_type not in ("bar", "line"):
        return {"ok": False, "error": "chart_type must be 'bar' or 'line'"}
    try:
        stash = _run_cache.get().get("__last_query__")
    except LookupError:
        stash = None
    if not stash:
        return {"ok": False, "error": "no successful query_warehouse result this turn - query first"}

    result = stash.get("result") or {}
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    if len(columns) < 2 or len(rows) < 2:
        return {"ok": False, "error": "need at least 2 rows and 2 columns to chart - narrate in prose instead"}

    # First non-numeric column is x, first ratio/number column is y.
    x_idx = next((i for i, c in enumerate(columns) if c.get("type") in ("categorical", "date", "month")), 0)
    y_idx = next((i for i, c in enumerate(columns) if i != x_idx), 1)
    y_col = columns[y_idx]
    chart = {
        "type": chart_type,
        "title": title,
        "x_label": columns[x_idx].get("name"),
        "y_label": y_col.get("name"),
        "y_format": _column_format(y_col),
        "points": [{"x": str(r[x_idx]), "y": r[y_idx]} for r in rows if r[y_idx] is not None],
        "as_of": (stash.get("metadata") or {}).get("as_of"),
    }
    return {"ok": True, "chart": chart, "_note": "chart is now displayed inline - do not repeat its numbers as a table, just give the readout"}
