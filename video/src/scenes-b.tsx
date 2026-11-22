import React from "react";
import { interpolate, random } from "remotion";
import {
  Appear, C, Card, Check, Cross, Glyph, Hand, Kicker, Logo, Pill, Scene, Sticky, Title,
  mono, serif, useRamp, useSeconds, useSpring,
} from "./ui";

/* ---------- 6. Search ---------- */

const Knob: React.FC<{ label: string; at: number; seed: number }> = ({ label, at, seed }) => {
  const t = useSeconds();
  const pos = 0.5 + 0.4 * Math.sin(t * (1.1 + seed * 0.3) + seed * 2);
  return (
    <Appear at={at} from="left">
      <div style={{ display: "flex", alignItems: "center", gap: 24, width: 640 }}>
        <span style={{ fontFamily: mono, fontSize: 32, width: 230 }}>{label}</span>
        <div style={{ position: "relative", flex: 1, height: 12, background: C.grey, borderRadius: 6 }}>
          <div style={{ position: "absolute", left: `${pos * 100}%`, top: -14, width: 40, height: 40, marginLeft: -20, borderRadius: 20, background: C.graphite }} />
        </div>
      </div>
    </Appear>
  );
};

const BOX = { w: 620, h: 360 };

const RandomDots: React.FC = () => {
  const t = useSeconds();
  const n = Math.max(0, Math.min(18, Math.floor((t - 6.4) * 5)));
  return (
    <svg width={BOX.w} height={BOX.h}>
      {Array.from({ length: n }).map((_, i) => (
        <circle key={i} cx={40 + random(`rx${i}`) * (BOX.w - 80)} cy={30 + random(`ry${i}`) * (BOX.h - 60)} r={14} fill={C.skyInk} opacity={0.75} />
      ))}
    </svg>
  );
};

