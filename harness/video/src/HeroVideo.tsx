// Master composition: the six scenes sequenced with transitions.
import React from "react";
import { AbsoluteFill, continueRender, delayRender } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { waitForFonts } from "./theme/fonts";
import { Scene1Hero } from "./scenes/Scene1Hero";
import { Scene2Ambiguity } from "./scenes/Scene2Ambiguity";
import { Scene3Answer } from "./scenes/Scene3Answer";
import { Scene4Denial } from "./scenes/Scene4Denial";
import { Scene5Dashboard } from "./scenes/Scene5Dashboard";
import { Scene6Outro } from "./scenes/Scene6Outro";

// Scene lengths (frames @30). Transitions overlap by their own duration, so the
// master length is the sum of scene lengths minus the overlaps.
const S = { hero: 150, ambiguity: 300, answer: 330, denial: 300, dashboard: 240, outro: 90 };
const T = 15; // transition frames
const NUM_TRANSITIONS = 5;
export const HERO_DURATION =
  S.hero + S.ambiguity + S.answer + S.denial + S.dashboard + S.outro - NUM_TRANSITIONS * T;

const fontHandle = delayRender("fonts");
waitForFonts().then(() => continueRender(fontHandle));

const t = () => linearTiming({ durationInFrames: T });

export const HeroVideo: React.FC = () => {
  return (
    <AbsoluteFill>
      <TransitionSeries>
        <TransitionSeries.Sequence durationInFrames={S.hero}>
          <Scene1Hero />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={t()} />
        <TransitionSeries.Sequence durationInFrames={S.ambiguity}>
          <Scene2Ambiguity />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={t()} />
        <TransitionSeries.Sequence durationInFrames={S.answer}>
          <Scene3Answer />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={t()} />
        <TransitionSeries.Sequence durationInFrames={S.denial}>
          <Scene4Denial />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={t()} />
        <TransitionSeries.Sequence durationInFrames={S.dashboard}>
          <Scene5Dashboard />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={t()} />
        <TransitionSeries.Sequence durationInFrames={S.outro}>
          <Scene6Outro />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
