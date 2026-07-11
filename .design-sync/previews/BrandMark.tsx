import * as React from "react";
import { BrandMark } from "true-north-ui";

// The mark as the topbar composes it (see .brand in app/globals.css):
// icon + product name on a white surface row.
export const BrandRow = () => (
  <div style={{ display: "flex", alignItems: "center", gap: 8, padding: 12 }}>
    <BrandMark />
    <span style={{ fontSize: 14, fontWeight: 600, letterSpacing: "-0.01em", color: "#32353f" }}>
      True North
    </span>
  </div>
);
