import * as React from "react";
import { AskUserCard } from "true-north-ui";

// The real ambiguity the governed KG raises for "customer retention".
const QUESTION =
  "“Customer retention” has multiple governed variants. Which one should I use for retention by channel?";
const OPTIONS = [
  "Repeat-purchase rate (90d) — share of customers whose second purchase is within 90 days of first purchase",
  "Member active rate (30d) — share of loyalty members active in the trailing 30 days",
];

export const OpenQuestion = () => (
  <AskUserCard question={QUESTION} options={OPTIONS} answered={false} onSelect={() => {}} />
);

export const Answered = () => (
  <AskUserCard question={QUESTION} options={OPTIONS} answered={true} />
);
