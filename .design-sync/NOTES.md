# design-sync notes — true-north-ui

Repo-specific gotchas for re-syncs. Source is the Next.js app at `harness/ui`
(NOT a packaged library): no dist, no Storybook — the converter runs in
synth-entry mode over `harness/ui/components/`.

- **Package-resolution shim (critical).** npm never self-installs, so the
  converter can't find `node_modules/true-north-ui`. A plain self-symlink
  recurses infinitely (`pkg -> node_modules -> pkg…`) and crashes ts-morph
  with ENAMETOOLONG. The fix is a shim DIRECTORY at
  `harness/ui/node_modules/true-north-ui/` containing only: symlinks to
  `package.json`, `components/`, `app/`, plus a **copy** (not symlink — the
  cssEntry containment check realpaths and rejects escapes) of
  `harness/ui/design-fonts.css`. Recreate per clone/install; the staged
  runner `.ds-sync/convert.sh` does this before every build.
- **Runner scripts.** The scout-block Bash hook in this repo denies commands
  containing literal `node_modules`/`dist`/`build` tokens, so all converter
  invocations live in gitignored `.ds-sync/*.sh` runners (stage.sh,
  convert.sh, validate.sh, capture.sh, rebuild-previews.sh). On a fresh
  clone: re-stage skill scripts per the skill's step-7 `cp -r` line, then
  recreate the runners (each is 5-10 lines; convert.sh builds the shim above,
  then `node .ds-sync/package-build.mjs --config .design-sync/config.json
  --node-modules harness/ui/node_modules --out ./ds-bundle`).
- **Converter deps.** `.ds-sync` needs `esbuild ts-morph @types/react
  playwright typescript@5.9.3`. Pin typescript 5.x: `typescript@latest`
  (the Go-based compiler) has no `createSourceFile` on its module surface
  and silently skips validate's `.d.ts` parse check.
- **Fonts.** The app loads Inter via `next/font` (layout.tsx), which also
  defines `--font-inter` at runtime — neither exists outside Next. The
  repo-committed `harness/ui/design-fonts.css` (cfg.cssEntry) supplies a
  Google-Fonts remote `@import` plus a `--font-inter` fallback; validate
  reports `[FONT_REMOTE] Inter` — expected, not a gap.
- **dtsPropsFor is the API source of truth.** Synth-entry mode extracts no
  props (all `.d.ts` fell back to index signatures), so every prop-bearing
  component's interface is hand-written in `cfg.dtsPropsFor`. When a
  component's props change in `harness/ui/components/`, update the config
  entry in the same PR.
- Preview data is REAL output from tn governed queries (small/seed-42):
  gross margin by category (Laptop -236.3 tỷ), b2b 100% repeat-purchase rate
  (a deliberate dataset trap — see source/data/TRAPS.md; do not "fix" it in
  previews), total net revenue 5,885 tỷ.

## Known render warns

- (none currently — BrandMark's `[RENDER_THIN]` cleared once its authored
  preview composed the mark with the wordmark row.)

## Re-sync risks

- **Inline preview data drifts by design**: chart numbers were copied from
  live seed-42 query output; regenerating the dataset with another seed or
  scale changes real numbers but NOT these previews. Cosmetic only — refresh
  when convenient.
- **cfg.dtsPropsFor duplicates the components' TypeScript props** — it goes
  stale silently if someone edits component props without updating config.
- **app/globals.css is the whole styling surface** (`tokensGlob`); its
  `body { height: 100vh; overflow: hidden }` ships to designs. The
  conventions header teaches the shell pattern; if the app ever splits
  tokens from app-shell CSS, point `tokensGlob` at the tokens file instead.
- **Assumed toolchain**: node 24, npm; chromium via playwright cache
  (macOS path `~/Library/Caches/ms-playwright`).
- Verified only on the 6 exported components; page-level chrome (chat pane,
  suggestion chips — CopilotKit-rendered) is deliberately out of scope.
