"use client";

// Vertical-band rendering of the agent's accumulated KG subgraph (shared
// state `kg_context` from the backend). One band per node label, stacked
// top-to-bottom (Concept -> Metric -> ... ) so the graph fits the tall,
// narrow side pane at readable scale. Locked nodes show governance visually;
// freshly-discovered nodes pulse.

type KgNode = { id: string; label: string; name: string; locked: boolean; new: boolean };
type KgEdge = { source: string; target: string; label: string };
export type KgGraph = { nodes: KgNode[]; edges: KgEdge[] };

const BAND_ORDER = ["Concept", "Metric", "Dimension", "Constraint", "Table"];
const COLORS: Record<string, string> = {
  Concept: "#8b7bd8",
  Metric: "#3f9d6e",
  Dimension: "#3a7fc2",
  Constraint: "#c2803a",
  Table: "#697086",
};
const W = 430;
const NODE_W = 196;
const NODE_H = 36;
const GAP_X = 14;
const ROW_GAP = 10;
const BAND_GAP = 46; // room for edge labels between bands
const PER_ROW = 2;
const PAD = 10;

export function KgPanel({ graph }: { graph?: KgGraph }) {
  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];

  if (nodes.length === 0) {
    return <p className="hint" style={{ padding: 16 }}>Ask a question — the graph fills in as the agent explores the knowledge graph.</p>;
  }

  // Lay out bands top-to-bottom, wrapping nodes 2-per-row inside a band.
  const bands = BAND_ORDER.filter((label) => nodes.some((n) => n.label === label));
  const extra = [...new Set(nodes.map((n) => n.label))].filter((l) => !bands.includes(l));
  const pos = new Map<string, { x: number; y: number }>();
  let y = PAD + 14;
  for (const label of [...bands, ...extra]) {
    const group = nodes.filter((n) => n.label === label);
    group.forEach((node, i) => {
      pos.set(node.id, {
        x: PAD + (i % PER_ROW) * (NODE_W + GAP_X),
        y: y + Math.floor(i / PER_ROW) * (NODE_H + ROW_GAP),
      });
    });
    y += Math.ceil(group.length / PER_ROW) * (NODE_H + ROW_GAP) + BAND_GAP;
  }
  const height = y - BAND_GAP + PAD;

  return (
    <svg viewBox={`0 0 ${W} ${height}`} width="100%" style={{ display: "block" }}>
      {edges.map((edge, i) => {
        const s = pos.get(edge.source);
        const t = pos.get(edge.target);
        if (!s || !t) return null;
        // Connect bottom-center of the higher node to top-center of the lower.
        const [top, bot] = s.y <= t.y ? [s, t] : [t, s];
        const x1 = top.x + NODE_W / 2;
        const y1 = top.y + NODE_H;
        const x2 = bot.x + NODE_W / 2;
        const y2 = bot.y;
        const my = (y1 + y2) / 2;
        return (
          <g key={i}>
            <path
              d={`M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`}
              fill="none" stroke="#3a4054" strokeWidth={1.2} opacity={0.9}
            />
            <text x={(x1 + x2) / 2} y={my + 3} fontSize={8.5} fill="#6b7390" textAnchor="middle">
              {edge.label}
            </text>
          </g>
        );
      })}
      {nodes.map((node) => {
        const p = pos.get(node.id);
        if (!p) return null;
        const color = COLORS[node.label] ?? "#697086";
        return (
          <g key={node.id}>
            <rect
              x={p.x} y={p.y} width={NODE_W} height={NODE_H} rx={7}
              fill={node.new ? color : "#171b26"}
              stroke={node.locked ? "#d05c5c" : color}
              strokeWidth={node.new ? 2 : 1.2}
            >
              {node.new && (
                <animate attributeName="opacity" values="0.4;1" dur="0.6s" repeatCount="2" />
              )}
            </rect>
            <text x={p.x + 9} y={p.y + 15} fontSize={12} fontWeight={600}
              fill={node.new ? "#fff" : "#dde2ee"}>
              {node.locked ? "🔒 " : ""}{node.name.length > 26 ? node.name.slice(0, 25) + "…" : node.name}
            </text>
            <text x={p.x + 9} y={p.y + 29} fontSize={9.5}
              fill={node.new ? "#e8ecf5" : "#7d859c"}>
              {node.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
