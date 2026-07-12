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

# Column roles. Everything that is not a dimension is treated as the numeric
# measure (money, number, ratio, int, ...). Time columns can also serve as the
# x-axis of a line.
_DIM_TYPES = ("categorical", "geo", "time", "date", "month", "string", "text", "bool", "boolean")
_TIME_TYPES = ("time", "date", "month")


def _column_format(col: dict) -> str:
    return _FORMATS.get(col.get("unit") or "", _FORMATS.get(col.get("type") or "", "number"))


def _is_measure(col: dict) -> bool:
    return (col.get("type") or "") not in _DIM_TYPES


def _build_chart(chart_type: str, title: str, stash: dict) -> dict:
    """Shape a governed query envelope into a chart payload. Pure (no context
    or IO) so it is unit-testable; render_chart just supplies the stash.

    The measure is always the numeric column - never a dimension. A result with
    a time column, a second dimension, and a measure (e.g. GMV by month by
    channel) becomes a MULTI-SERIES line: one line per second-dimension value,
    x = time. Bars/hbars stay single-series.
    """
    result = stash.get("result") or {}
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    as_of = (stash.get("metadata") or {}).get("as_of")

    # The measure column: the (first) non-dimension column; fall back to the
    # last column so we never pick a dimension as the y-value.
    measure_idx = next((i for i, c in enumerate(columns) if _is_measure(c)), len(columns) - 1)

    if chart_type == "kpi":
        if len(rows) != 1:
            return {"ok": False, "error": "'kpi' is for single-row results - use 'bar'/'hbar'/'line' for breakdowns"}
        y_col = columns[measure_idx]
        chart = {
            "type": "kpi",
            "title": title,
            "x_label": "",
            "y_label": y_col.get("name"),
            "y_format": _column_format(y_col),
            "points": [{"x": str(y_col.get("name")), "y": rows[0][measure_idx]}],
            "as_of": as_of,
        }
        return {"ok": True, "chart": chart, "_note": "KPI card is now displayed inline - give the readout, do not repeat the number as a table"}

    if len(columns) < 2 or len(rows) < 2:
        return {"ok": False, "error": "need at least 2 rows and 2 columns - for a single value use chart_type 'kpi'"}

    y_col = columns[measure_idx]
    dim_idxs = [i for i in range(len(columns)) if i != measure_idx]
    time_idx = next((i for i in dim_idxs if (columns[i].get("type") in _TIME_TYPES)), None)

    # x-axis: the time column for a line, otherwise the first dimension.
    x_idx = time_idx if (chart_type == "line" and time_idx is not None) else (dim_idxs[0] if dim_idxs else 0)
    # A second dimension turns a line into one series per value (e.g. one line
    # per channel). Only lines fan out; bars/hbars stay single-series.
    series_idx = next((i for i in dim_idxs if i != x_idx), None) if chart_type == "line" else None

    base = {
        "type": chart_type,
        "title": title,
        "x_label": columns[x_idx].get("name"),
        "y_label": y_col.get("name"),
        "y_format": _column_format(y_col),
        "as_of": as_of,
    }

    if series_idx is not None:
        # Group into one series per distinct second-dimension value, first-seen
        # order preserved. x stays the time axis; the frontend orders x itself.
        groups: dict[str, list] = {}
        for r in rows:
            if r[measure_idx] is None:
                continue
            groups.setdefault(str(r[series_idx]), []).append({"x": str(r[x_idx]), "y": r[measure_idx]})
        chart = {**base, "points": [], "series": [{"name": n, "points": p} for n, p in groups.items()]}
        return {"ok": True, "chart": chart, "_note": "multi-series chart is now displayed inline - give the readout per series, do not repeat numbers as a table"}

    chart = {**base, "points": [{"x": str(r[x_idx]), "y": r[measure_idx]} for r in rows if r[measure_idx] is not None]}
    return {"ok": True, "chart": chart, "_note": "chart is now displayed inline - do not repeat its numbers as a table, just give the readout"}


@tool
def render_chart(chart_type: str, title: str) -> dict:
    """Visualize the rows of your MOST RECENT successful query_warehouse call
    as an inline chart. Call this once after EVERY successful query, BEFORE
    narrating the numbers. chart_type: 'kpi' for a single-value result (one
    row), 'bar' for a categorical breakdown of up to 4 items, 'hbar' for
    rankings or 5+ categories (reads best with long names), 'line' for time
    series. A 'line' over a result grouped by BOTH time and one dimension
    (e.g. by month by channel) automatically draws one line per dimension
    value - so a "metric by month by channel" request is a single 'line' call.
    The data comes from the governed envelope - you never pass numbers."""
    if chart_type not in ("bar", "hbar", "line", "kpi"):
        return {"ok": False, "error": "chart_type must be 'kpi', 'bar', 'hbar' or 'line'"}
    try:
        stash = _run_cache.get().get("__last_query__")
    except LookupError:
        stash = None
    if not stash:
        return {"ok": False, "error": "no successful query_warehouse result this turn - query first"}
    return _build_chart(chart_type, title, stash)
