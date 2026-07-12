"""Chart payload shaping — regression tests for _build_chart.

Guards the multi-series bug: a query grouped by BOTH time and a dimension
(GMV by month by channel) must chart the numeric measure as y and fan out one
series per dimension value — never plot a dimension column as the y-value.
"""

from agent.charts import _build_chart


def _stash(columns, rows, as_of="2025-12-31"):
    return {"result": {"columns": columns, "rows": rows}, "metadata": {"as_of": as_of}}


TIME = {"name": "date", "type": "time", "unit": None}
CHANNEL = {"name": "channel", "type": "categorical", "unit": None}
MONEY = {"name": "gmv_gross", "type": "money", "unit": "VND"}


def test_line_time_by_dimension_is_multi_series():
    # [time, category, measure] -> one line per category, measure as y.
    stash = _stash(
        [TIME, CHANNEL, MONEY],
        [
            ["2025-01-01", "app", 21_000_000_000],
            ["2025-01-01", "b2b", 212_000_000_000],
            ["2025-02-01", "app", 22_000_000_000],
            ["2025-02-01", "b2b", 210_000_000_000],
        ],
    )
    out = _build_chart("line", "GMV by month by channel", stash)
    assert out["ok"]
    chart = out["chart"]
    assert chart["x_label"] == "date" and chart["y_label"] == "gmv_gross"
    assert chart["y_format"] == "vnd"
    assert {s["name"] for s in chart["series"]} == {"app", "b2b"}
    # y is always the numeric measure, never a dimension string.
    ys = [p["y"] for s in chart["series"] for p in s["points"]]
    assert all(isinstance(y, int) for y in ys)
    app = next(s for s in chart["series"] if s["name"] == "app")
    assert app["points"] == [
        {"x": "2025-01-01", "y": 21_000_000_000},
        {"x": "2025-02-01", "y": 22_000_000_000},
    ]


def test_measure_is_never_a_dimension_even_if_columns_reordered():
    # Measure first, then two dimensions: still picks the measure as y.
    stash = _stash(
        [MONEY, CHANNEL, TIME],
        [[5, "app", "2025-01-01"], [6, "b2b", "2025-01-01"]],
    )
    chart = _build_chart("line", "t", stash)["chart"]
    assert chart["y_label"] == "gmv_gross"
    assert chart["x_label"] == "date"  # time is the x-axis of a line
    assert {s["name"] for s in chart["series"]} == {"app", "b2b"}


def test_single_series_line_has_no_series_key():
    stash = _stash([TIME, MONEY], [["2025-01-01", 5], ["2025-02-01", 7]])
    chart = _build_chart("line", "trend", stash)["chart"]
    assert "series" not in chart
    assert chart["points"] == [{"x": "2025-01-01", "y": 5}, {"x": "2025-02-01", "y": 7}]


def test_bar_stays_single_series_with_measure_as_y():
    stash = _stash(
        [{"name": "category", "type": "categorical"}, {"name": "gross_margin", "type": "money", "unit": "VND"}],
        [["Laptop", -10], ["Accessory", 42]],
    )
    chart = _build_chart("bar", "margin", stash)["chart"]
    assert "series" not in chart
    assert chart["x_label"] == "category" and chart["y_label"] == "gross_margin"
    assert chart["points"] == [{"x": "Laptop", "y": -10}, {"x": "Accessory", "y": 42}]


def test_kpi_single_row():
    stash = _stash([{"name": "net_revenue", "type": "money", "unit": "VND"}], [[999]])
    chart = _build_chart("kpi", "k", stash)["chart"]
    assert chart["type"] == "kpi"
    assert chart["points"] == [{"x": "net_revenue", "y": 999}]


def test_none_measure_rows_are_dropped():
    stash = _stash(
        [TIME, CHANNEL, MONEY],
        [["2025-01-01", "app", None], ["2025-01-01", "b2b", 5]],
    )
    chart = _build_chart("line", "t", stash)["chart"]
    assert {s["name"] for s in chart["series"]} == {"b2b"}
