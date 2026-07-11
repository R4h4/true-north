// IBM Plex Sans/Mono, matching harness/ui/app/layout.tsx. loadFont() registers
// the faces and Remotion waits for them before rendering.
import { loadFont as loadSans } from "@remotion/google-fonts/IBMPlexSans";
import { loadFont as loadMono } from "@remotion/google-fonts/IBMPlexMono";

const sans = loadSans("normal", {
  weights: ["400", "500", "600", "700"],
  subsets: ["latin"],
  ignoreTooManyRequestsWarning: true,
});
const mono = loadMono("normal", {
  weights: ["400", "500"],
  subsets: ["latin"],
  ignoreTooManyRequestsWarning: true,
});

export const FONT_SANS = sans.fontFamily;
export const FONT_MONO = mono.fontFamily;

export const waitForFonts = () =>
  Promise.all([sans.waitUntilDone(), mono.waitUntilDone()]);
