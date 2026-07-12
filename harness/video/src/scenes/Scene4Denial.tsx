import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { AppFrame } from "../chrome/AppFrame";
import { UserBubble, Thoughts, DenialCard } from "../chrome/Conversation";
import { KgPanel } from "../chrome/KgPanel";
import { Cursor } from "../lib/Cursor";
import { DENIAL } from "../data/lending";
import { KG_DENIED } from "../data/kg";

// 0-300f: persona is now Partnerships; the same question is denied with a
// disclosed reason and the delinquency metrics render restricted (red) in KG.
export const Scene4Denial: React.FC = () => {
  const frame = useCurrentFrame();
  const kgReveal = interpolate(frame, [60, 150], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill>
      <AppFrame
        dataset="Consumer Lending"
        persona="Partnerships"
        kg={<KgPanel nodes={KG_DENIED.nodes} edges={KG_DENIED.edges} reveal={kgReveal} />}
      >
        <div style={{ padding: "26px 30px", display: "flex", flexDirection: "column", gap: 18 }}>
          <UserBubble text="How is our delinquency doing by partner?" delay={40} />
          <Thoughts seconds={3} delay={62} />
          <DenialCard
            headline={DENIAL.headline}
            reason={DENIAL.reason}
            alternatives={DENIAL.alternatives}
            delay={90}
          />
        </div>
      </AppFrame>
      {/* cursor drifts to the persona picker to motivate the switch */}
      <Cursor
        path={[
          { frame: 0, x: 900, y: 400 },
          { frame: 24, x: 1720, y: 46 },
          { frame: 40, x: 1720, y: 46 },
        ]}
        clicks={[30]}
        hideAfter={70}
      />
    </AbsoluteFill>
  );
};
