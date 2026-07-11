// Frame-driven typewriter: reveals text.slice(0, chars) where chars grows with
// the frame. Optional blinking caret. Deterministic (no timers).
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

export const Typewriter: React.FC<{
  text: string;
  startFrame: number;
  cps?: number; // characters per second
  caret?: boolean;
  style?: React.CSSProperties;
}> = ({ text, startFrame, cps = 26, caret = true, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const elapsed = Math.max(0, frame - startFrame);
  const chars = Math.min(text.length, Math.floor((elapsed * cps) / fps));
  const done = chars >= text.length;
  const showCaret = caret && (!done || Math.floor(frame / 15) % 2 === 0);

  return (
    <span style={style}>
      {text.slice(0, chars)}
      {showCaret && (
        <span style={{ opacity: 0.6, fontWeight: 300 }}>|</span>
      )}
    </span>
  );
};
