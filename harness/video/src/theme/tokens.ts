// Design tokens ported verbatim from harness/ui/app/globals.css :root.
// Single source of truth for every scene so the video matches the live app.

export const C = {
  ink: "#363d52",
  inkStrong: "#060a1f",
  inkSecondary: "#5b6172",
  muted: "#8b90a3",
  bgApp: "#eef0f6",
  surface: "#ffffff",
  surfaceSubtle: "#fafbfe",
  border: "#e8eaf2",
  borderStrong: "#d9dce8",
  accent: "#7c5cf0",
  accentDark: "#6344d6",
  accentTint: "#f0ecfd",
  green: "#259b6c",
  greenDark: "#196848",
  greenTint: "#e5f5ee",
  navy: "#060a1f",
  blueTint: "#e8f1fd",
  red: "#d6455d",
  redTint: "#fdeef1",
  amber: "#b7791f",
  amberTint: "#fdf6e3",
} as const;

export const SHADOW_CARD = "0 1px 2px rgba(6, 10, 31, 0.06)";
export const SHADOW_PANE =
  "0 1px 2px rgba(6, 10, 31, 0.05), 0 6px 20px rgba(6, 10, 31, 0.06)";

// Chart palette (from chart-view.tsx).
export const CHART = {
  navy: "#1c2340",
  accent: "#7c5cf0",
  red: "#d6455d",
  grid: "#eef0f7",
  zero: "#d9dce8",
  ink: "#363d52",
  muted: "#8b90a3",
  green: "#259b6c",
} as const;
