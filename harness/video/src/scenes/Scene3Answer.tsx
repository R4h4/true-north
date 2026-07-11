import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { AppFrame } from "../chrome/AppFrame";
import { AnswerCard } from "../chrome/Conversation";
import { KgPanel } from "../chrome/KgPanel";
import { HBar } from "../charts/Chart";
import { Typewriter } from "../lib/Typewriter";
import { fadeUp } from "../lib/timing";
import { C } from "../theme/tokens";
import { NPL_BY_PRODUCT, NPL_READOUT, NPL_CAVEATS } from "../data/lending";
import { KG_PROVENANCE, KG_PROVENANCE_HL } from "../data/kg";

// 0-330f: NPL hbar draws on, narrated readout + caveats, KG provenance grows +
// highlights.
export const Scene3Answer: React.FC = () => {
  const frame = useCurrentFrame();
  const barReveal = interpolate(frame, [24, 78], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const kgReveal = interpolate(frame, [10, 120], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const highlight = frame > 130 ? KG_PROVENANCE_HL : [];

  return (
    <AbsoluteFill>
      <AppFrame
        dataset="Consumer Lending"
        persona="CEO"
        kg={<KgPanel nodes={KG_PROVENANCE.nodes} edges={KG_PROVENANCE.edges} reveal={kgReveal} highlight={highlight} />}
      >
        <div style={{ padding: "26px 30px", display: "flex", flexDirection: "column", gap: 18 }}>
          <AnswerCard delay={4}>
            <HBar title={NPL_BY_PRODUCT.title} points={NPL_BY_PRODUCT.points} yFormat="percent" reveal={barReveal} />
          </AnswerCard>
          <div style={{ fontSize: 18, lineHeight: 1.6, color: C.ink }}>
            <Typewriter text={NPL_READOUT} startFrame={90} cps={34} caret={false} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {NPL_CAVEATS.map((cav, i) => (
              <div key={i} style={{ fontSize: 15.5, color: C.inkSecondary, ...fadeUp(frame, 150 + i * 26) }}>
                • {cav}
              </div>
            ))}
          </div>
        </div>
      </AppFrame>
    </AbsoluteFill>
  );
};
