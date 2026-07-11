import React from "react";
import { Composition } from "remotion";
import { HeroVideo, HERO_DURATION } from "./HeroVideo";

export const Root: React.FC = () => {
  return (
    <Composition
      id="HeroVideo"
      component={HeroVideo}
      durationInFrames={HERO_DURATION}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