const LlmDots: React.FC = () => {
  const t = useSeconds();
  const target = { x: 440, y: 120 };
  const n = Math.max(0, Math.min(10, Math.floor((t - 9.6) * 4)));
  const offRails = t >= 12.0 && t < 14.3;
  const fallback = t >= 14.3;
  return (
    <svg width={BOX.w} height={BOX.h} style={{ overflow: "visible" }}>
      <circle cx={target.x} cy={target.y} r={46} fill="none" stroke={C.violetInk} strokeWidth={3} strokeDasharray="8 8" />
      {Array.from({ length: n }).map((_, i) => {
        const k = 1 - i / 10;
        const x = target.x + (random(`lx${i}`) - 0.5) * 420 * k;
        const y = target.y + (random(`ly${i}`) - 0.3) * 300 * k;
        return <circle key={i} cx={x} cy={y} r={14} fill={C.violetInk} opacity={0.8} />;
      })}
      {offRails || fallback
        ? [0, 1, 2].map((i) => {
            const r = interpolate(t, [12.0, 13.4], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
            return <circle key={`o${i}`} cx={120 + i * 60 - r * (200 + i * 80)} cy={300 + r * (120 + i * 40)} r={14} fill={C.redInk} opacity={fallback ? 0.25 : 0.9} />;
          })
        : null}
    </svg>
  );
};

const SearchContent: React.FC = () => (
  <>
    <Appear at={0} style={{ position: "absolute", left: 120, top: 80 }}>
      <Title size={76}>You pick the knobs.</Title>
    </Appear>
    <div style={{ position: "absolute", left: 1120, top: 90, display: "flex", flexDirection: "column", gap: 30 }}>
      <Knob label="top_k" at={2.4} seed={0} />
      <Knob label="chunk_size" at={3.0} seed={1} />
      <Knob label="prompt" at={3.6} seed={2} />
      <Knob label="model" at={4.2} seed={3} />
    </div>

    <Appear at={6.1} from="up" style={{ position: "absolute", left: 120, top: 420 }}>
      <Card style={{ width: BOX.w + 64, padding: 32, background: "rgba(255,255,255,.92)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 40, fontWeight: 700 }}>Random search</span>
          <Pill bg={C.sky} style={{ fontSize: 26, padding: "8px 20px" }}>fair · repeatable</Pill>
        </div>
        <div style={{ marginTop: 16, background: C.canvas, borderRadius: 18 }}>
          <RandomDots />
        </div>
      </Card>
    </Appear>

    <Appear at={9.4} from="up" style={{ position: "absolute", left: 1000, top: 420 }}>
      <Card style={{ width: BOX.w + 64, padding: 32, background: "rgba(255,255,255,.92)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 40, fontWeight: 700 }}>LLM-guided</span>
          <Pill bg={C.lilac} color={C.violetInk} style={{ fontSize: 26, padding: "8px 20px" }}>smarter guesses</Pill>
        </div>
        <div style={{ marginTop: 16, background: C.canvas, borderRadius: 18 }}>
          <LlmDots />
        </div>
      </Card>
    </Appear>
    <Appear at={11.9} from="pop" style={{ position: "absolute", left: 1020, top: 960 }}>
      <Hand size={50} color={C.redInk}>…off the rails?</Hand>
    </Appear>
    <Appear at={14.3} from="pop" style={{ position: "absolute", left: 1330, top: 950 }}>
      <Pill bg={C.graphite} color={C.white} style={{ fontSize: 32 }}>↩ falls back to random</Pill>
    </Appear>
    <Appear at={17.1} from="pop" style={{ position: "absolute", left: 620, top: 300 }}>
      <Sticky rotate={-3} size={48}>grown-up supervision ✓</Sticky>
    </Appear>
  </>
);

export const Search: React.FC = () => (
  <Scene audio="06-search" halo={{ x: 1000, y: 650, size: 1100 }}>
    <SearchContent />
  </Scene>
);

/* ---------- 7. Scoring ---------- */

const WeightBar: React.FC<{ label: string; weight: string; value: number; bg: string; at: number }> = ({ label, weight, value, bg, at }) => {
  const r = useSpring(at, 200);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20, fontSize: 32 }}>
      <span style={{ width: 170, fontWeight: 600 }}>{label}</span>
      <div style={{ width: 340, height: 40, background: C.grey, borderRadius: 20, overflow: "hidden" }}>
        <div style={{ width: `${value * 100 * r}%`, height: "100%", background: bg, borderRadius: 20 }} />
      </div>
      <span style={{ fontFamily: mono, color: C.fog, fontSize: 28 }}>{weight}</span>
    </div>
  );
};

const Score: React.FC = () => {
  const r = useRamp(9.2, 10.4);
  return <div style={{ fontFamily: serif, fontSize: 150, lineHeight: 1 }}>{(0.82 * r).toFixed(2)}</div>;
};

const ScoringContent: React.FC = () => {
  const strike = useRamp(12.6, 13.2);
  return (
    <>
      <Appear at={0} style={{ position: "absolute", left: 120, top: 80 }}>
        <Title size={76}>What does “best” even mean?</Title>
      </Appear>

      <Appear at={2.3} from="left" style={{ position: "absolute", left: 120, top: 250, width: 560 }}>
        <Card>
          <Kicker>Evaluators</Kicker>
          <Appear at={3.6}>
            <div style={{ fontFamily: mono, fontSize: 26, background: C.canvas, borderRadius: 14, padding: "16px 20px", marginTop: 18, lineHeight: 1.5 }}>
              <span style={{ color: C.violetInk }}>def</span> recall(out, ex):
              <br />
              {"    "}<span style={{ color: C.violetInk }}>return</span> hits / needed
            </div>
          </Appear>
          <Appear at={4.9} style={{ display: "flex", alignItems: "center", gap: 18, marginTop: 22 }}>
            <span style={{ fontSize: 30, color: C.fog, fontWeight: 600 }}>or plug in</span>
            <Logo name="ragas.png" size={56} />
          </Appear>
        </Card>
      </Appear>

      <Appear at={6.9} style={{ position: "absolute", left: 760, top: 250, width: 1040 }}>
        <Card style={{ display: "flex", alignItems: "center", gap: 40 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <Kicker>Objective</Kicker>
            <WeightBar label="Quality" weight="× 0.6" value={0.92} bg={C.mint} at={7.2} />
            <WeightBar label="Cost" weight="× 0.25" value={0.7} bg={C.butter} at={7.7} />
            <WeightBar label="Latency" weight="× 0.15" value={0.6} bg={C.sky} at={8.2} />
          </div>
          <div style={{ textAlign: "center", flex: 1 }}>
            <div style={{ fontSize: 28, color: C.fog, fontWeight: 600 }}>one number</div>
            <Score />
          </div>
        </Card>
      </Appear>

      <Appear at={10.6} from="up" style={{ position: "absolute", left: 760, top: 640, display: "flex", gap: 30 }}>
        <Card style={{ width: 470, padding: 26, position: "relative" }}>
          <div style={{ fontSize: 30, fontWeight: 700 }}>Config A</div>
          <div style={{ fontSize: 28, color: C.fog, marginTop: 8 }}>quality 0.93 · cost $$$ (3×)</div>
          <div style={{ position: "relative", display: "inline-block", fontFamily: serif, fontSize: 64, marginTop: 6, color: C.redInk }}>
            0.62
            <div style={{ position: "absolute", left: -8, right: -8, top: "50%", height: 6, background: C.redInk, borderRadius: 3, scale: `${strike} 1`, transformOrigin: "left" }} />
          </div>
        </Card>
        <Card style={{ width: 470, padding: 26, background: "#f0faf5" }}>
          <div style={{ fontSize: 30, fontWeight: 700, display: "flex", alignItems: "center", gap: 10 }}>Config B <Check size={34} /></div>
          <div style={{ fontSize: 28, color: C.fog, marginTop: 8 }}>quality 0.90 · cost $</div>
          <div style={{ fontFamily: serif, fontSize: 64, marginTop: 6, color: C.greenInk }}>0.84</div>
        </Card>
      </Appear>
      <Appear at={13.0} from="pop" style={{ position: "absolute", left: 800, top: 905 }}>
        <Hand size={50} color={C.redInk}>nice try, Config A</Hand>
      </Appear>

      <Appear at={15.0} from="left" style={{ position: "absolute", left: 120, top: 700, width: 560 }}>
        <Card style={{ background: C.butter }}>
          <Kicker color={C.graphite}>Stop rules</Kicker>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 14, marginTop: 18 }}>
            <Appear at={15.6} from="pop"><Pill style={{ fontSize: 28, padding: "10px 22px" }}>budget $5</Pill></Appear>
            <Appear at={16.4} from="pop"><Pill style={{ fontSize: 28, padding: "10px 22px" }}>30 minutes</Pill></Appear>
            <Appear at={17.0} from="pop"><Pill style={{ fontSize: 28, padding: "10px 22px" }}>40 trials</Pill></Appear>
          </div>
        </Card>
      </Appear>
    </>
  );
};

export const Scoring: React.FC = () => (
  <Scene audio="07-scoring" halo={{ x: 1250, y: 480, size: 1000 }}>
    <ScoringContent />
  </Scene>
);

/* ---------- 8. Reliability ---------- */

const Tile: React.FC<{ at: number; q: string; children: React.ReactNode; bg: string; x: number; y: number }> = ({ at, q, children, bg, x, y }) => (
  <Appear at={at} from="pop" style={{ position: "absolute", left: x, top: y, width: 800 }}>
    <Card style={{ height: 290, boxSizing: "border-box", display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ width: 22, height: 22, borderRadius: 11, background: bg }} />
        <span style={{ fontFamily: serif, fontSize: 48 }}>{q}</span>
      </div>
      {children}
    </Card>
  </Appear>
);

const ResumeBar: React.FC = () => {
  const t = useSeconds();
  const p = t < 5.0 ? interpolate(t, [4.4, 5.0], [0.15, 0.55], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : t < 6.0 ? 0.55 : interpolate(t, [6.0, 7.4], [0.55, 1], { extrapolateRight: "clamp" });
  const crashed = t >= 5.0 && t < 6.0;
  return (
    <div>
      <div style={{ height: 34, background: C.grey, borderRadius: 17, overflow: "hidden" }}>
        <div style={{ width: `${p * 100}%`, height: "100%", background: crashed ? C.blush : C.mint }} />
      </div>
      <div style={{ fontSize: 32, marginTop: 16, fontWeight: 600, color: crashed ? C.redInk : C.greenInk }}>
        {t < 5.0 ? "trial 7 of 12…" : crashed ? "💥 crashed at trial 7" : "resumed at trial 7 ✓"}
      </div>
    </div>
  );
};

const Attempts: React.FC = () => {
  const rows = [
    { at: 11.1, label: "attempt 1 · 429 rate limit", ok: false },
    { at: 11.8, label: "attempt 2 · timeout", ok: false },
    { at: 12.7, label: "attempt 3 · success", ok: true },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {rows.map((r) => (
        <Appear key={r.label} at={r.at} from="left" style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: mono, fontSize: 28 }}>
          {r.ok ? <Check size={32} /> : <Cross size={32} />} {r.label}
        </Appear>
      ))}
    </div>
  );
};

const ReliabilityContent: React.FC = () => (
  <>
    <Appear at={0} style={{ position: "absolute", left: 120, top: 70, display: "flex", alignItems: "center", gap: 28 }}>
      <Title size={72}>Real life is messy. TunaRAG copes.</Title>
    </Appear>
    <Tile at={4.4} q="Laptop crashed?" bg={C.blush} x={120} y={200}>
      <ResumeBar />
    </Tile>
    <Tile at={7.9} q="Same question twice?" bg={C.butter} x={1000} y={200}>
      <Appear at={9.5} from="pop">
        <Pill bg={C.mint} style={{ fontSize: 36 }}>⚡ cache hit · skipped</Pill>
      </Appear>
      <Appear at={10.0}>
        <div style={{ fontSize: 28, color: C.fog, fontWeight: 500 }}>no repeat calls, no repeat bill</div>
      </Appear>
    </Tile>
    <Tile at={10.9} q="Provider having a bad day?" bg={C.sky} x={120} y={530}>
      <Attempts />
    </Tile>
    <Tile at={14.4} q="All done? Export it." bg={C.mint} x={1000} y={530}>
      <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
        <Appear at={14.9} from="pop"><Pill bg={C.grey} style={{ fontFamily: mono, fontSize: 32 }}>results.json</Pill></Appear>
        <Appear at={15.4} from="pop"><Pill bg={C.grey} style={{ fontFamily: mono, fontSize: 32 }}>results.csv</Pill></Appear>
      </div>
      <Appear at={17.3} from="left" style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ fontSize: 30, color: C.fog, fontWeight: 600 }}>mirror to</span>
        <Logo name="mlflow.svg" size={56} />
      </Appear>
    </Tile>
    <Appear at={6.2} style={{ position: "absolute", left: 120, top: 880, display: "flex", alignItems: "center", gap: 20 }}>
      <Logo name="sqlite.svg" size={64} />
      <span style={{ fontSize: 34, fontWeight: 600 }}>every trial lives in SQLite, so resuming just works</span>
    </Appear>
  </>
);

