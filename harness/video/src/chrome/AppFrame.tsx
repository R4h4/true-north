// The workbench shell: topbar + two floating panes on the grey canvas,
// mirroring harness/ui/app/page.tsx.
import React from "react";
import { AbsoluteFill } from "remotion";
import { C, SHADOW_PANE } from "../theme/tokens";
import { FONT_SANS } from "../theme/fonts";
import { BrandMark } from "./BrandMark";

const RETAIL_PERSONAS = ["Executive", "RM South", "Marketing", "Analyst"];
const LENDING_PERSONAS = ["CEO", "Risk", "Collections South", "Partnerships"];

export const AppFrame: React.FC<{
  dataset?: "Retail Commerce" | "Consumer Lending";
  persona?: string;
  children?: React.ReactNode; // chat pane
  kg?: React.ReactNode; // KG pane
}> = ({ dataset = "Consumer Lending", persona = "CEO", children, kg }) => {
  const personas = dataset === "Consumer Lending" ? LENDING_PERSONAS : RETAIL_PERSONAS;
  return (
    <AbsoluteFill style={{ background: C.bgApp, fontFamily: FONT_SANS }}>
      {/* topbar */}
      <div
        style={{
          height: 68,
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: "0 28px",
          borderBottom: `1px solid ${C.border}`,
          background: C.surface,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <BrandMark size={30} />
          <span style={{ fontSize: 20, fontWeight: 700, color: C.inkStrong, letterSpacing: "-0.02em" }}>
            True North
          </span>
        </div>
        <span
          style={{
            fontSize: 15,
            fontWeight: 500,
            color: C.accentDark,
            background: C.accentTint,
            border: `1px solid #dcd2fa`,
            borderRadius: 99,
            padding: "4px 13px",
          }}
        >
          Governed BI
        </span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14 }}>
          {/* dataset dropdown trigger */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 9,
              height: 38,
              padding: "0 12px 0 14px",
              background: C.surface,
              border: `1px solid ${C.borderStrong}`,
              borderRadius: 9,
              fontSize: 16,
              fontWeight: 500,
              color: C.ink,
            }}
          >
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: C.accent }} />
            {dataset}
            <span style={{ color: C.muted, fontSize: 12 }}>▾</span>
          </div>
          {/* persona picker */}
          <div
            style={{
              display: "flex",
              gap: 2,
              background: "#eef0f7",
              border: `1px solid ${C.border}`,
              borderRadius: 9,
              padding: 3,
            }}
          >
            {personas.map((p) => {
              const active = p === persona;
              return (
                <span
                  key={p}
                  style={{
                    borderRadius: 7,
                    padding: "6px 14px",
                    fontSize: 15,
                    fontWeight: 500,
                    color: active ? C.ink : C.inkSecondary,
                    background: active ? C.surface : "transparent",
                    border: `1px solid ${active ? C.borderStrong : "transparent"}`,
                    boxShadow: active ? "0 1px 2px rgba(6,10,31,0.06)" : "none",
                  }}
                >
                  {p}
                </span>
              );
            })}
          </div>
        </div>
      </div>
      {/* panes */}
      <div
        style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "1fr 460px",
          gap: 18,
          padding: 18,
          minHeight: 0,
        }}
      >
        <div
          style={{
            position: "relative",
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 16,
            boxShadow: SHADOW_PANE,
            overflow: "hidden",
          }}
        >
          {children}
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            background: C.surfaceSubtle,
            border: `1px solid ${C.border}`,
            borderRadius: 16,
            boxShadow: SHADOW_PANE,
            overflow: "hidden",
          }}
        >
          <div style={{ padding: "18px 20px 4px", display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: C.muted, textTransform: "uppercase", letterSpacing: "0.08em" }}>
              Knowledge graph
            </span>
          </div>
          <div style={{ flex: 1, minHeight: 0, position: "relative" }}>{kg}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
