import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The floating dev-tools badge overlaps the chat input's bottom corner
  // and shows up in every demo recording - keep dev mode visually clean.
  devIndicators: false,
};

export default nextConfig;
