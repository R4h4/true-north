"use client";

// Dependency-free SVG chart for render_chart tool results. The payload comes
// from the governed envelope (backend-injected rows) - never model-typed.
// Visual language: Holistics answer cards - navy bars, green line with a soft
// area fill, hairline gridlines, and a dataset-attribution footer strip.

export type ChartPayload = {
  type: "bar" | "line";
  title: string;
  x_label: string;
  y_label: string;
  y_format: "percent" | "vnd" | "number";
  points: { x: string; y: number }[];
  as_of?: string;
};

const W = 640;
const H = 280;
const PAD = { top: 34, right: 16, bottom: 40, left: 64 };

const NAVY = "#1e2a4a";
const GREEN = "#259b6c";
const GRID = "#eef2f6";
const INK = "#32353f";
const MUTED = "#8a94a6";

function formatY(v: number, fmt: ChartPayload["y_format"]): string {
  if (fmt === "percent") return `${(v * 100).toFixed(v * 100 >= 10 ? 0 : 1)}%`;
  if (fmt === "vnd") {
    if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(1)} tỷ`;
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)} tr`;
    return v.toLocaleString("vi-VN");
  }
  return v.toLocaleString();
}

export function ChartView({ chart }: { chart: ChartPayload }) {
  const pts = chart.points ?? [];
  if (pts.length === 0) return null;

  const yMax = Math.max(...pts.map((p) => p.y)) * 1.15 || 1;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const xStep = plotW / pts.length;
  const yPos = (v: number) => PAD.top + plotH - (v / yMax) * plotH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * yMax);
  const lineXY = (i: number) => `${PAD.left + (i + 0.5) * xStep},${yPos(pts[i].y)}`;

  return (
    <div className="chart-card">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={chart.title}>
        <text x={PAD.left} y={20} fontSize={13.5} fontWeight={600} fill={INK}>
          {chart.title}
        </text>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={W - PAD.right} y1={yPos(t)} y2={yPos(t)} stroke={GRID} strokeWidth={1} />
            <text x={PAD.left - 8} y={yPos(t) + 4} fontSize={10} fill={MUTED} textAnchor="end">
              {formatY(t, chart.y_format)}
            </text>
          </g>
        ))}
        {chart.type === "bar" &&
          pts.map((p, i) => {
            const bw = Math.min(xStep * 0.55, 72);
            const x = PAD.left + i * xStep + (xStep - bw) / 2;
            return (
              <g key={p.x}>
                <rect x={x} y={yPos(p.y)} width={bw} height={PAD.top + plotH - yPos(p.y)} rx={3} fill={NAVY} />
                <text x={x + bw / 2} y={yPos(p.y) - 6} fontSize={11} fontWeight={500} fill={INK} textAnchor="middle">
                  {formatY(p.y, chart.y_format)}
                </text>
              </g>
            );
          })}
        {chart.type === "line" && (
          <>
            <polygon
              points={`${PAD.left + 0.5 * xStep},${PAD.top + plotH} ${pts.map((_, i) => lineXY(i)).join(" ")} ${
                PAD.left + (pts.length - 0.5) * xStep
              },${PAD.top + plotH}`}
              fill={GREEN}
              opacity={0.08}
            />
            <polyline
              points={pts.map((_, i) => lineXY(i)).join(" ")}
              fill="none"
              stroke={GREEN}
              strokeWidth={2}
              strokeLinejoin="round"
            />
            {pts.map((p, i) => (
              <circle key={p.x} cx={PAD.left + (i + 0.5) * xStep} cy={yPos(p.y)} r={3} fill="#ffffff" stroke={GREEN} strokeWidth={2} />
            ))}
          </>
        )}
        {pts.map((p, i) => (
          <text
            key={p.x}
            x={PAD.left + (i + 0.5) * xStep}
            y={H - PAD.bottom + 18}
            fontSize={10.5}
            fill={MUTED}
            textAnchor="middle"
          >
            {p.x.length > 12 ? p.x.slice(0, 11) + "…" : p.x}
          </text>
        ))}
      </svg>
      <div className="card-footer">
        <span>
          {chart.x_label}
          {chart.y_label ? ` · ${chart.y_label}` : ""}
        </span>
        <span>Governed by tn contract{chart.as_of ? ` · as of ${chart.as_of}` : ""}</span>
      </div>
    </div>
  );
}
