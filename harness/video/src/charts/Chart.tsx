// SVG charts ported from harness/ui/components/chart-view.tsx, with a `reveal`
// (0..1) prop that drives draw-on animation. Same scales/formatting so numbers
// stay truthful. Supports hbar (rankings) and line/area (time series) + kpi.
import React from "react";
import { CHART } from "../theme/tokens";
import { FONT_SANS } from "../theme/fonts";

export type Point = { x: string; y: number };
export type YFormat = "percent" | "vnd" | "number";

const W = 640;

export function formatY(v: number, fmt: YFormat): string {
  if (fmt === "percent") return `${(v * 100).toFixed(Math.abs(v * 100) >= 10 ? 0 : 1)}%`;
  if (fmt === "vnd") {
    if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(1)} tỷ`;
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)} tr`;
    return v.toLocaleString("vi-VN");
  }
  return v.toLocaleString();
}

const truncate = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

function valueScale(values: number[]) {
  const vMax = Math.max(0, ...values) * 1.15 || (Math.min(...values) < 0 ? 0 : 1);
  const vMin = Math.min(0, ...values) * 1.15;
  const span = vMax - vMin || 1;
  return { vMax, vMin, span };
}

// Horizontal bars (rankings). reveal grows bar widths + fades labels in.
export const HBar: React.FC<{
  title: string;
  points: Point[];
  yFormat: YFormat;
  reveal: number;
}> = ({ title, points, yFormat, reveal }) => {
  const pts = [...points].sort((a, b) => b.y - a.y);
  const { vMin, span } = valueScale(pts.map((p) => p.y));
  const PAD = { top: 40, right: 74, bottom: 14, left: 150 };
  const ROW_H = 30;
  const ROW_GAP = 14;
  const H = PAD.top + pts.length * (ROW_H + ROW_GAP) + PAD.bottom;
  const plotW = W - PAD.left - PAD.right;
  const xPos = (v: number) => PAD.left + ((v - vMin) / span) * plotW;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" style={{ fontFamily: FONT_SANS }}>
      <text x={16} y={22} fontSize={16} fontWeight={600} fill={CHART.ink}>
        {title}
      </text>
      <line x1={xPos(0)} x2={xPos(0)} y1={PAD.top - 6} y2={H - PAD.bottom} stroke={CHART.zero} strokeWidth={1} />
      {pts.map((p, i) => {
        const y = PAD.top + i * (ROW_H + ROW_GAP);
        const neg = p.y < 0;
        const x0 = xPos(Math.min(0, p.y));
        const fullW = Math.abs(xPos(p.y) - xPos(0));
        const bw = Math.max(fullW * reveal, 1);
        return (
          <g key={p.x} opacity={reveal > 0.05 ? 1 : 0}>
            <text x={PAD.left - 10} y={y + ROW_H / 2 + 5} fontSize={14} fill={CHART.ink} textAnchor="end">
              {truncate(p.x, 18)}
            </text>
            <rect x={x0} y={y} width={bw} height={ROW_H} rx={4} fill={neg ? CHART.red : CHART.navy} />
            <text
              x={neg ? x0 - 8 : x0 + bw + 8}
              y={y + ROW_H / 2 + 5}
              fontSize={14}
              fontWeight={600}
              fill={neg ? CHART.red : CHART.ink}
              textAnchor={neg ? "end" : "start"}
              opacity={reveal > 0.85 ? 1 : 0}
            >
              {formatY(p.y, yFormat)}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

// Line/area time series. reveal draws the path via strokeDashoffset.
export const Line: React.FC<{
  title?: string;
  points: Point[];
  yFormat: YFormat;
  reveal: number;
  color?: string;
  height?: number;
}> = ({ title, points, yFormat, reveal, color = CHART.green, height = 260 }) => {
  const pts = points;
  const { vMax, vMin, span } = valueScale(pts.map((p) => p.y));
  const H = height;
  const PAD = { top: title ? 40 : 16, right: 20, bottom: 34, left: 66 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const xStep = plotW / Math.max(1, pts.length - 1);
  const yPos = (v: number) => PAD.top + ((vMax - v) / span) * plotH;
  const xAt = (i: number) => PAD.left + i * xStep;
  const line = pts.map((p, i) => `${xAt(i)},${yPos(p.y)}`).join(" ");
  const area = `${xAt(0)},${yPos(Math.max(0, vMin))} ${line} ${xAt(pts.length - 1)},${yPos(Math.max(0, vMin))}`;
  const ticks = [0, 0.5, 1].map((f) => vMin + f * span);
  // draw-on: total path length approx, use large dash + offset
  const total = 4000;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" style={{ fontFamily: FONT_SANS }}>
      {title && (
        <text x={PAD.left} y={24} fontSize={16} fontWeight={600} fill={CHART.ink}>
          {title}
        </text>
      )}
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={PAD.left} x2={W - PAD.right} y1={yPos(t)} y2={yPos(t)} stroke={CHART.grid} strokeWidth={1} />
          <text x={PAD.left - 8} y={yPos(t) + 4} fontSize={11} fill={CHART.muted} textAnchor="end">
            {formatY(t, yFormat)}
          </text>
        </g>
      ))}
      <polygon points={area} fill={color} opacity={0.1 * reveal} />
      <polyline
        points={line}
        fill="none"
        stroke={color}
        strokeWidth={2.5}
        strokeLinejoin="round"
        strokeDasharray={total}
        strokeDashoffset={total * (1 - reveal)}
      />
    </svg>
  );
};

// Single big value.
export const Kpi: React.FC<{ title: string; value: string; reveal: number }> = ({
  title,
  value,
  reveal,
}) => (
  <div style={{ fontFamily: FONT_SANS, opacity: reveal }}>
    <div style={{ fontSize: 15, color: CHART.muted }}>{title}</div>
    <div style={{ fontSize: 44, fontWeight: 700, color: CHART.ink, letterSpacing: "-0.02em" }}>
      {value}
    </div>
  </div>
);
