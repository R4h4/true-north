"use client";

// Dependency-free SVG chart for render_chart tool results. The payload comes
// from the governed envelope (backend-injected rows) - never model-typed.
// Visual language: Holistics answer cards - navy bars, green line with a soft
// area fill, hairline gridlines, and a dataset-attribution footer strip.
// Negative values are supported (zero baseline, red bars) - retail margins
// go negative and a chart that clips them lies by omission.

export type ChartPayload = {
  type: "bar" | "hbar" | "line" | "kpi";
  title: string;
  x_label: string;
  y_label: string;
  y_format: "percent" | "vnd" | "number";
  points: { x: string; y: number }[];
  as_of?: string;
};

const W = 640;
const NAVY = "#1e2a4a";
const GREEN = "#259b6c";
const RED = "#d6455d";
const GRID = "#eef2f6";
const ZERO = "#d8dfe8";
const INK = "#32353f";
const MUTED = "#8a94a6";

function formatY(v: number, fmt: ChartPayload["y_format"]): string {
  if (fmt === "percent") return `${(v * 100).toFixed(Math.abs(v * 100) >= 10 ? 0 : 1)}%`;
  if (fmt === "vnd") {
    if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(1)} tỷ`;
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)} tr`;
    return v.toLocaleString("vi-VN");
  }
  return v.toLocaleString();
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// ISO dates make unreadable tick labels at 12+ points; compress to "Jan"
// (with the year on January / the first tick so the series stays anchored).
function xTick(s: string, isFirst: boolean): string {
  const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(s);
  if (!m) return truncate(s, 12);
  const month = MONTHS[Number(m[2]) - 1] ?? m[2];
  return isFirst || m[2] === "01" ? `${month} ${m[1].slice(2)}` : month;
}

function Footer({ chart }: { chart: ChartPayload }) {
  return (
    <div className="card-footer">
      <span>{[chart.x_label, chart.y_label].filter(Boolean).join(" · ")}</span>
      <span>Governed by tn contract{chart.as_of ? ` · as of ${chart.as_of}` : ""}</span>
    </div>
  );
}

function KpiCard({ chart }: { chart: ChartPayload }) {
  const value = chart.points[0]?.y ?? 0;
  return (
    <div className="chart-card">
      <div className="kpi-body">
        <span className="kpi-label">{chart.title}</span>
        <span className="kpi-value">{formatY(value, chart.y_format)}</span>
        {chart.y_format === "vnd" && Math.abs(value) >= 1e6 && (
          <span className="kpi-sub">{value.toLocaleString("vi-VN")} ₫</span>
        )}
      </div>
      <Footer chart={chart} />
    </div>
  );
}

// Shared value scale: always spans zero so bars have an honest baseline.
function valueScale(values: number[]) {
  const vMax = Math.max(0, ...values) * 1.15 || (Math.min(...values) < 0 ? 0 : 1);
  const vMin = Math.min(0, ...values) * 1.15;
  const span = vMax - vMin || 1;
  return { vMax, vMin, span };
}

function HBarChart({ chart }: { chart: ChartPayload }) {
  // Rankings read top-down: sort descending by value.
  const pts = [...chart.points].sort((a, b) => b.y - a.y);
  const { vMin, span } = valueScale(pts.map((p) => p.y));
  const PAD = { top: 34, right: 66, bottom: 12, left: 130 };
  const ROW_H = 22;
  const ROW_GAP = 9;
  const H = PAD.top + pts.length * (ROW_H + ROW_GAP) + PAD.bottom;
  const plotW = W - PAD.left - PAD.right;
  const xPos = (v: number) => PAD.left + ((v - vMin) / span) * plotW;

  return (
    <div className="chart-card">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={chart.title}>
        <text x={16} y={20} fontSize={13.5} fontWeight={600} fill={INK}>
          {chart.title}
        </text>
        <line x1={xPos(0)} x2={xPos(0)} y1={PAD.top - 6} y2={H - PAD.bottom} stroke={ZERO} strokeWidth={1} />
        {pts.map((p, i) => {
          const y = PAD.top + i * (ROW_H + ROW_GAP);
          const neg = p.y < 0;
          const x0 = xPos(Math.min(0, p.y));
          const bw = Math.abs(xPos(p.y) - xPos(0));
          return (
            <g key={p.x}>
              <text x={PAD.left - 8} y={y + ROW_H / 2 + 4} fontSize={11} fill={INK} textAnchor="end">
                {truncate(p.x, 18)}
              </text>
              <rect x={x0} y={y} width={Math.max(bw, 1)} height={ROW_H} rx={3} fill={neg ? RED : NAVY} />
              <text
                x={neg ? x0 - 6 : x0 + bw + 6}
                y={y + ROW_H / 2 + 4}
                fontSize={11}
                fontWeight={500}
                fill={neg ? RED : INK}
                textAnchor={neg ? "end" : "start"}
              >
                {formatY(p.y, chart.y_format)}
              </text>
            </g>
          );
        })}
      </svg>
      <Footer chart={chart} />
    </div>
  );
}

function XYChart({ chart }: { chart: ChartPayload }) {
  const pts = chart.points;
  const { vMax, vMin, span } = valueScale(pts.map((p) => p.y));
  const H = 280;
  const PAD = { top: 34, right: 16, bottom: 40, left: 64 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const xStep = plotW / pts.length;
  const yPos = (v: number) => PAD.top + ((vMax - v) / span) * plotH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => vMin + f * span);
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
        {vMin < 0 && (
          <line x1={PAD.left} x2={W - PAD.right} y1={yPos(0)} y2={yPos(0)} stroke={ZERO} strokeWidth={1.2} />
        )}
        {chart.type === "bar" &&
          pts.map((p, i) => {
            const bw = Math.min(xStep * 0.55, 72);
            const x = PAD.left + i * xStep + (xStep - bw) / 2;
            const neg = p.y < 0;
            const yTop = Math.min(yPos(p.y), yPos(0));
            const bh = Math.abs(yPos(p.y) - yPos(0));
            return (
              <g key={p.x}>
                <rect x={x} y={yTop} width={bw} height={Math.max(bh, 1)} rx={3} fill={neg ? RED : NAVY} />
                <text
                  x={x + bw / 2}
                  y={neg ? yPos(p.y) + 14 : yPos(p.y) - 6}
                  fontSize={11}
                  fontWeight={500}
                  fill={neg ? RED : INK}
                  textAnchor="middle"
                >
                  {formatY(p.y, chart.y_format)}
                </text>
              </g>
            );
          })}
        {chart.type === "line" && (
          <>
            <polygon
              points={`${PAD.left + 0.5 * xStep},${yPos(Math.max(0, vMin))} ${pts.map((_, i) => lineXY(i)).join(" ")} ${
                PAD.left + (pts.length - 0.5) * xStep
              },${yPos(Math.max(0, vMin))}`}
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
            {xTick(p.x, i === 0)}
          </text>
        ))}
      </svg>
      <Footer chart={chart} />
    </div>
  );
}

export function ChartView({ chart }: { chart: ChartPayload }) {
  if ((chart.points ?? []).length === 0) return null;
  if (chart.type === "kpi") return <KpiCard chart={chart} />;
  if (chart.type === "hbar") return <HBarChart chart={chart} />;
  return <XYChart chart={chart} />;
}
