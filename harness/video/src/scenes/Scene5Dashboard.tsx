import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate, Easing } from "remotion";
import { C } from "../theme/tokens";
import { FONT_SANS } from "../theme/fonts";
import { Dashboard } from "../charts/Dashboard";

// 0-240f: slow Ken-Burns pan/zoom across the lending dashboard.
export const Scene5Dashboard: React.FC = () => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, 240], [1.0, 1.08], { easing: Easing.inOut(Easing.quad) });
  const ty = interpolate(frame, [0, 240], [0, -40], { easing: Easing.inOut(Easing.quad) });
  const reveal = interpolate(frame, [20, 140], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: C.bgApp, fontFamily: FONT_SANS }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          transform: `scale(${scale}) translateY(${ty}px)`,
          transformOrigin: "center 30%",
          padding: "60px 90px",
        }}
      >
        <div style={{ fontSize: 26, fontWeight: 700, color: C.inkStrong, letterSpacing: "-0.02em", marginBottom: 24 }}>
          Consumer Lending · portfolio health
        </div>
        <Dashboard reveal={reveal} />
      </div>
    </AbsoluteFill>
  );
};
