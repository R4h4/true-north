# True North — hero demo video

A programmatic [Remotion](https://remotion.dev) recreation of the True North
governed-BI harness, told as a 6-scene "governed story". Everything is drawn
from the app's own design language (IBM Plex, violet accent, floating panes,
compass mark) and real Consumer Lending numbers — no screen capture.

## The story

| Scene | Beat | What it shows |
|-------|------|---------------|
| 1 Hero | Ask anything | Empty state, compass mark, live-typed question |
| 2 Ambiguity | Governed clarification | "Delinquency" is ambiguous → 3 measures offered, KG shows each concept and its metric |
| 3 Answer | Governed answer | NPL-by-product bar chart with caveats + governed footer; KG provenance path highlights |
| 4 Denial | Access with a reason | Partnerships role is denied delinquency, told why, offered alternatives; KG metrics render restricted |
| 5 Dashboard | Portfolio health | KPI + NPL-over-time dashboard, Ken-Burns; illustrative KPIs tagged |
| 6 Outro | CTA | "True North · Trust answers for your business" |

The numbers in Scene 3 (cash_loan 6.9%, CD installment / credit_card 1.1%,
two-wheeler 0.1%) match the generated Consumer Lending dataset. KPIs marked
`illustrative` in Scene 5 are flagged in-frame so the demo never implies a
precision it doesn't have.

## Run it

```bash
cd harness/video
npm install
npm run studio      # interactive preview at localhost:3000
npm run render      # → out/truenorth-hero.mp4 (1920×1080, 30fps, h264)
npm run still -- HeroVideo out/frame.png --frame=620   # single frame
npm run typecheck
```

`out/` and `node_modules/` are gitignored; only source is committed.

## Layout

```
src/
  Root.tsx, index.ts, HeroVideo.tsx   composition registration + master timeline
  scenes/Scene1..6*.tsx               one file per beat, local-frame timing
  chrome/                             AppFrame, Conversation, KgPanel, BrandMark
  charts/                             Chart (hbar/line/kpi), Dashboard
  data/lending.ts, data/kg.ts         copy + KG layouts (edit these to retune)
  lib/                                Cursor, Typewriter, timing helpers
  theme/tokens.ts, theme/fonts.ts     ported globals.css tokens + fonts
```

This is a standalone dependency island: it does not touch the `harness/ui`
Next.js app or the `uv` Python workspace. Retuning copy or KG shape is almost
always a `data/*.ts` edit; timing lives at the top of each `scenes/*.tsx`.