export const Reliability: React.FC = () => (
  <Scene audio="08-reliability" halo={{ x: 960, y: 560, size: 1200 }}>
    <ReliabilityContent />
  </Scene>
);

/* ---------- 9. The code ---------- */

const CODE: { text: string; hl?: [number, number] }[] = [
  { text: "optimizer = Optimizer(" },
  { text: "    adapter=LangChainAdapter(factory=build_chain, ...),", hl: [2.2, 3.4] },
  { text: "    strategy=RandomSearch(", hl: [3.4, 4.8] },
  { text: '        SearchSpace({"top_k": IntegerRange(1, 2)}), seed=7),', hl: [3.4, 4.8] },
  { text: '    evaluators=(MetricEvaluator("retrieval_recall", recall),),', hl: [4.8, 5.8] },
  { text: '    objective=Objective((ObjectiveTerm("retrieval_recall"),)),', hl: [5.8, 6.9] },
  { text: ")" },
  { text: 'result = optimizer.optimize(dataset, study_name="langchain-rag")', hl: [6.9, 8.4] },
  { text: "print(result.best_candidate.parameters)  # {'top_k': 2}" },
];

const CodeLine: React.FC<{ text: string; hl?: [number, number] }> = ({ text, hl }) => {
  const t = useSeconds();
  const on = hl ? t >= hl[0] && t < hl[1] : false;
  return (
    <div style={{ background: on ? "rgba(251,231,184,.9)" : "transparent", borderRadius: 8, padding: "2px 12px", whiteSpace: "pre", opacity: hl && !on && t >= 2.2 && t < 8.4 ? 0.55 : 1 }}>
      {text}
    </div>
  );
};

