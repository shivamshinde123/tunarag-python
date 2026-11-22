import React from "react";
import {
  AbsoluteFill,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Audio } from "@remotion/media";
import { loadFont as loadSerif } from "@remotion/google-fonts/SourceSerif4";
import { loadFont as loadSans } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";
import { loadFont as loadHand } from "@remotion/google-fonts/Caveat";

export const serif = loadSerif("normal", { weights: ["400", "600"], subsets: ["latin"] }).fontFamily;
export const sans = loadSans("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily;
export const mono = loadMono("normal", { weights: ["400", "600"], subsets: ["latin"] }).fontFamily;
export const hand = loadHand("normal", { weights: ["600", "700"], subsets: ["latin"] }).fontFamily;

// Landing-page palette + the diagram colour key (blue = your app, orange = TunaRAG,
// green = results, grey = storage, violet = LLM helpers, yellow = notes).
export const C = {
  canvas: "#f8f5ef",
  graphite: "#393737",
  fog: "#888787",
  white: "#ffffff",
  sky: "#d6e6f7",
  skyInk: "#1c6fb8",
  peach: "#ffe1c2",
  orangeInk: "#d9730d",
  mint: "#cfeee3",
  greenInk: "#2b8a5e",
  butter: "#fbe7b8",
  blush: "#f5cfdc",
  redInk: "#c2410c",
  lilac: "#e4dcf3",
  violetInk: "#6d4fc2",
  grey: "#ebe8e2",
};

export const SHADOW = "rgba(0,0,0,.06) 0 6px 28px";

/** Narration starts this long after a scene begins. */
export const LEAD = 0.4;

/** 0 → 1 spring that starts `at` seconds (narration time) into the scene. */
export const useSpring = (at: number, damping = 200, durationSec?: number) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({
    frame: frame - at * fps,
    fps,
    config: { damping },
    durationInFrames: durationSec ? durationSec * fps : undefined,
  });
};

/** Linear 0 → 1 between two narration times. */
export const useRamp = (from: number, to: number) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return interpolate(frame / fps, [from, to], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
};

export const useSeconds = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return frame / fps;
};

type AppearProps = {
  readonly at: number;
  readonly children: React.ReactNode;
  readonly style?: React.CSSProperties;
  readonly from?: "up" | "down" | "left" | "right" | "pop";
  readonly pop?: boolean;
};

/** Fades and slides its children in at narration time `at`. */
export const Appear: React.FC<AppearProps> = ({ at, children, style, from = "up" }) => {
  const p = useSpring(at, from === "pop" ? 12 : 200);
  const d = 40 * (1 - p);
  const translate =
    from === "up" ? `0px ${d}px` : from === "down" ? `0px ${-d}px` : from === "left" ? `${-d}px 0px` : from === "right" ? `${d}px 0px` : "0px 0px";
  return (
    <div
      style={{
        opacity: Math.min(1, p * 1.4),
        translate,
        scale: from === "pop" ? String(0.6 + 0.4 * p) : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

/** Slowly turning pastel conic halo, as on the landing page. */
export const Halo: React.FC<{ readonly x: number; readonly y: number; readonly size: number; readonly opacity?: number }> = ({
  x,
  y,
  size,
  opacity = 0.9,
}) => {
  const t = useSeconds();
  return (
    <div
      style={{
        position: "absolute",
        left: x - size / 2,
        top: y - size / 2,
        width: size,
        height: size,
        borderRadius: "50%",
        background:
          "conic-gradient(from 180deg, #cfeee3, #e7f3e0, #d6e6f7, #fef1d8, #e4dcf3, #f5cfdc, #cfeee3)",
        filter: "blur(70px)",
        opacity,
        rotate: `${t * 8}deg`,
      }}
    />
  );
};

type SceneProps = {
  readonly audio: string;
  readonly children: React.ReactNode;
  readonly halo?: { x: number; y: number; size: number };
};

/** Cream canvas + halo; children and narration start LEAD seconds in. */
export const Scene: React.FC<SceneProps> = ({ audio, children, halo = { x: 960, y: 560, size: 1100 } }) => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: C.canvas, fontFamily: sans, color: C.graphite, overflow: "hidden" }}>
      <Halo {...halo} opacity={0.55} />
      <Sequence from={Math.round(LEAD * fps)} layout="none">
        <Audio src={staticFile(`voiceover/${audio}.mp3`)} />
        <AbsoluteFill>{children}</AbsoluteFill>
      </Sequence>
    </AbsoluteFill>
  );
};

