import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { useVideoConfig } from "remotion";
import { C } from "../theme/tokens";
import { FONT_SANS } from "../theme/fonts";
import { BrandMark } from "../chrome/BrandMark";
import { fadeUp, pop } from "../lib/timing";

// 0-90f: white; logo pops in, wordmark + tagline fade up (accent on one word).
export const Scene6Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill
      style={{
        background: C.surface,
        fontFamily: FONT_SANS,
        alignItems: "center",
        justifyContent: "center",
        gap: 28,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14, ...pop(frame, fps, 4) }}>
        <BrandMark size={52} />
        <span style={{ fontSize: 46, fontWeight: 700, color: C.inkStrong, letterSpacing: "-0.02em" }}>
          True North
        </span>
      </div>
      <div style={{ fontSize: 34, fontWeight: 600, color: C.inkStrong, ...fadeUp(frame, 24) }}>
        Trust <span style={{ color: C.accent }}>answers</span> for your business
      </div>
    </AbsoluteFill>
  );
};
