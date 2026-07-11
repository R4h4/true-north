"use client";

import { CopilotKit, useCoAgent, useCopilotAction } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";
import { useState } from "react";
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

function Workbench() {
  // Shared state streamed by the backend (STATE_SNAPSHOT events).
  const { state } = useCoAgent<{ kg_context?: KgGraph }>({ name: "true-north" });

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
        <h2>What the agent knows so far</h2>
        <p className="hint">Live knowledge-graph context · 🔒 = exists but not accessible to your role</p>
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
        <h1>True North</h1>
        <span className="tag">governed BI · every answer via the tn contract</span>
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