const RecallBar: React.FC<{ label: string; value: number; at: number; win?: boolean }> = ({ label, value, at, win }) => {
  const r = useSpring(at, 200);
  return (
    <Appear at={at} from="left">
      <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
        <span style={{ fontFamily: mono, fontSize: 34, width: 170 }}>{label}</span>
        <div style={{ width: 360, height: 52, background: C.grey, borderRadius: 26, overflow: "hidden" }}>
          <div style={{ width: `${value * 100 * r}%`, height: "100%", background: win ? C.mint : C.butter, borderRadius: 26 }} />
        </div>
        <span style={{ fontFamily: serif, fontSize: 52 }}>{(value * r).toFixed(1)}</span>
      </div>
    </Appear>
  );
};

const CodeContent: React.FC = () => (
  <>
    <Appear at={0} style={{ position: "absolute", left: 120, top: 70 }}>
      <Title size={72}>Here's the whole thing.</Title>
    </Appear>
    <Appear at={0.6} style={{ position: "absolute", left: 100, top: 210 }}>
      <Card style={{ fontFamily: mono, fontSize: 25, lineHeight: 1.65, padding: "30px 28px", width: 1060, boxSizing: "border-box" }}>
        {CODE.map((l, i) => (
          <CodeLine key={i} text={l.text} hl={l.hl} />
        ))}
      </Card>
    </Appear>
    <Appear at={7.8} from="right" style={{ position: "absolute", left: 1230, top: 230 }}>
      <Card style={{ width: 640, boxSizing: "border-box" }}>
        <Kicker>retrieval recall</Kicker>
        <div style={{ display: "flex", flexDirection: "column", gap: 26, marginTop: 24 }}>
          <RecallBar label="top_k=1" value={0.5} at={8.2} />
          <RecallBar label="top_k=2" value={1.0} at={11.9} win />
        </div>
        <Appear at={14.0} from="pop" style={{ marginTop: 30 }}>
          <Pill bg={C.graphite} color={C.white} style={{ fontSize: 34 }}>🏆 best: top_k = 2</Pill>
        </Appear>
      </Card>
    </Appear>
    <Appear at={8.6} style={{ position: "absolute", left: 1240, top: 760 }}>
      <Hand size={46} color={C.fog}>half the context… then all of it</Hand>
    </Appear>
    <Appear at={16.0} from="pop" style={{ position: "absolute", left: 1480, top: 860 }}>
      <Sticky rotate={4} size={70}>Science! 🧪</Sticky>
    </Appear>
  </>
);

