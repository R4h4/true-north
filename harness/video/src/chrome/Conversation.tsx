// Conversation surfaces ported from the app: empty hero, user bubble, thoughts
// row, tool-step rows, answer card, ambiguity card, denial card. Kept in one
// file since each is small and they share tokens.
import React from "react";
import { C, SHADOW_CARD } from "../theme/tokens";
import { FONT_SANS, FONT_MONO } from "../theme/fonts";
import { BrandMark } from "./BrandMark";
import { Typewriter } from "../lib/Typewriter";
import { fadeUp } from "../lib/timing";
import { useCurrentFrame } from "remotion";

// Empty-state hero: greeting + centered input (optionally typing a question).
export const EmptyHero: React.FC<{
  typeStart?: number;
  question?: string;
  placeholder?: string;
}> = ({ typeStart, question, placeholder = "Ask about disbursements, NPL, collections — anything in your data…" }) => {
  const frame = useCurrentFrame();
  const typing = typeStart !== undefined && question !== undefined;
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 30,
        padding: 40,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, ...fadeUp(frame, 4) }}>
        <BrandMark size={52} />
        <div style={{ fontSize: 30, fontWeight: 700, color: C.inkStrong, letterSpacing: "-0.03em" }}>
          Ask your governed data anything
        </div>
        <div style={{ fontSize: 18, color: C.inkSecondary, maxWidth: 620, textAlign: "center", lineHeight: 1.5 }}>
          Every answer is resolved through the semantic layer — one definition of the truth, per persona access policy.
        </div>
      </div>
      <div
        style={{
          width: 720,
          minHeight: 96,
          background: C.surface,
          border: `1px solid ${C.borderStrong}`,
          borderRadius: 14,
          boxShadow: SHADOW_CARD,
          padding: "22px 24px",
          fontSize: 19,
          color: typing ? C.ink : C.muted,
          display: "flex",
          alignItems: "flex-start",
          ...fadeUp(frame, 10),
        }}
      >
        {typing ? <Typewriter text={question!} startFrame={typeStart!} /> : placeholder}
      </div>
    </div>
  );
};

export const UserBubble: React.FC<{ text: string; delay?: number }> = ({ text, delay = 0 }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ display: "flex", justifyContent: "flex-end", ...fadeUp(frame, delay, { rise: 6 }) }}>
      <div
        style={{
          background: C.accentTint,
          color: "#2c2350",
          borderRadius: "14px 14px 4px 14px",
          padding: "12px 18px",
          fontSize: 18,
          fontWeight: 450,
          maxWidth: "78%",
        }}
      >
        {text}
      </div>
    </div>
  );
};

export const Thoughts: React.FC<{ seconds: number; delay?: number }> = ({ seconds, delay = 0 }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, color: C.muted, fontSize: 16, fontWeight: 500, ...fadeUp(frame, delay) }}>
      <span style={{ fontSize: 13 }}>▸</span>
      <span>Thought for {seconds}s</span>
    </div>
  );
};

export const ToolStep: React.FC<{ label: string; mono?: string; done: boolean; delay?: number }> = ({
  label,
  mono,
  done,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        fontSize: 15.5,
        color: C.ink,
        paddingLeft: 10,
        borderLeft: `2px solid ${C.border}`,
        ...fadeUp(frame, delay),
      }}
    >
      {done ? (
        <span style={{ color: C.green, fontWeight: 700 }}>✓</span>
      ) : (
        <span
          style={{
            width: 13,
            height: 13,
            borderRadius: "50%",
            border: `2px solid ${C.border}`,
            borderTopColor: C.accent,
            transform: `rotate(${(frame * 12) % 360}deg)`,
            display: "inline-block",
          }}
        />
      )}
      <span>{label}</span>
      {mono && <span style={{ fontFamily: FONT_MONO, fontSize: 14, color: C.muted }}>{mono}</span>}
    </div>
  );
};

export const AnswerCard: React.FC<{ children: React.ReactNode; asOf?: string; delay?: number }> = ({
  children,
  asOf = "2025-12-31",
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 12,
        boxShadow: SHADOW_CARD,
        overflow: "hidden",
        ...fadeUp(frame, delay),
      }}
    >
      <div style={{ padding: "16px 18px 6px" }}>{children}</div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          padding: "10px 18px",
          borderTop: `1px solid ${C.border}`,
          fontSize: 13,
          color: C.muted,
        }}
      >
        <span>product · npl_ratio</span>
        <span>Governed by tn contract · as of {asOf}</span>
      </div>
    </div>
  );
};

export const AskUserCard: React.FC<{
  prompt: string;
  options: { title: string; sub: string }[];
  selected: number;
  reveal: number; // 0..1, controls highlight of the selected row
  delay?: number;
}> = ({ prompt, options, selected, reveal, delay = 0 }) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        background: C.surface,
        border: `1px solid ${C.borderStrong}`,
        borderRadius: 12,
        boxShadow: SHADOW_CARD,
        padding: "20px 22px",
        fontFamily: FONT_SANS,
        ...fadeUp(frame, delay),
      }}
    >
      <div style={{ fontSize: 18, fontWeight: 600, color: C.inkStrong, marginBottom: 16 }}>{prompt}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {options.map((o, i) => {
          const picked = i === selected && reveal > 0.5;
          return (
            <div
              key={o.title}
              style={{
                border: `1px solid ${picked ? C.accent : C.border}`,
                background: picked ? C.accentTint : C.surface,
                borderRadius: 10,
                padding: "12px 16px",
                fontSize: 16,
                boxShadow: picked ? `0 0 0 3px rgba(124,92,240,0.15)` : "none",
              }}
            >
              <span style={{ fontWeight: 600, color: C.ink }}>{o.title}</span>
              <span style={{ color: C.inkSecondary }}> — {o.sub}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const DenialCard: React.FC<{
  headline: string;
  reason: string;
  alternatives: string[];
  delay?: number;
}> = ({ headline, reason, alternatives, delay = 0 }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ fontFamily: FONT_SANS, ...fadeUp(frame, delay) }}>
      <div style={{ fontSize: 20, fontWeight: 600, color: C.inkStrong, marginBottom: 14 }}>{headline}</div>
      <div
        style={{
          borderLeft: `3px solid ${C.red}`,
          background: C.redTint,
          borderRadius: "0 8px 8px 0",
          padding: "12px 16px",
          fontSize: 16,
          color: C.ink,
          lineHeight: 1.5,
          marginBottom: 18,
        }}
      >
        <span style={{ fontWeight: 600, color: C.red }}>Reason: </span>
        {reason}
      </div>
      <div style={{ fontSize: 16, fontWeight: 600, color: C.ink, marginBottom: 8 }}>What you can see instead:</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {alternatives.map((a) => (
          <div key={a} style={{ fontSize: 15.5, color: C.inkSecondary }}>• {a}</div>
        ))}
      </div>
    </div>
  );
};
