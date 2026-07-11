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
    as an inline chart. Call this once after EVERY successful query, BEFORE
    narrating the numbers. chart_type: 'kpi' for a single-value result (one
    row), 'bar' for a categorical breakdown of up to 4 items, 'hbar' for
    rankings or 5+ categories (reads best with long names), 'line' for time
    series. The data comes from the governed envelope - you never pass
    numbers."""
    if chart_type not in ("bar", "hbar", "line", "kpi"):
        return {"ok": False, "error": "chart_type must be 'kpi', 'bar', 'hbar' or 'line'"}
    try:
        stash = _run_cache.get().get("__last_query__")
    except LookupError:
        stash = None
    if not stash:
        return {"ok": False, "error": "no successful query_warehouse result this turn - query first"}

    result = stash.get("result") or {}
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    as_of = (stash.get("metadata") or {}).get("as_of")

    if chart_type == "kpi":
        if len(rows) != 1:
            return {"ok": False, "error": "'kpi' is for single-row results - use 'bar'/'hbar'/'line' for breakdowns"}
        y_idx = next(
            (i for i, c in enumerate(columns) if c.get("type") not in ("categorical", "geo", "time", "date", "month")), 0
        )
        y_col = columns[y_idx]
        chart = {
            "type": "kpi",
            "title": title,
            "x_label": "",
            "y_label": y_col.get("name"),
            "y_format": _column_format(y_col),
            "points": [{"x": str(y_col.get("name")), "y": rows[0][y_idx]}],
            "as_of": as_of,
        }
        return {"ok": True, "chart": chart, "_note": "KPI card is now displayed inline - give the readout, do not repeat the number as a table"}

    if len(columns) < 2 or len(rows) < 2:
        return {"ok": False, "error": "need at least 2 rows and 2 columns - for a single value use chart_type 'kpi'"}

    # First non-numeric column is x, first ratio/number column is y.
    x_idx = next(
        (i for i, c in enumerate(columns) if c.get("type") in ("categorical", "geo", "time", "date", "month")), 0
    )
    y_idx = next((i for i, c in enumerate(columns) if i != x_idx), 1)
    y_col = columns[y_idx]
    chart = {
        "type": chart_type,
        "title": title,
        "x_label": columns[x_idx].get("name"),
        "y_label": y_col.get("name"),
        "y_format": _column_format(y_col),
        "points": [{"x": str(r[x_idx]), "y": r[y_idx]} for r in rows if r[y_idx] is not None],
        "as_of": as_of,
    }
    return {"ok": True, "chart": chart, "_note": "chart is now displayed inline - do not repeat its numbers as a table, just give the readout"}
