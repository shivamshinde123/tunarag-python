import React from "react";
import { interpolate, staticFile, useVideoConfig } from "remotion";
import { Audio } from "@remotion/media";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import durations from "./durations.json";
import { LEAD } from "./ui";
import { Adapter, Data, Hook, Loop, Meet } from "./scenes-a";
import { Close, Code, Reliability, Scoring, Search } from "./scenes-b";

export const FPS = 30;
const TAIL = 1.1; // seconds of breathing room after each line
const FADE = 15; // frames

const SCENES: { id: keyof typeof durations; C: React.FC }[] = [
  { id: "01-hook", C: Hook },
  { id: "02-meet", C: Meet },
  { id: "03-adapter", C: Adapter },
  { id: "04-loop", C: Loop },
  { id: "05-data", C: Data },
  { id: "06-search", C: Search },
  { id: "07-scoring", C: Scoring },
  { id: "08-reliability", C: Reliability },
  { id: "09-code", C: Code },
  { id: "10-close", C: Close },
];

const sceneFrames = (id: keyof typeof durations, fps: number) =>
  Math.ceil((LEAD + durations[id] + TAIL) * fps) +
  (id === "10-close" ? 2 * fps : 0);

export const TOTAL_FRAMES =
  SCENES.reduce((sum, s) => sum + sceneFrames(s.id, FPS), 0) -
  (SCENES.length - 1) * FADE;

// Music sits ~16 dB under the voice, lifts for the outro, then fades out.
const musicVolume = (f: number) =>
  interpolate(
    f,
    [0, 45, TOTAL_FRAMES - 150, TOTAL_FRAMES - 90, TOTAL_FRAMES - 10],
    [0, 0.14, 0.14, 0.3, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

export const TunaRAGVideo: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <>
      <Audio src={staticFile("music/bed.mp3")} volume={musicVolume} />
      <TransitionSeries>
        {SCENES.flatMap(({ id, C }, i) => [
          ...(i > 0
            ? [
                <TransitionSeries.Transition
                  key={`t-${id}`}
                  presentation={fade()}
                  timing={linearTiming({ durationInFrames: FADE })}
                />,
              ]
            : []),
          <TransitionSeries.Sequence
            key={id}
            name={id}
            durationInFrames={sceneFrames(id, fps)}
          >
            <C />
          </TransitionSeries.Sequence>,
        ])}
      </TransitionSeries>
    </>
  );
};
