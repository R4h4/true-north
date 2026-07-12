import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, interpolate, Easing } from "remotion";
import { AppFrame } from "../chrome/AppFrame";
import { EmptyHero } from "../chrome/Conversation";
import { QUESTION } from "../data/lending";
import { C } from "../theme/tokens";

// Opening beat, three phases on one local timeline (frames @30):
//   0- 58  banner title card, centered on a dark stage; fades out 46-58
//  48-230  app fades in UNDER the banner, zoomed into the input; the first
//          question types out; on "enter" (~150) the camera eases back out to
//          the whole page before Scene 2 takes over.
const BANNER_OUT = 58;
const APP_IN = 46;
const TYPE_START = 76;
const ENTER = 150;
const ZOOM_OUT_END = 198;
const ZOOM_IN = 1.55;

export const Scene1Hero: React.FC = () => {
  const frame = useCurrentFrame();

  const bannerOp = interpolate(frame, [0, 12, 46, BANNER_OUT], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bannerScale = interpolate(frame, [0, BANNER_OUT], [1.0, 1.05], {
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.quad),
  });
  const appOp = interpolate(frame, [APP_IN, APP_IN + 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  // hold the zoom-in, then ease out to identity (whole page) after "enter".
  const scale = interpolate(frame, [APP_IN, ENTER, ZOOM_OUT_END], [ZOOM_IN, ZOOM_IN, 1.0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });

  return (
    <AbsoluteFill style={{ background: C.bgApp }}>
      {/* App layer, zoomed toward the input; origin at the input keeps scale=1
          exactly identity so the zoom-out lands on the true whole page. */}
      <AbsoluteFill style={{ opacity: appOp, overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: 0, transformOrigin: "38% 54%", transform: `scale(${scale})` }}>
          <AppFrame dataset="Consumer Lending" persona="CEO" kg={null}>
            <EmptyHero typeStart={TYPE_START} question={QUESTION} />
          </AppFrame>
        </div>
      </AbsoluteFill>

      {/* Banner title card on a dark stage, fading out into the app */}
      <AbsoluteFill
        style={{
          opacity: bannerOp,
          background: "#0a0d24",
          alignItems: "center",
          justifyContent: "center",
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            width: 1680,
            maxWidth: "90%",
            borderRadius: 20,
            overflow: "hidden",
            boxShadow: "0 30px 90px rgba(0,0,0,0.55)",
            transform: `scale(${bannerScale})`,
          }}
        >
          <Img src={staticFile("banner.png")} style={{ display: "block", width: "100%", height: "auto" }} />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