export const Code: React.FC = () => (
  <Scene audio="09-code" halo={{ x: 1500, y: 500, size: 900 }}>
    <CodeContent />
  </Scene>
);

/* ---------- 10. Close ---------- */

const CloseContent: React.FC = () => {
  const strike = useRamp(1.0, 1.5);
  const t = useSeconds();
  return (
    <>
      <Appear at={0} style={{ position: "absolute", top: 170, width: "100%", display: "flex", justifyContent: "center" }}>
        <div style={{ position: "relative" }}>
          <Title size={120}>
            Stop tuning by <span style={{ position: "relative" }}>vibes.<span style={{ position: "absolute", left: -6, right: -6, top: "55%", height: 8, background: C.redInk, borderRadius: 4, scale: `${strike} 1`, transformOrigin: "left" }} /></span>
          </Title>
          <Appear at={1.4} from="pop" style={{ position: "absolute", right: -40, top: -70 }}>
            <Hand size={80} color={C.greenInk} style={{ rotate: "-6deg" }}>data!</Hand>
          </Appear>
        </div>
      </Appear>
      <Appear at={2.0} style={{ position: "absolute", top: 430, width: "100%", display: "flex", justifyContent: "center" }}>
        <Pill bg={C.graphite} color={C.white} style={{ fontFamily: mono, fontSize: 50, padding: "22px 48px" }}>$ pip install tunarag-python</Pill>
      </Appear>
      <Appear at={3.6} style={{ position: "absolute", top: 600, width: "100%", display: "flex", justifyContent: "center", alignItems: "center", gap: 30 }}>
        <Glyph size={90} wiggle={Math.sin(t * 1.6) * 0.5 + 0.5} />
        <div style={{ fontSize: 38, fontWeight: 600 }}>shivamshinde123.github.io/tunarag-python</div>
      </Appear>
      <Appear at={4.4} style={{ position: "absolute", top: 700, width: "100%", textAlign: "center", fontSize: 32, color: C.fog, fontWeight: 500 }}>
        open source · LangChain · LangGraph · Google ADK · Python 3.10–3.13
      </Appear>
      <Appear at={5.4} from="pop" style={{ position: "absolute", top: 780, width: "100%", display: "flex", justifyContent: "center" }}>
        <Pill bg={C.mint} style={{ fontSize: 36 }}>🏆 the data picks the winner</Pill>
      </Appear>
      <Appear at={7.4} from="pop" style={{ position: "absolute", top: 880, width: "100%", display: "flex", justifyContent: "center" }}>
        <Hand size={96}>Happy tuning!</Hand>
      </Appear>
    </>
  );
};

export const Close: React.FC = () => (
  <Scene audio="10-close" halo={{ x: 960, y: 480, size: 1300 }}>
    <CloseContent />
  </Scene>
);
