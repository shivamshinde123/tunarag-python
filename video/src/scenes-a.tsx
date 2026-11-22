import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import {
  Appear, C, Card, Check, Glyph, Hand, Kicker, Logo, Pill, Scene, Sticky, Title,
  mono, serif, useRamp, useSeconds, useSpring,
} from "./ui";

/* ---------- 1. Hook: tuning by eye ---------- */

const ConfigRow: React.FC<{ label: string; before: string; after: string; at: number }> = ({ label, before, after, at }) => {
  const p = useSpring(at, 14);
  const changed = useSeconds() >= at;
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontFamily: mono, fontSize: 38, padding: "18px 0", borderBottom: `2px solid ${C.grey}` }}>
      <span style={{ color: C.fog }}>{label}</span>
      <span
        style={{
          background: changed ? C.butter : "transparent",
          padding: "4px 16px",
          borderRadius: 12,
          scale: changed ? String(0.85 + 0.15 * p) : "1",
          fontWeight: 600,
        }}
      >
        {changed ? after : before}
      </span>
    </div>
  );
};

const Bill: React.FC = () => {
  const r = useRamp(16.4, 19);
  const dollars = 12 + 12 * r;
  return (
    <Pill bg={r > 0.95 ? C.blush : C.white} style={{ fontFamily: mono, fontSize: 36 }}>
      API bill ${dollars.toFixed(2)} {r > 0.95 ? <span style={{ color: C.redInk }}>×2</span> : null}
    </Pill>
  );
};

