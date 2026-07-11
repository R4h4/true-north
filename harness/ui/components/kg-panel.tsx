"use client";

import type { CSSProperties } from "react";
import { BrandMark } from "./brand-mark";

// Card-node rendering of the agent's accumulated KG subgraph (shared state
// `kg_context` from the backend). Nodes are typed cards — colored chip +
// name — positioned in horizontal bands per label (Concept on top, Table at
// the bottom) over an SVG edge layer with mono relationship labels. Locked
// nodes show governance visually (red card + lock glyph); freshly-discovered
// nodes pop in and pulse. A type legend closes the pane.

type KgNode = { id: string; label: string; name: string; locked: boolean; new: boolean };
type KgEdge = { source: string; target: string; label: string };
export type KgGraph = { nodes: KgNode[]; edges: KgEdge[] };

const BAND_ORDER = ["Concept", "Metric", "Dimension", "Constraint", "Table"];

const MONO = "var(--font-mono), ui-monospace, SFMono-Regular, Menlo, monospace";
const TYPE_STYLES: Record<string, { bg: string; border: string; chip: string; name: CSSProperties }> = {
  Concept: { bg: "var(--accent-tint)", border: "#dcd2fa", chip: "var(--accent-dark)", name: { fontSize: 12.5, fontWeight: 600, color: "var(--accent-dark)" } },
  Metric: { bg: "var(--surface)", border: "var(--border-strong)", chip: "var(--navy)", name: { fontSize: 12, fontFamily: MONO, color: "var(--navy)", fontWeight: 500 } },
  Dimension: { bg: "var(--blue-tint)", border: "#cfe0f5", chip: "#3b5a8a", name: { fontSize: 12, fontFamily: MONO, color: "#21324e" } },
  Constraint: { bg: "#fdf6e3", border: "#ecd9b0", chip: "var(--amber)", name: { fontSize: 12, color: "var(--amber)", fontWeight: 500 } },
  Table: { bg: "var(--surface-subtle)", border: "var(--border-strong)", chip: "var(--muted)", name: { fontSize: 12, fontFamily: MONO, color: "var(--ink-secondary)" } },
};
const FALLBACK_STYLE = TYPE_STYLES.Table;

const LEGEND: { label: string; bg: string; border: string }[] = [
  { label: "Concept", bg: "var(--accent-tint)", border: "#dcd2fa" },
  { label: "Metric", bg: "var(--surface)", border: "var(--navy)" },
  { label: "Dimension", bg: "var(--blue-tint)", border: "#cfe0f5" },
  { label: "Table", bg: "var(--surface-subtle)", border: "var(--border-strong)" },
  { label: "Restricted", bg: "var(--red-tint)", border: "var(--red)" },
];

function LockGlyph() {
  return (
    <svg width="10" height="10" viewBox="0 0 12 12" style={{ flexShrink: 0 }} aria-hidden="true">
      <rect x="2" y="5" width="8" height="6" rx="1.5" fill="var(--red)" />
      <path d="M4 5.2 V3.8 a2 2 0 0 1 4 0 V5.2" fill="none" stroke="var(--red)" strokeWidth="1.5" />
    </svg>
  );
}

