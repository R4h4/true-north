import React from "react";
import { AbsoluteFill } from "remotion";
import { AppFrame } from "../chrome/AppFrame";
import { EmptyHero } from "../chrome/Conversation";
import { Cursor } from "../lib/Cursor";
import { QUESTION } from "../data/lending";

// 0-150f: hero, live-typed question, cursor drifts to the Send button.
export const Scene1Hero: React.FC = () => {
  return (
    <AbsoluteFill>
      <AppFrame dataset="Consumer Lending" persona="CEO" kg={null}>
        <EmptyHero typeStart={30} question={QUESTION} />
      </AppFrame>
      <Cursor
        path={[
          { frame: 0, x: 1360, y: 900 },
          { frame: 90, x: 1150, y: 560 },
          { frame: 120, x: 1150, y: 560 },
        ]}
        clicks={[118]}
      />
    </AbsoluteFill>
  );
};
