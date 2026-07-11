import * as React from "react";
import { Thoughts } from "true-north-ui";

// Reasoning text as the agent actually streams it (Responses API summaries).
const REASONING = `Resolving gross margin

I need to start by getting the schema for the new conversation. Once I have that figured out, I can then focus on resolving the gross margin. It feels like a logical step to begin with the schema first, as it sets the foundation for everything else.

Choosing the breakdown

The user asked for margin by category, so category is the grouping dimension. The metric context lists a caveat that COGS uses realized transacted cost, not SKU list cost — I should carry that caveat into the answer so the number isn't misread.`;

export const ThinkingLive = () => <Thoughts text={REASONING} live={true} />;

export const CollapsedAfterRun = () => <Thoughts text={REASONING} live={false} />;
