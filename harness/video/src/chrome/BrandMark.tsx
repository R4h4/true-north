// Compass mark, ported from harness/ui/components/brand-mark.tsx.
import React from "react";
import { C } from "../theme/tokens";

export const BrandMark: React.FC<{ size?: number }> = ({ size = 26 }) => {
  const s = size;
  return (
    <svg width={s} height={s} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <circle cx="16" cy="16" r="13.2" stroke={C.accent} strokeWidth="2.4" />
      <path d="M16 6 L19 16 L16 26 Z" fill={C.navy} opacity="0.28" />
      <path d="M16 6 L13 16 L16 26 Z" fill={C.accent} />
      <circle cx="16" cy="16" r="1.8" fill={C.surface} />
    </svg>
  );
};
