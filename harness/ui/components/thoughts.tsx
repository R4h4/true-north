"use client";

import { useEffect, useRef, useState } from "react";

// ChatGPT-style collapsible reasoning block: expanded and auto-following
// while the agent thinks, auto-collapses to a "Thoughts" toggle when done.
export function Thoughts({ text, live }: { text: string; live: boolean }) {
  // null = automatic (follow `live`); true/false = user override.
  const [open, setOpen] = useState<boolean | null>(null);
  const expanded = open ?? live;
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (live && expanded && body.current) body.current.scrollTop = body.current.scrollHeight;
  }, [text, live, expanded]);
  return (
    <div className="thoughts">
      <button className="thoughts-toggle" onClick={() => setOpen(!expanded)}>
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          className={expanded ? "chev open" : "chev"}
          aria-hidden="true"
        >
          <path d="M3 1.5 7 5 3 8.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {live ? "Thinking…" : "Thoughts"}
      </button>
      {expanded && (
        <div className="thoughts-body" ref={body}>
          {text.replace(/\*\*/g, "")}
        </div>
      )}
    </div>
  );
}
