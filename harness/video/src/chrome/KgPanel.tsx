// Mini knowledge-graph panel: typed nodes positioned by percent over an SVG
// edge layer, ported from harness/ui/components/kg-panel.tsx. Nodes reveal
// progressively; locked nodes render red with a lock glyph; a highlight set
// emphasises the provenance path.
import React from "react";
import { C } from "../theme/tokens";
import { FONT_SANS, FONT_MONO } from "../theme/fonts";

export type KgType = "Concept" | "Metric" | "Dimension" | "Constraint" | "Table";
export type KgNode = { id: string; type: KgType; name: string; x: number; y: number; locked?: boolean };
export type KgEdge = { from: string; to: string; label?: string };

const STYLE: Record<KgType, { bg: string; border: string; chip: string; mono?: boolean }> = {
  Concept: { bg: C.accentTint, border: "#dcd2fa", chip: C.accentDark },
  Metric: { bg: C.surface, border: C.borderStrong, chip: C.navy, mono: true },
  Dimension: { bg: C.blueTint, border: "#cfe0f5", chip: "#3b5a8a", mono: true },
  Constraint: { bg: C.amberTint, border: "#ecd9b0", chip: C.amber },
  Table: { bg: C.surfaceSubtle, border: C.borderStrong, chip: C.muted, mono: true },
};

export const KgPanel: React.FC<{
  nodes: KgNode[];
  edges: KgEdge[];
  reveal?: number; // 0..1 fraction of nodes shown (by index order)
  highlight?: string[];
}> = ({ nodes, edges, reveal = 1, highlight = [] }) => {
  const shown = Math.ceil(nodes.length * reveal);
  const visible = new Set(nodes.slice(0, shown).map((n) => n.id));
  const pos = new Map(nodes.map((n) => [n.id, { x: n.x, y: n.y }]));

  return (
    <div style={{ position: "absolute", inset: 0, fontFamily: FONT_SANS }}>
      <svg width="100%" height="100%" style={{ position: "absolute", inset: 0 }}>
        {edges.map((e, i) => {
          const a = pos.get(e.from);
          const b = pos.get(e.to);
          if (!a || !b || !visible.has(e.from) || !visible.has(e.to)) return null;
          const on = highlight.includes(e.from) && highlight.includes(e.to);
          return (
            <g key={i}>
              <line
                x1={`${a.x}%`}
                y1={`${a.y}%`}
                x2={`${b.x}%`}
                y2={`${b.y}%`}
                stroke={on ? C.accent : C.borderStrong}
                strokeWidth={on ? 2.4 : 1.5}
              />
              {e.label && (
                <text
                  x={`${(a.x + b.x) / 2}%`}
                  y={`${(a.y + b.y) / 2}%`}
                  dy={a.y === b.y ? -10 : 0}
                  textAnchor="middle"
                  fontSize={10}
                  letterSpacing="0.05em"
                  fill={on ? C.accentDark : C.muted}
                  stroke={C.surfaceSubtle}
                  strokeWidth={3}
                  paintOrder="stroke"
                  fontFamily={FONT_MONO}
                >
                  {e.label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {nodes.slice(0, shown).map((n) => {
        const s = STYLE[n.type];
        const locked = n.locked;
        const hi = highlight.includes(n.id);
        return (
          <div
            key={n.id}
            style={{
              position: "absolute",
              left: `${n.x}%`,
              top: `${n.y}%`,
              transform: "translate(-50%, -50%)",
              maxWidth: 190,
            }}
          >
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 2,
                padding: "7px 11px",
                borderRadius: 8,
                background: locked ? C.redTint : s.bg,
                border: `1px solid ${locked ? C.red : hi ? C.accent : s.border}`,
                boxShadow: hi ? `0 0 0 3px rgba(124,92,240,0.16)` : "0 1px 2px rgba(6,10,31,0.06)",
                whiteSpace: "nowrap",
              }}
            >
              <div
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: "0.09em",
                  textTransform: "uppercase",
                  color: locked ? C.red : s.chip,
                }}
              >
                {locked ? `${n.type} · restricted` : n.type}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                {locked && (
                  <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
                    <rect x="2" y="5" width="8" height="6" rx="1.5" fill={C.red} />
                    <path d="M4 5.2 V3.8 a2 2 0 0 1 4 0 V5.2" fill="none" stroke={C.red} strokeWidth="1.5" />
                  </svg>
                )}
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: s.mono ? 500 : 600,
                    fontFamily: s.mono ? FONT_MONO : FONT_SANS,
                    color: locked ? C.red : s.chip,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {n.name}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
