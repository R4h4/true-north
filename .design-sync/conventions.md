# True North UI — build conventions

True North is a governed-BI workbench (Holistics-inspired light theme, Vietnamese retail data). Components render standalone — **no provider or theme wrapper is required**. Import everything from `window.TrueNorthUI`.

## Styling idiom: CSS custom properties + a small shipped class vocabulary

Style your own layout glue with the design tokens defined in `tokens/globals.css` (`:root`), never raw hex:

| Token | Use |
|---|---|
| `--ink`, `--ink-secondary`, `--muted` | text: primary / secondary / hints & labels |
| `--bg-app`, `--surface`, `--surface-subtle` | page background / white cards / card footers & side panes |
| `--border`, `--border-strong` | hairline card borders / control borders |
| `--green`, `--green-dark`, `--green-tint` | brand + primary actions / hover text / pill & hover fills |
| `--navy` | data ink (chart bars) — not for UI chrome |
| `--blue-tint` | user chat bubbles |
| `--red`, `--red-tint` | negative values, locked/denied governance states |
| `--amber` | warnings |
| `--shadow-card` | the only shadow — cards sit on hairlines, not depth |
| `--font-inter` | body font family (Inter, loaded by `styles.css`) |

Reusable classes shipped in the stylesheet: `chart-card` + `card-footer` (the answer-card surface: white, 10px radius, hairline border, attribution footer), `kpi-body`/`kpi-label`/`kpi-value`/`kpi-sub` (stat cards), `tool-step`/`step-label`/`step-args`/`step-spinner` (timeline rows), `thoughts`/`thoughts-toggle`/`thoughts-body` (collapsible reasoning), `ask-user-card` (HITL choices), `hint` (muted helper text), and the shell chrome `topbar`/`brand`/`tag`/`persona-picker`. Invent no new visual language: new surfaces are white cards with `1px solid var(--border)`, radius 8–10px, `var(--shadow-card)`.

## Page structure: viewport-locked shell

`tokens/globals.css` locks `body` to the viewport (`height: 100vh; overflow: hidden`). Build pages the way the product does — a grid shell whose panes scroll internally:

```jsx
const { ChartView, ToolStep, Thoughts, BrandMark } = window.TrueNorthUI;

<div style={{ display: "grid", gridTemplateRows: "52px 1fr", height: "100vh" }}>
  <div className="topbar"><div className="brand"><BrandMark /><h1>True North</h1></div></div>
  <main style={{ overflowY: "auto", padding: 20, background: "var(--bg-app)" }}>
    <ToolStep name="query_warehouse" args={{ metric: "net_revenue", group_by: "region" }} status="complete" />
    <ChartView chart={{ type: "bar", title: "Net revenue by region", x_label: "region",
      y_label: "net revenue", y_format: "vnd", as_of: "2025-12-31",
      points: [{ x: "South", y: 2612000000000 }, { x: "North", y: 2144000000000 }] }} />
  </main>
</div>
```

## Component notes

- `ChartView` draws its own card + footer — never wrap it in another card. `type: "kpi"` needs exactly one point; `y_format: "vnd"` renders tỷ/tr; negative values render red automatically.
- `ToolStep` renders nothing for tool names outside its governed list (`get_kg_schema`, `resolve_term`, `get_metric_context`, `check_metric_access`, `list_metrics`, `describe_metric`, `query_warehouse`).
- `Thoughts` with `live: true` is expanded; `live: false` collapses to a toggle.
- Locked/denied governance states are red (`--red` border, `--red-tint` fill) with a lock glyph — see `KgPanel`.

## Where the truth lives

Read `styles.css` → `tokens/globals.css` (all tokens and classes above) and each component's `<Name>.d.ts` + `<Name>.prompt.md` before styling. Numbers are VND; use tabular figures and Vietnamese formats where the components don't already do it for you.