const HookContent: React.FC = () => {
  const t = useSeconds();
  const dim = interpolate(t, [24.6, 25.3], [1, 0.12], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const blur = interpolate(t, [24.6, 25.3], [0, 8], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <>
      <AbsoluteFill style={{ opacity: dim, filter: `blur(${blur}px)` }}>
        <Appear at={0} style={{ position: "absolute", left: 140, top: 110 }}>
          <Kicker>Tuning a RAG app, the usual way</Kicker>
        </Appear>
        <Appear at={1.6} style={{ position: "absolute", left: 140, top: 190, width: 720 }}>
          <Card style={{ padding: "28px 44px" }}>
            <div style={{ fontFamily: mono, fontSize: 28, color: C.fog, marginBottom: 6 }}>my_rag_config.py</div>
            <ConfigRow label="top_k" before="3" after="5" at={4.5} />
            <ConfigRow label="prompt" before="v1" after="v2-final-final" at={12.2} />
            <ConfigRow label="model" before="model-a" after="model-b" at={13.9} />
            <Appear at={6.8} style={{ marginTop: 26 }}>
              <Pill bg={C.graphite} color={C.white} style={{ fontSize: 30 }}>▶ run it</Pill>
            </Appear>
          </Card>
        </Appear>

        {[0, 1, 2].map((i) => (
          <Appear key={i} at={7.7 + i * 0.35} from="right" style={{ position: "absolute", left: 980 + i * 40, top: 200 + i * 150, width: 640 }}>
            <Card style={{ padding: "24px 32px", rotate: `${(i - 1) * 1.5}deg` }}>
              <div style={{ fontSize: 24, color: C.fog, fontWeight: 600 }}>ANSWER {i + 1}</div>
              <div style={{ height: 16, background: C.grey, borderRadius: 8, marginTop: 14, width: "92%" }} />
              <div style={{ height: 16, background: C.grey, borderRadius: 8, marginTop: 12, width: "70%" }} />
            </Card>
          </Appear>
        ))}
        <Appear at={9.2} from="pop" style={{ position: "absolute", left: 1600, top: 160 }}>
          <Hand size={90}>hmm…</Hand>
        </Appear>
        <Appear at={10.7} from="pop" style={{ position: "absolute", left: 1010, top: 690 }}>
          <Hand size={76} color={C.skyInk}>better?</Hand>
        </Appear>
        <Appear at={11.4} from="pop" style={{ position: "absolute", left: 1330, top: 720 }}>
          <Hand size={76} color={C.violetInk}>maybe?</Hand>
        </Appear>

        <Appear at={15.1} from="down" style={{ position: "absolute", left: 140, top: 780 }}>
          <Pill style={{ fontFamily: mono, fontSize: 36 }}>🕑 2:00 AM</Pill>
        </Appear>
        <Appear at={16.4} from="down" style={{ position: "absolute", left: 480, top: 780 }}>
          <Bill />
        </Appear>
        <Appear at={19.4} from="pop" style={{ position: "absolute", left: 1170, top: 820 }}>
          <Sticky rotate={-4} size={58}>
            <div style={{ fontSize: 30, color: C.fog }}>experiment log:</div>
            top_k 5, good-ish?
          </Sticky>
        </Appear>
      </AbsoluteFill>
      <Appear at={24.9} style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Title size={120}>There had to be a better way.</Title>
      </Appear>
    </>
  );
};

export const Hook: React.FC = () => (
  <Scene audio="01-hook" halo={{ x: 1300, y: 500, size: 1000 }}>
    <HookContent />
  </Scene>
);

/* ---------- 2. Meet TunaRAG ---------- */

const Balance: React.FC = () => {
  const t = useSeconds();
  const items = [
    { label: "Quality", bg: C.mint },
    { label: "Cost", bg: C.butter },
    { label: "Speed", bg: C.sky },
  ];
  return (
    <div style={{ display: "flex", gap: 28, justifyContent: "center" }}>
      {items.map((it, i) => (
        <Appear key={it.label} at={8.3 + i * 0.5} from="pop">
          <Pill bg={it.bg} style={{ fontSize: 40, translate: `0px ${Math.sin(t * 2.4 + i * 2) * 8}px` }}>{it.label}</Pill>
        </Appear>
      ))}
    </div>
  );
};

const Typed: React.FC<{ text: string; at: number; cps?: number }> = ({ text, at, cps = 22 }) => {
  const t = useSeconds();
  const n = Math.max(0, Math.min(text.length, Math.floor((t - at) * cps)));
  const caret = Math.floor(t * 2) % 2 === 0 ? "▍" : " ";
  return (
    <span>
      {text.slice(0, n)}
      <span style={{ opacity: 0.6 }}>{caret}</span>
    </span>
  );
};

const MeetContent: React.FC = () => {
  const t = useSeconds();
  const wiggle = Math.sin(t * 1.6) * 0.5 + 0.5;
  return (
    <>
      <Appear at={0} style={{ position: "absolute", top: 120, width: "100%", textAlign: "center" }}>
        <Hand size={64}>so I built one.</Hand>
      </Appear>
      <Appear at={1.3} from="pop" style={{ position: "absolute", top: 240, width: "100%", display: "flex", justifyContent: "center", alignItems: "center", gap: 36 }}>
        <Glyph size={150} wiggle={wiggle} />
        <Title size={190} style={{ fontWeight: 600 }}>TunaRAG</Title>
      </Appear>
      <Appear at={2.5} from="pop" style={{ position: "absolute", top: 455, left: 1180 }}>
        <Hand size={60} color={C.skyInk} style={{ rotate: "-3deg" }}>as in: tune a RAG</Hand>
      </Appear>
      <Appear at={4.3} style={{ position: "absolute", top: 560, width: "100%", textAlign: "center" }}>
        <div style={{ fontSize: 48, fontWeight: 500, maxWidth: 1400, margin: "0 auto", lineHeight: 1.3 }}>
          Open-source Python library that finds the best configuration
          <br />
          for the <b>RAG app you already have</b>.
        </div>
      </Appear>
      <div style={{ position: "absolute", top: 730, width: "100%" }}>
        <Balance />
      </div>
      <Appear at={12.2} style={{ position: "absolute", top: 870, width: "100%", display: "flex", justifyContent: "center" }}>
        <Pill bg={C.graphite} color={C.white} style={{ fontFamily: mono, fontSize: 40, padding: "18px 40px" }}>
          $ <Typed text="pip install tunarag-python" at={12.3} cps={30} />
        </Pill>
      </Appear>
    </>
  );
};

export const Meet: React.FC = () => (
  <Scene audio="02-meet" halo={{ x: 960, y: 380, size: 1200 }}>
    <MeetContent />
  </Scene>
);

/* ---------- 3. Adapter boundary ---------- */

const Packet: React.FC<{ at: number; label: string; toLeft: boolean; bg: string }> = ({ at, label, toLeft, bg }) => {
  const r = useRamp(at, at + 1.6);
  const show = useSpring(at, 200);
  const gone = useRamp(at + 1.7, at + 2.1);
  const x = toLeft ? interpolate(r, [0, 1], [1200, 720]) : interpolate(r, [0, 1], [720, 1200]);
  return (
    <div style={{ position: "absolute", left: x - 210, top: toLeft ? 360 : 770, width: 420, display: "flex", justifyContent: "center", opacity: show * (1 - gone) }}>
      <Pill bg={bg} style={{ fontSize: 32 }}>{toLeft ? "← " : ""}{label}{toLeft ? "" : " →"}</Pill>
    </div>
  );
};

const OwnedChip: React.FC<{ at: number; label: string }> = ({ at, label }) => (
  <Appear at={at} from="pop">
    <Pill style={{ fontSize: 30, padding: "10px 24px" }}>🔒 {label}</Pill>
  </Appear>
);

const AdapterContent: React.FC = () => (
  <>
    <Appear at={0} style={{ position: "absolute", top: 70, width: "100%", textAlign: "center" }}>
      <Title size={76}>You don't rebuild anything.</Title>
    </Appear>

    {/* Your app (blue) */}
    <Appear at={2.8} from="left" style={{ position: "absolute", left: 110, top: 220, width: 640, height: 740 }}>
      <div style={{ width: "100%", height: "100%", border: `4px dashed ${C.skyInk}`, borderRadius: 36, background: "rgba(214,230,247,.55)", padding: 40, boxSizing: "border-box" }}>
        <Kicker color={C.skyInk}>Your app</Kicker>
        <div style={{ display: "flex", flexDirection: "column", gap: 22, marginTop: 30 }}>
          {[
            { at: 3.3, logo: "langchain.svg", name: "LangChain chain" },
            { at: 4.6, logo: "langgraph.svg", name: "LangGraph graph" },
            { at: 6.0, logo: "adk.png", name: "Google ADK agent" },
          ].map((f) => (
            <Appear key={f.name} at={f.at} from="left">
              <div style={{ display: "flex", alignItems: "center", gap: 24, background: C.white, borderRadius: 20, padding: "16px 24px", boxShadow: "rgba(0,0,0,.05) 0 4px 16px" }}>
                <Logo name={f.logo} size={58} style={{ width: 58 }} />
                <span style={{ fontSize: 36, fontWeight: 600 }}>{f.name}</span>
              </div>
            </Appear>
          ))}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginTop: 40 }}>
          <OwnedChip at={9.1} label="index" />
          <OwnedChip at={9.6} label="prompts" />
          <OwnedChip at={10.2} label="API keys" />
        </div>
        <Appear at={11.8} from="pop" style={{ marginTop: 26 }}>
          <Hand size={58} color={C.skyInk}>all still yours ✓</Hand>
        </Appear>
      </div>
    </Appear>

    {/* Adapter diamond */}
    <Appear at={13.1} from="pop" style={{ position: "absolute", left: 860, top: 470, width: 200, height: 200 }}>
      <div style={{ width: 200, height: 200, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ position: "absolute", width: 150, height: 150, rotate: "45deg", background: C.peach, border: `4px solid ${C.orangeInk}`, borderRadius: 18 }} />
        <span style={{ position: "relative", fontSize: 28, fontWeight: 700, color: C.orangeInk }}>adapter</span>
      </div>
    </Appear>
    <Appear at={13.6} style={{ position: "absolute", left: 790, top: 700, width: 340, textAlign: "center" }}>
      <div style={{ fontSize: 26, color: C.fog, fontWeight: 600 }}>official, built in</div>
    </Appear>

    {/* TunaRAG (orange) */}
    <Appear at={13.1} from="right" style={{ position: "absolute", left: 1170, top: 220, width: 640, height: 740 }}>
      <div style={{ width: "100%", height: "100%", border: `4px dashed ${C.orangeInk}`, borderRadius: 36, background: "rgba(255,225,194,.5)", padding: 40, boxSizing: "border-box", display: "flex", flexDirection: "column" }}>
        <Kicker color={C.orangeInk}>TunaRAG</Kicker>
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 20 }}>
          <Glyph size={150} />
          <div style={{ fontSize: 34, fontWeight: 600, color: C.fog }}>runs the experiments</div>
        </div>
      </div>
    </Appear>

    <Packet at={16.6} label="settings + question" toLeft bg={C.butter} />
    <Packet at={18.7} label="answer + usage" toLeft={false} bg={C.mint} />

    <Appear at={21.0} from="pop" style={{ position: "absolute", left: 1290, top: 780 }}>
      <Sticky rotate={3} size={52}>That's it. No funny business.</Sticky>
    </Appear>
  </>
);

