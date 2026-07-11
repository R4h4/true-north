"use client";

// Compass-in-circle brand mark: green needle pointing north, navy tail
// south. `tone: "muted"` renders the grayscale variant for empty states.
export function BrandMark({ size = 26, tone = "brand" }: { size?: number; tone?: "brand" | "muted" }) {
  const ring = tone === "muted" ? "var(--muted)" : "var(--green)";
  const needle = tone === "muted" ? "var(--muted)" : "var(--green)";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 26 26"
      aria-hidden="true"
      opacity={tone === "muted" ? 0.45 : 1}
    >
      <circle cx="13" cy="13" r="11.4" fill="none" stroke={ring} strokeWidth={size > 30 ? 1.6 : 2} />
      {tone === "brand" && (
        <path d="M13 21.4 L10.4 13.8 L13 12.1 L15.6 13.8 Z" fill="var(--navy)" opacity="0.28" />
      )}
      <path d="M13 4.6 L16 14.2 L13 12.1 L10 14.2 Z" fill={needle} />
    </svg>
  );
}
