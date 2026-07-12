import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate, Easing } from "remotion";
import { C } from "../theme/tokens";
import { FONT_SANS } from "../theme/fonts";
import { fadeUp } from "../lib/timing";

// Full-screen interstitial shown as the persona switches (CEO -> Partnerships).
// Large statement, banner-matched dark stage: governed BI resolves every answer
// per persona — which sets up the access denial in the next scene.
export const ScenePersonaSwitch: React.FC = () => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, 90], [1.04, 1.0], {
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.quad),
  });

  return (
    <AbsoluteFill
      style={{
        background: "#0a0d24",
        fontFamily: FONT_SANS,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div style={{ textAlign: "center", transform: `scale(${scale})`, maxWidth: 1200, padding: "0 60px" }}>
        <div
          style={{
            fontSize: 26,
            fontWeight: 600,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: C.accent,
            ...fadeUp(frame, 4),
          }}
        >
          Governed BI
        </div>
        <div
          style={{
            fontSize: 92,
            fontWeight: 700,
            lineHeight: 1.06,
            letterSpacing: "-0.03em",
            color: "#ffffff",
            marginTop: 24,
            ...fadeUp(frame, 12),
          }}
        >
          Same question.
          <br />
          Different <span style={{ color: C.accent }}>persona.</span>
        </div>
        <div
          style={{
            fontSize: 29,
            fontWeight: 400,
            lineHeight: 1.5,
            color: "#b8bdd6",
            marginTop: 30,
            ...fadeUp(frame, 28),
          }}
        >
          Every answer is resolved through the semantic layer — per persona access policy.
        </div>
      </div>
    </AbsoluteFill>
  );
};