export function KgPanel({ graph }: { graph?: KgGraph }) {
  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];

  if (nodes.length === 0) {
    return (
      <div className="kg-empty">
        <BrandMark size={34} tone="muted" />
        <p>Entities appear here as the agent resolves your question against the semantic layer.</p>
      </div>
    );
  }

  // Percent-based positions: one horizontal band per label, nodes spread
  // evenly within their band. Small graphs (a governed turn touches ~6-12
  // entities) stay readable without a force layout. Bands wider than the pane
  // can hold (3 cards) wrap onto extra rows, and each card is width-capped to
  // its row slot so neighbors can never overlap.
  const MAX_PER_ROW = 3;
  const bands = BAND_ORDER.filter((label) => nodes.some((n) => n.label === label));
  const extra = [...new Set(nodes.map((n) => n.label))].filter((l) => !bands.includes(l));
  const rows: KgNode[][] = [...bands, ...extra].flatMap((label) => {
    const group = nodes.filter((n) => n.label === label);
    const chunks: KgNode[][] = [];
    for (let i = 0; i < group.length; i += MAX_PER_ROW) chunks.push(group.slice(i, i + MAX_PER_ROW));
    return chunks;
  });
  // Centers at (i+0.5)/n use the full pane width; `slot` is the horizontal
  // span each card may occupy before it would touch its neighbor.
  const pos = new Map<string, { x: number; y: number; slot: number }>();
  rows.forEach((row, bi) => {
    row.forEach((node, i) => {
      pos.set(node.id, {
        x: ((i + 0.5) / row.length) * 100,
        y: ((bi + 1) / (rows.length + 1)) * 100,
        slot: 100 / row.length,
      });
    });
  });

  // A fan of same-label edges from one node (metric HAS_DIMENSION x7) piles
  // its labels onto overlapping midpoints - label only the middle edge.
  const fanKey = (e: KgEdge) => `${e.source}|${e.label}`;
  const fanSize = new Map<string, number>();
  edges.forEach((e) => fanSize.set(fanKey(e), (fanSize.get(fanKey(e)) ?? 0) + 1));
  const fanSeen = new Map<string, number>();
  const showLabel = edges.map((e) => {
    const k = fanKey(e);
    const idx = fanSeen.get(k) ?? 0;
    fanSeen.set(k, idx + 1);
    return idx === Math.floor((fanSize.get(k)! - 1) / 2);
  });

  return (
    <>
      {/* min-height by band count: cramped panes scroll instead of piling
          rows onto each other */}
      <div className="kg-graph" style={{ minHeight: rows.length * 56 }}>
        <svg width="100%" height="100%" style={{ position: "absolute", inset: 0, display: "block" }}>
          {edges.map((edge, i) => {
            const a = pos.get(edge.source);
            const b = pos.get(edge.target);
            if (!a || !b) return null;
            return (
              <g key={i} style={{ animation: "tn-edge .4s ease both" }}>
                <line x1={`${a.x}%`} y1={`${a.y}%`} x2={`${b.x}%`} y2={`${b.y}%`} stroke="var(--border-strong)" strokeWidth={1.5} />
                {showLabel[i] ? (
                  <text
                    x={`${(a.x + b.x) / 2}%`}
                    y={`${(a.y + b.y) / 2}%`}
                    /* same-row edges: the midpoint sits between the two cards,
                       which paint over the SVG - lift the label above them */
                    dy={a.y === b.y ? -30 : 0}
                    textAnchor="middle"
                    fontSize={9.5}
                    letterSpacing="0.05em"
                    fill="var(--muted)"
                    stroke="var(--surface-subtle)"
                    strokeWidth={3}
                    paintOrder="stroke"
                    fontFamily={MONO}
                  >
                    {edge.label}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
        {nodes.map((node) => {
          const p = pos.get(node.id);
          if (!p) return null;
          const ts = TYPE_STYLES[node.label] ?? FALLBACK_STYLE;
          return (
            <div
              key={node.id}
              className="kg-node"
              style={{ left: `${p.x}%`, top: `${p.y}%`, maxWidth: `calc(${p.slot}% - 10px)` }}
              title={node.name}
            >
              <div
                className="kg-node-card"
                style={{
                  background: node.locked ? "var(--red-tint)" : ts.bg,
                  borderColor: node.locked ? "var(--red)" : ts.border,
                  animation: node.new ? "tn-pulse 1.4s ease 2" : "none",
                }}
              >
                <div className="kg-node-type" style={{ color: node.locked ? "var(--red)" : ts.chip }}>
                  {node.locked ? `${node.label} · restricted` : node.label}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  {node.locked && <LockGlyph />}
                  <span className="kg-node-name" style={{ ...ts.name, ...(node.locked ? { color: "var(--red)" } : null) }}>
                    {node.name}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="kg-legend">
        {LEGEND.map((item) => (
          <span key={item.label}>
            <span className="kg-legend-swatch" style={{ background: item.bg, borderColor: item.border }} />
            {item.label}
          </span>
        ))}
      </div>
    </>
  );
}
