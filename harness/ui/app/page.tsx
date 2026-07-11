"use client";

import { CopilotKit, useCoAgent, useCopilotAction } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";
import { useEffect, useRef, useState } from "react";
import { ChartView, type ChartPayload } from "../components/chart-view";
import { KgPanel, type KgGraph } from "../components/kg-panel";

function safeParse(s: string): any {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

// The CopilotKit dev inspector persists isOpen in localStorage - one stray
// click and it overlays every page load after that. Force it closed before
// CopilotKit mounts (module scope runs pre-render on the client).
if (typeof window !== "undefined") {
  const state = safeParse(localStorage.getItem("cpk:inspector:state") ?? "");
  if (state?.isOpen) {
    localStorage.setItem("cpk:inspector:state", JSON.stringify({ ...state, isOpen: false }));
  }
}

const PERSONAS = [
  { id: "mai", label: "Mai · Executive" },
  { id: "duc", label: "Đức · RM South" },
  { id: "lan", label: "Lan · Marketing" },
  { id: "binh", label: "Bình · Analyst" },
];

// Human-readable labels for the governed tools; the step timeline renders
// only tools listed here (render_chart / ask_user have their own renderers).
const TOOL_STEPS: Record<string, string> = {
  get_kg_schema: "Loading knowledge-graph schema",
  resolve_term: "Resolving business term",
  get_metric_context: "Loading metric context",
  check_metric_access: "Checking metric access",
  list_metrics: "Listing governed metrics",
  describe_metric: "Inspecting metric definition",
  query_warehouse: "Running governed query",
};

const ARG_KEYS = ["term", "metric_key", "metric_keys", "metric", "group_by", "time_grain", "filter", "start", "end"];

function argSummary(args: any): string {
  if (!args || typeof args !== "object") return "";
  const parts: string[] = [];
  for (const key of ARG_KEYS) {
    const v = args[key];
    if (v && String(v).trim()) parts.push(`${key}=${Array.isArray(v) ? v.join(",") : v}`);
  }
  return parts.join("  ");
}

function StepCheck() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <path d="M2.5 6.5 5 9l4.5-6" stroke="#259b6c" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// One row of the agent's visible act loop: tool choice + arguments, live.
function ToolStep({ name, args, status }: { name: string; args: any; status: string }) {
  const label = TOOL_STEPS[name];
  if (!label) return <></>;
  return (
    <div className="tool-step">
      {status === "complete" ? <StepCheck /> : <span className="step-spinner" aria-label="running" />}
      <span className="step-label">{label}</span>
      <span className="step-args">{argSummary(args)}</span>
    </div>
  );
}

// Compass-in-hexagon brand mark, drawn in the brand green.
function BrandMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 2.5 20.2 7.25v9.5L12 21.5 3.8 16.75v-9.5L12 2.5Z"
        stroke="#259b6c"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M12 6.5 14 12l-2 5.5L10 12l2-5.5Z" fill="#259b6c" />
    </svg>
  );
}

// Live reasoning-summary stream (mirrored into shared state by the server,
// since CopilotKit's chat drops AG-UI reasoning events). Auto-follows.
function ThinkingBox({ text }: { text: string }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [text]);
  return (
    <div className="thinking-box">
      <h2>Agent reasoning</h2>
      <div className="thinking-scroll" ref={box}>
        {text.replace(/\*\*/g, "")}
      </div>
    </div>
  );
}

function Workbench() {
  // Shared state streamed by the backend (STATE_SNAPSHOT events).
  const { state } = useCoAgent<{ kg_context?: KgGraph; thinking?: string }>({ name: "true-north" });

  // ask_user: the agent's human-in-the-loop tool. Rendering happens here;
  // the adapter proxies it to the model as a frontend tool per thread.
  useCopilotAction({
    name: "ask_user",
    description:
      "Ask the user to choose between options - required for ambiguous metric variants and metric-not-found candidates.",
    parameters: [
      { name: "question", type: "string", required: true },
      { name: "options", type: "string[]", required: true },
    ],
    renderAndWaitForResponse: ({ args, respond, status }) => (
      <div className="ask-user-card">
        <p>{args.question}</p>
        {status !== "complete" && respond ? (
          (args.options ?? []).map((option: string) => (
            <button key={option} onClick={() => respond(option)}>
              {option}
            </button>
          ))
        ) : (
          <span className="answered">✓ answered</span>
        )}
      </div>
    ),
  });

  // Wildcard render: every backend tool call streams as an AG-UI tool event;
  // this turns each one into a visible step row (plan -> tool choice -> act).
  useCopilotAction({
    name: "*",
    render: ({ name, args, status }: any) => <ToolStep name={name} args={args} status={status} />,
  });

  // render_chart runs in Python (rows come from the governed envelope);
  // available: "disabled" means we only RENDER the tool call - the action is
  // never advertised to the model, so it can't collide with the backend tool.
  useCopilotAction({
    name: "render_chart",
    available: "disabled",
    render: ({ status, result }) => {
      if (status !== "complete") return <p className="hint">rendering chart…</p>;
      const parsed = typeof result === "string" ? safeParse(result) : result;
      if (!parsed?.ok || !parsed.chart) return <></>;
      return <ChartView chart={parsed.chart as ChartPayload} />;
    },
  });

  return (
    <div className="main">
      <div className="chat-pane">
        <CopilotChat
          labels={{
            title: "True North",
            initial:
              "Ask a business question — e.g. “How is our customer retention doing by channel?”",
          }}
        />
      </div>
      <div className="kg-pane">
        {(state?.thinking ?? "").trim() && <ThinkingBox text={state!.thinking!} />}
        <h2>What the agent knows so far</h2>
        <p className="hint">Live knowledge-graph context · locked = exists but not accessible to your role</p>
        <div className="kg-canvas">
          <KgPanel graph={state?.kg_context} />
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  const [persona, setPersona] = useState("binh");
  return (
    <div className="shell">
      <div className="topbar">
        <div className="brand">
          <BrandMark />
          <h1>True North</h1>
        </div>
        <span className="tag">Governed BI · tn contract</span>
        <div className="persona-picker">
          {PERSONAS.map((p) => (
            <button
              key={p.id}
              className={p.id === persona ? "active" : ""}
              onClick={() => setPersona(p.id)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
      {/* key={persona}: switching persona starts a fresh thread - tokens never
          mix mid-conversation (matches the backend's per-session freeze). */}
      <CopilotKit
        key={persona}
        runtimeUrl="/api/copilotkit"
        agent="true-north"
        properties={{ persona }}
        showDevConsole={false}
      >
        <Workbench />
      </CopilotKit>
    </div>
  );
}
