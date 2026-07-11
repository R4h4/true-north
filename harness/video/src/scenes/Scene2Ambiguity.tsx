import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { AppFrame } from "../chrome/AppFrame";
import { UserBubble, Thoughts, ToolStep, AskUserCard } from "../chrome/Conversation";
import { KgPanel } from "../chrome/KgPanel";
import { Cursor } from "../lib/Cursor";
import { QUESTION, AMBIGUITY } from "../data/lending";
import { KG_AMBIGUITY } from "../data/kg";

// 0-300f: question sent, reasoning + tool steps, KG lights up, ambiguity card,
// cursor selects NPL.
export const Scene2Ambiguity: React.FC = () => {
  const frame = useCurrentFrame();
  const kgReveal = interpolate(frame, [40, 150], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const pickReveal = interpolate(frame, [205, 220], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill>
      <AppFrame
        dataset="Consumer Lending"
        persona="CEO"
        kg={<KgPanel nodes={KG_AMBIGUITY.nodes} edges={KG_AMBIGUITY.edges} reveal={kgReveal} />}
      >
        <div style={{ padding: "26px 30px", display: "flex", flexDirection: "column", gap: 18 }}>
          <UserBubble text={QUESTION} delay={6} />
          <Thoughts seconds={6} delay={22} />
          <ToolStep label="Loading knowledge-graph schema" done={frame > 70} delay={32} />
          <ToolStep label="Resolving business term" mono="term=delinquency" done={frame > 100} delay={54} />
          <AskUserCard
            prompt={AMBIGUITY.prompt}
            options={AMBIGUITY.options}
            selected={AMBIGUITY.selected}
            reveal={pickReveal}
            delay={120}
          />
        </div>
      </AppFrame>
      <Cursor
        path={[
          { frame: 150, x: 700, y: 700 },
          { frame: 205, x: 620, y: 620 },
          { frame: 230, x: 620, y: 620 },
        ]}
        clicks={[212]}
        hideAfter={260}
      />
    </AbsoluteFill>
  );
};
