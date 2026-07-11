"use client";

// Layered SVG rendering of the agent's accumulated KG subgraph (shared state
// `kg_context` from the backend). Columns by node label; locked nodes show
// governance visually; freshly-discovered nodes pulse.

type KgNode = { id: string; label: string; name: string; locked: boolean; new: boolean };
type KgEdge = { source: string; target: string; label: string };
export type KgGraph = { nodes: KgNode[]; edges: KgEdge[] };

const COLUMNS = ["Concept", "Metric", "Dimension", "Constraint", "Table"];
const COLORS: Record<string, string> = {
  Concept: "#8b7bd8",
  Metric: "#3f9d6e",
  Dimension: "#3a7fc2",
  Constraint: "#c2803a",
  Table: "#697086",
};
const COL_W = 210;
const ROW_H = 44;
const NODE_W = 180;
const NODE_H = 30;

export function KgPanel({ graph }: { graph?: KgGraph }) {
  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];

  if (nodes.length === 0) {
    return <p className="hint" style={{ padding: 16 }}>Ask a question — the graph fills in as the agent explores the knowledge graph.</p>;
  }

  const pos = new Map<string, { x: number; y: number }>();
  const counts: Record<string, number> = {};
  for (const node of nodes) {
    const col = Math.max(0, COLUMNS.indexOf(node.label));
    const row = counts[node.label] ?? 0;
    counts[node.label] = row + 1;
    pos.set(node.id, { x: 20 + col * COL_W, y: 30 + row * ROW_H });
  }
  const height = 60 + Math.max(...Object.values(counts)) * ROW_H;
  const width = 40 + COLUMNS.length * COL_W;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" style={{ minHeight: height }}>
      {edges.map((edge, i) => {
        const s = pos.get(edge.source);
        const t = pos.get(edge.target);
        if (!s || !t) return null;
        return (
          <g key={i}>
            <line
              x1={s.x + NODE_W} y1={s.y + NODE_H / 2}
              x2={t.x} y2={t.y + NODE_H / 2}
              stroke="#3a4054" strokeWidth={1} opacity={0.85}
            />
            <text
              x={(s.x + NODE_W + t.x) / 2} y={(s.y + t.y) / 2 + NODE_H / 2 - 4}
              fontSize={8} fill="#59617a" textAnchor="middle"
            >
              {edge.label}
            </text>
          </g>
        );
      })}
      {nodes.map((node) => {
        const p = pos.get(node.id)!;
        const color = COLORS[node.label] ?? "#697086";
        return (
          <g key={node.id}>
            <rect
              x={p.x} y={p.y} width={NODE_W} height={NODE_H} rx={6}
              fill={node.new ? color : "#171b26"}
              stroke={node.locked ? "#d05c5c" : color}
              strokeWidth={node.new ? 2 : 1}
            >
              {node.new && (
                <animate attributeName="opacity" values="0.4;1" dur="0.6s" repeatCount="2" />
              )}
            </rect>
            <text
              x={p.x + 8} y={p.y + NODE_H / 2 + 3.5} fontSize={10.5}
              fill={node.new ? "#fff" : "#c9cfdd"}
            >
              {node.locked ? "🔒 " : ""}{node.name.length > 24 ? node.name.slice(0, 23) + "…" : node.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
