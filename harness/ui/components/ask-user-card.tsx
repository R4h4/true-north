"use client";

// Human-in-the-loop choice card: the agent's ask_user tool renders one of
// these when a business term is ambiguous or a metric wasn't found.
export function AskUserCard({
  question,
  options,
  answered,
  onSelect,
}: {
  question: string;
  options: string[];
  answered: boolean;
  onSelect?: (option: string) => void;
}) {
  return (
    <div className="ask-user-card">
      <p>{question}</p>
      {!answered && onSelect ? (
        options.map((option) => (
          <button key={option} onClick={() => onSelect(option)}>
            {option}
          </button>
        ))
      ) : (
        <span className="answered">✓ answered</span>
      )}
    </div>
  );
}