export const Adapter: React.FC = () => (
  <Scene audio="03-adapter">
    <AdapterContent />
  </Scene>
);

/* ---------- 4. The loop ---------- */

const STEPS = [
  { label: "Pick settings", at: 2.4, bg: C.lilac },
  { label: "Run your RAG", at: 3.7, bg: C.sky },
  { label: "Grade answers", at: 6.1, bg: C.mint },
  { label: "Score it", at: 7.6, bg: C.butter },
  { label: "Learn", at: 9.8, bg: C.blush },
];
const CX = 760;
const CY = 590;
const R = 330;
const LAP = 1.5;
const LOOP_START = 11.0;

const stepPos = (i: number) => {
  const a = -Math.PI / 2 + (i / STEPS.length) * Math.PI * 2;
  return { x: CX + R * Math.cos(a), y: CY + R * Math.sin(a) };
};

const LoopContent: React.FC = () => {
  const t = useSeconds();
  const running = t >= LOOP_START;
  const lapT = (t - LOOP_START) / LAP;
  const laps = running ? Math.floor(lapT) : 0;
  const a = -Math.PI / 2 + (lapT % 1) * Math.PI * 2;
  const ring = useRamp(0.2, 1.6);
  return (
    <>
      <Appear at={0} style={{ position: "absolute", left: 120, top: 90 }}>
        <Title size={76}>One simple loop.</Title>
      </Appear>
      <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
        <circle
          cx={CX}
          cy={CY}
          r={R}
          fill="none"
          stroke={C.graphite}
          strokeWidth={4}
          strokeDasharray={`${2 * Math.PI * R * ring} ${2 * Math.PI * R}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${CX} ${CY})`}
          opacity={0.35}
        />
        {running ? <circle cx={CX + R * Math.cos(a)} cy={CY + R * Math.sin(a)} r={18} fill={C.orangeInk} /> : null}
      </svg>
      {STEPS.map((s, i) => {
        const p = stepPos(i);
        return (
          <Appear key={s.label} at={s.at} from="pop" style={{ position: "absolute", left: p.x - 170, top: p.y - 46, width: 340, display: "flex", justifyContent: "center" }}>
            <Pill bg={s.bg} style={{ fontSize: 34 }}>{i + 1}. {s.label}</Pill>
          </Appear>
        );
      })}
      <Appear at={11.0} from="pop" style={{ position: "absolute", left: CX - 160, top: CY - 70, width: 320, textAlign: "center" }}>
        <Kicker>trial</Kicker>
        <div style={{ fontFamily: serif, fontSize: 110, lineHeight: 1 }}>#{laps + 1}</div>
      </Appear>

      {/* SQLite log */}
      <Appear at={12.1} from="right" style={{ position: "absolute", left: 1280, top: 230, width: 520 }}>
        <Card style={{ background: C.grey, padding: 36 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 20 }}>
            <Logo name="sqlite.svg" size={64} />
            <span style={{ fontSize: 38, fontWeight: 700 }}>study.sqlite</span>
          </div>
          {Array.from({ length: Math.min(laps, 6) }).map((_, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: C.white, borderRadius: 14, padding: "12px 20px", marginTop: 12, fontFamily: mono, fontSize: 28 }}>
              <span>trial {i + 1}</span>
              <span style={{ display: "flex", alignItems: "center", gap: 8, color: C.greenInk }}>saved <Check size={30} /></span>
            </div>
          ))}
        </Card>
      </Appear>
      <Appear at={15.5} from="pop" style={{ position: "absolute", left: 1330, top: 900 }}>
        <Hand size={56}>nothing gets lost</Hand>
      </Appear>
    </>
  );
};