export const Title: React.FC<{ readonly children: React.ReactNode; readonly size?: number; readonly style?: React.CSSProperties }> = ({
  children,
  size = 84,
  style,
}) => (
  <div
    style={{
      fontFamily: serif,
      fontWeight: 400,
      fontSize: size,
      letterSpacing: "-0.03em",
      lineHeight: 1.05,
      ...style,
    }}
  >
    {children}
  </div>
);

export const Kicker: React.FC<{ readonly children: React.ReactNode; readonly color?: string }> = ({ children, color = C.fog }) => (
  <div style={{ fontSize: 26, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color }}>{children}</div>
);

export const Card: React.FC<{ readonly children: React.ReactNode; readonly style?: React.CSSProperties }> = ({ children, style }) => (
  <div style={{ background: C.white, borderRadius: 24, boxShadow: SHADOW, padding: 32, ...style }}>{children}</div>
);

export const Pill: React.FC<{ readonly children: React.ReactNode; readonly bg?: string; readonly color?: string; readonly style?: React.CSSProperties }> = ({
  children,
  bg = C.white,
  color = C.graphite,
  style,
}) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 14,
      padding: "14px 30px",
      borderRadius: 100,
      background: bg,
      color,
      fontSize: 34,
      fontWeight: 600,
      boxShadow: SHADOW,
      whiteSpace: "nowrap",
      ...style,
    }}
  >
    {children}
  </div>
);

/** Hand-written yellow sticky note: the friendly aside. */
export const Sticky: React.FC<{ readonly children: React.ReactNode; readonly rotate?: number; readonly style?: React.CSSProperties; readonly size?: number }> = ({
  children,
  rotate = -3,
  style,
  size = 54,
}) => (
  <div
    style={{
      background: "#fff3b0",
      fontFamily: hand,
      fontWeight: 700,
      fontSize: size,
      lineHeight: 1.05,
      padding: "22px 34px",
      boxShadow: "rgba(0,0,0,.10) 0 10px 24px",
      rotate: `${rotate}deg`,
      color: C.graphite,
      ...style,
    }}
  >
    {children}
  </div>
);

export const Hand: React.FC<{ readonly children: React.ReactNode; readonly size?: number; readonly color?: string; readonly style?: React.CSSProperties }> = ({
  children,
  size = 56,
  color = C.graphite,
  style,
}) => <div style={{ fontFamily: hand, fontWeight: 700, fontSize: size, color, lineHeight: 1.05, ...style }}>{children}</div>;

export const Logo: React.FC<{ readonly name: string; readonly size?: number; readonly style?: React.CSSProperties }> = ({ name, size = 72, style }) => (
  <Img src={staticFile(`logos/${name}`)} style={{ height: size, objectFit: "contain", ...style }} />
);

/** TunaRAG's slider glyph (from the landing page). */
export const Glyph: React.FC<{ readonly size?: number; readonly wiggle?: number }> = ({ size = 80, wiggle = 0 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size}>
    <rect width="24" height="24" rx="7" fill={C.graphite} />
    <g fill="#fff">
      <rect x="5" y="6.5" width="14" height="1.6" rx=".8" />
      <rect x="5" y="11.2" width="14" height="1.6" rx=".8" />
      <rect x="5" y="15.9" width="14" height="1.6" rx=".8" />
      <circle cx={15 - 3 * wiggle} cy="7.3" r="2.1" />
      <circle cx={9 + 4 * wiggle} cy="12" r="2.1" />
      <circle cx={13 - 2 * wiggle} cy="16.7" r="2.1" />
    </g>
  </svg>
);

export const Check: React.FC<{ readonly size?: number; readonly color?: string }> = ({ size = 40, color = C.greenInk }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </svg>
);

export const Cross: React.FC<{ readonly size?: number; readonly color?: string }> = ({ size = 40, color = C.redInk }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round">
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
);
