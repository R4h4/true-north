// Frame-driven animation helpers. No Date.now/Math.random — everything is a
// pure function of the current frame so re-renders are byte-stable.
import { interpolate, spring, Easing } from "remotion";

type Num = number;

// Standard "fade + rise" entrance. Returns style props for opacity/translateY.
export function fadeUp(
  frame: Num,
  start: Num,
  { rise = 10, dur = 16 }: { rise?: Num; dur?: Num } = {},
) {
  const t = interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  return {
    opacity: t,
    transform: `translateY(${(1 - t) * rise}px)`,
  };
}

// Springy pop-in (mascot, logo). Scale from 0.8 -> 1.
export function pop(frame: Num, fps: Num, delay = 0) {
  const s = spring({ frame: frame - delay, fps, config: { damping: 14, mass: 0.7 } });
  return { transform: `scale(${interpolate(s, [0, 1], [0.82, 1])})`, opacity: s };
}

// Eased 0->1 progress over a window; for chart draw-on and generic reveals.
export function reveal(frame: Num, start: Num, dur: Num) {
  return interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
}

// Count a number up to `to` over a window (KPI values).
export function countTo(frame: Num, start: Num, dur: Num, to: Num) {
  return interpolate(frame, [start, start + dur], [0, to], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
}
