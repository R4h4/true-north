// Lending KPI dashboard for the Ken-Burns scene. KPI cards with sparklines +
// an "NPL & collections over time" area chart. KPIs not backed by a real
// governed query carry a small "illustrative" tag (truthfulness).
import React from "react";
import { C, SHADOW_CARD } from "../theme/tokens";
import { FONT_SANS } from "../theme/fonts";
import { Line, type Point } from "./Chart";
import { DASHBOARD_KPIS } from "../data/lending";

const Sparkline: React.FC<{ up: boolean }> = ({ up }) => {
  const pts = up
    ? [8, 10, 9, 12, 14, 13, 16, 18, 20, 24]
    : [24, 22, 23, 20, 18, 19, 16, 14, 13, 11];
  const w = 220;
  const h = 46;
  const max = Math.max(...pts);
  const min = Math.min(...pts);
  const d = pts
    .map((p, i) => `${(i / (pts.length - 1)) * w},${h - ((p - min) / (max - min)) * h}`)
    .join(" ");
  const color = up ? C.green : C.red;
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <polyline points={d} fill="none" stroke={color} strokeWidth={2} />
    </svg>
  );
};

const npl: Point[] = [
  { x: "Jun", y: 0.074 }, { x: "Aug", y: 0.072 }, { x: "Oct", y: 0.071 },
  { x: "Dec", y: 0.073 }, { x: "Feb", y: 0.043 }, { x: "Apr", y: 0.067 }, { x: "Jun", y: 0.069 },
];

export const Dashboard: React.FC<{ reveal?: number }> = ({ reveal = 1 }) => {
  return (
    <div style={{ fontFamily: FONT_SANS, display: "flex", flexDirection: "column", gap: 20, padding: 8 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 18 }}>
        {DASHBOARD_KPIS.map((k) => (
          <div
            key={k.label}
            style={{
              background: C.surface,
              border: `1px solid ${C.border}`,
              borderRadius: 14,
              boxShadow: SHADOW_CARD,
              padding: "18px 20px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 15, color: C.muted }}>{k.label}</span>
              {!k.real && (
                <span style={{ fontSize: 10, color: C.muted, border: `1px solid ${C.border}`, borderRadius: 5, padding: "1px 5px" }}>
                  illustrative
                </span>
              )}
            </div>
            <div style={{ fontSize: 40, fontWeight: 700, color: C.inkStrong, letterSpacing: "-0.02em", margin: "4px 0 8px" }}>
              {k.value}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: k.up ? C.greenDark : C.red,
                  background: k.up ? C.greenTint : C.redTint,
                  borderRadius: 6,
                  padding: "2px 7px",
                }}
              >
                {k.up ? "▲" : "▼"} {k.delta}
              </span>
              <span style={{ fontSize: 13, color: C.muted }}>vs last month</span>
            </div>
            <Sparkline up={k.up} />
          </div>
        ))}
      </div>
      <div
        style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: 14,
          boxShadow: SHADOW_CARD,
          padding: "20px 22px",
        }}
      >
        <Line title="NPL ratio over time" points={npl} yFormat="percent" reveal={reveal} color={C.green} height={300} />
      </div>
    </div>
  );
};