export const Loop: React.FC = () => (
  <Scene audio="04-loop" halo={{ x: 760, y: 590, size: 900 }}>
    <LoopContent />
  </Scene>
);

/* ---------- 5. Test data ---------- */

const SplitBar: React.FC = () => {
  const parts = [
    { label: "optimize", w: 0.6, bg: C.peach },
    { label: "validation", w: 0.2, bg: C.sky },
    { label: "test", w: 0.2, bg: C.mint },
  ];
  const r = useRamp(11.2, 12.6);
  return (
    <div style={{ display: "flex", width: 880, height: 84, borderRadius: 100, overflow: "hidden", boxShadow: "rgba(0,0,0,.06) 0 4px 16px" }}>
      {parts.map((p) => (
        <div key={p.label} style={{ width: `${p.w * 100 * r}%`, background: p.bg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 30, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden" }}>
          {p.label}
        </div>
      ))}
    </div>
  );
};

const DataContent: React.FC = () => (
  <>
    <Appear at={0} style={{ position: "absolute", left: 120, top: 90 }}>
      <Title size={76}>Bring your test questions.</Title>
    </Appear>
    <div style={{ position: "absolute", left: 140, top: 300, display: "flex", flexDirection: "column", gap: 26 }}>
      {["JSON", "JSONL", "CSV"].map((f, i) => (
        <Appear key={f} at={1.2 + i * 0.7} from="left">
          <Pill bg={C.grey} style={{ fontFamily: mono, fontSize: 40, width: 260, justifyContent: "center" }}>📄 {f}</Pill>
        </Appear>
      ))}
    </div>
    <Appear at={4.4} from="pop" style={{ position: "absolute", left: 140, top: 700 }}>
      <Hand size={54}>no dataset yet?</Hand>
    </Appear>
    <Appear at={5.8} from="left" style={{ position: "absolute", left: 140, top: 790 }}>
      <Pill bg={C.lilac} color={C.violetInk} style={{ fontSize: 36 }}>✨ LLM writes Q&amp;A pairs</Pill>
    </Appear>

    <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
      <Arrows />
    </svg>

    <Appear at={9.1} from="pop" style={{ position: "absolute", left: 860, top: 300, width: 900 }}>
      <Card style={{ padding: 44 }}>
        <Kicker>Evaluation dataset</Kicker>
        <div style={{ fontFamily: serif, fontSize: 64, marginTop: 8 }}>one versioned dataset</div>
        <div style={{ fontFamily: mono, fontSize: 30, color: C.fog, marginTop: 12 }}>version 3f9a…c21 · 120 questions</div>
      </Card>
    </Appear>
    <Appear at={11.0} style={{ position: "absolute", left: 870, top: 640 }}>
      <SplitBar />
      <div style={{ fontSize: 32, color: C.fog, marginTop: 22, fontWeight: 500 }}>split the same way, every single time</div>
    </Appear>
  </>
);

const Arrows: React.FC = () => {
  const r = useRamp(9.0, 10.2);
  const paths = ["M 440 345 C 620 345, 660 420, 850 420", "M 440 445 C 620 445, 660 430, 850 430", "M 440 545 C 620 545, 660 440, 850 440", "M 720 820 C 800 820, 760 470, 850 450"];
  return (
    <>
      {paths.map((d) => (
        <path key={d} d={d} fill="none" stroke={C.graphite} strokeOpacity={0.35} strokeWidth={4} strokeDasharray="1000" strokeDashoffset={1000 * (1 - r)} strokeLinecap="round" />
      ))}
    </>
  );
};

export const Data: React.FC = () => (
  <Scene audio="05-data" halo={{ x: 1300, y: 500, size: 1000 }}>
    <DataContent />
  </Scene>
);
