"use client";

import { useState } from "react";
import { BrandMark } from "./brand-mark";

// Claude-style empty chat, in two parts:
// - EmptyStateGreeting: overlay above the (CSS-centered) input
// - SuggestionsPanel: sources bar + icon chips, plugged into CopilotChat's
//   RenderSuggestionsList slot so chip clicks go through the chat's own send
//   path (the headless hooks write to a separate message store).
// The sources are placeholders - the demo warehouse is the only live source.

export function EmptyStateGreeting() {
  return (
    <div className="chat-hero">
      <div className="hero-greeting">
        <BrandMark size={46} />
        <h3>Ask your governed data anything</h3>
        <p>
          Every answer is resolved through the semantic layer — one definition of the truth, per
          persona access policy.
        </p>
      </div>
    </div>
  );
}

const SOURCES = [
  { id: "pg", label: "Postgres", mono: "Pg", bg: "var(--blue-tint)", fg: "#3b5a8a" },
  { id: "my", label: "MySQL", mono: "My", bg: "#fdf6e3", fg: "var(--amber)" },
  { id: "bq", label: "BigQuery", mono: "BQ", bg: "var(--blue-tint)", fg: "#3b5a8a" },
  { id: "sf", label: "Snowflake", mono: "Sf", bg: "var(--surface-subtle)", fg: "var(--ink-secondary)" },
  { id: "rs", label: "Redshift", mono: "Rs", bg: "var(--red-tint)", fg: "var(--red)" },
  { id: "dw", label: "Warehouse", mono: "DW", bg: "var(--green-tint)", fg: "var(--green-dark)" },
];

const CHIP_ICONS = [
  // bar chart
  <svg key="bars" width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
    <path d="M3 13V8M8 13V3M13 13v-7" />
  </svg>,
  // trend line
  <svg key="trend" width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M2 12l4-4 3 2 5-6" />
    <path d="M10 4h4v4" />
  </svg>,
  // table grid
  <svg key="grid" width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <rect x="2.5" y="2.5" width="11" height="11" rx="1.5" />
    <path d="M2.5 6.5h11M6.5 6.5v7" />
  </svg>,
];

// Matches CopilotChat's RenderSuggestionsList contract.
export function SuggestionsPanel({
  suggestions,
  onSuggestionClick,
}: {
  suggestions: { title: string; message: string }[];
  onSuggestionClick: (message: string) => void;
  isLoading?: boolean;
}) {
  const [sourcesOpen, setSourcesOpen] = useState(true);
  if (!suggestions?.length) return null;

  return (
    <div className="suggestions-panel">
      {sourcesOpen && (
        <div className="sources-bar">
          <span className="sources-label">Get better answers from your data sources</span>
          <span className="sources-tiles">
            {SOURCES.map((s) => (
              <span key={s.id} className="source-tile" title={s.label} style={{ background: s.bg, color: s.fg }}>
                {s.mono}
              </span>
            ))}
          </span>
          <button className="sources-close" aria-label="Dismiss" onClick={() => setSourcesOpen(false)}>
            <svg width="12" height="12" viewBox="0 0 12 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
              <path d="M2.5 2.5l7 7M9.5 2.5l-7 7" />
            </svg>
          </button>
        </div>
      )}
      <div className="hero-chips">
        {suggestions.map((s, i) => (
          <button key={s.title} className="hero-chip" onClick={() => onSuggestionClick(s.message)}>
            {CHIP_ICONS[i % CHIP_ICONS.length]}
            {s.title}
          </button>
        ))}
      </div>
    </div>
  );
}
