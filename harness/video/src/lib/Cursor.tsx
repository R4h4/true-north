// The signature violet pointer. Moves through a list of keyframes (eased) and
// pulses on "click" frames. Coordinates are in the 1920x1080 composition space.
import React from "react";
import { interpolate, useCurrentFrame, Easing } from "remotion";
import { C } from "../theme/tokens";

export type CursorKey = { frame: number; x: number; y: number };

export const Cursor: React.FC<{
  path: CursorKey[];
  clicks?: number[];
  hideAfter?: number;
}> = ({ path, clicks = [], hideAfter }) => {
  const frame = useCurrentFrame();
  if (hideAfter !== undefined && frame > hideAfter) return null;
  if (path.length === 0) return null;

  const frames = path.map((p) => p.frame);
  const xs = path.map((p) => p.x);
  const ys = path.map((p) => p.y);
  const x = interpolate(frame, frames, xs, {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const y = interpolate(frame, frames, ys, {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });

  // Click pulse: brief scale-down near any click frame.
  let clickScale = 1;
  for (const cf of clicks) {
    const d = Math.abs(frame - cf);
    if (d < 6) clickScale = Math.min(clickScale, interpolate(d, [0, 6], [0.7, 1]));
  }

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        transform: `scale(${clickScale})`,
        transformOrigin: "top left",
        zIndex: 100,
        pointerEvents: "none",
        filter: "drop-shadow(0 2px 4px rgba(6,10,31,0.25))",
      }}
    >
      <svg width="30" height="30" viewBox="0 0 24 24" fill="none">
        <path
          d="M5 3l14 7-6 2-2 6-6-15z"
          fill={C.accent}
          stroke="#fff"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
};
