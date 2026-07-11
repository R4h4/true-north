"use client";

import {
  CopilotKit,
  useCoAgent,
  useCopilotAction,
  useCopilotChatSuggestions,
} from "@copilotkit/react-core";
import {
  AssistantMessage as CopilotAssistantMessage,
  CopilotChat,
  type AssistantMessageProps,
} from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";
import { useState } from "react";
import { AskUserCard } from "../components/ask-user-card";
import { BrandMark } from "../components/brand-mark";
import { ChartView, type ChartPayload } from "../components/chart-view";
import { KgPanel, type KgGraph } from "../components/kg-panel";
import { Thoughts } from "../components/thoughts";
import { ToolStep } from "../components/tool-step";

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

// Conversation starters per persona - each exercises a governed path that
// demos well for that role (KPI, trend, row filter, denial, ambiguity...).
const SUGGESTIONS: Record<string, string[]> = {
  mai: [
    "What is our total net revenue?",
    "Show me the monthly net revenue trend for 2025",
    "How does net revenue split by region?",
  ],
  duc: [
    "How is net revenue doing in my region?",
    "Net revenue by channel, please",
    "Show me the monthly net revenue trend for 2025",
  ],
  lan: [
    "How is our customer retention doing by channel?",
    "What is our gross margin by category?",
    "Which metrics can I access?",
  ],
  binh: [
    "How is our customer retention doing by channel?",
    "What is our gross margin by category?",
    "What is the average basket value by channel?",
  ],
};


// The reasoning block anchors to the FIRST assistant message after the last
// user message, so it leads the turn like ChatGPT's "Thought for Ns".
function isThoughtsAnchor(message?: { id?: string }, messages?: { id?: string; role?: string }[]): boolean {
  if (!message?.id || !messages) return false;
  let lastUser = -1;
  messages.forEach((m, i) => {
    if (m.role === "user") lastUser = i;
  });
  const firstAssistant = messages.slice(lastUser + 1).find((m) => m.role === "assistant");
  return firstAssistant?.id === message.id;
}

function AssistantMessageWithThoughts(props: AssistantMessageProps) {
  // `running` covers the whole agent run - the anchor message itself finishes
  // long before the reasoning does (tool loop), so per-message isGenerating
  // would collapse the block mid-thought.
  const { state, running } = useCoAgent<{ thinking?: string }>({ name: "true-north" });
  const thinking = (state?.thinking ?? "").trim();
  const anchor = isThoughtsAnchor(props.message as any, props.messages as any);
  return (
    <>
      {anchor && thinking && <Thoughts text={thinking} live={running} />}
      <CopilotAssistantMessage {...props} />
    </>
  );
}

function Workbench({ persona }: { persona: string }) {
  // Shared state streamed by the backend (STATE_SNAPSHOT events).
  const { state } = useCoAgent<{ kg_context?: KgGraph; thinking?: string }>({ name: "true-north" });

  // Conversation starters, rendered natively by CopilotChat until the first
  // user message; tailored per persona.
  useCopilotChatSuggestions(
    {
      suggestions: (SUGGESTIONS[persona] ?? []).map((q) => ({ title: q, message: q })),
      available: "before-first-message",
    },
    [persona],
  );

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
      <AskUserCard
        question={args.question ?? ""}
        options={args.options ?? []}
        answered={status === "complete" || !respond}
        onSelect={respond}
      />
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
            initial: "Where do you want to steer today?",
          }}
          AssistantMessage={AssistantMessageWithThoughts}
        />
      </div>
      <div className="kg-pane">
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
        <Workbench persona={persona} />
      </CopilotKit>
    </div>
  );
}
