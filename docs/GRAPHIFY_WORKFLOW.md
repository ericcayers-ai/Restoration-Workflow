# Using graphify to build this project

This project uses [graphify](https://github.com/safishamsi/graphify) as a working tool during
development, not as a one-off documentation step. Any AI agent picking up work on this
codebase should treat `graphify-out/graph.json` (once it exists) as the fastest path to
understanding current state — faster and more reliable than re-reading every file from
scratch every session.

## Why this matters here specifically

This repo starts as almost pure planning documentation (this ROADMAP and its supporting
docs) and grows into a real polyglot codebase (Python backend, TypeScript/React frontend,
Rust/Tauri shell, per-model plugin folders). That mix — docs that describe an architecture,
and code that implements it — is exactly what graphify's community detection and
"surprising connections" analysis is good at surfacing: it will show, concretely, whether the
code that got built actually matches the layering this roadmap describes, not just whether it
compiles.

## When to run it

- **Now, once this document set is written** (`ROADMAP.md`, `ARCHITECTURE.md`,
  `UI_DESIGN.md`, `MODEL_STACK.md`, this file): run `/graphify .` once to build the first
  graph over the planning corpus. This seeds a queryable map of the plan itself before any
  code exists — later, as real files are added, the same graph gains code nodes that connect
  back to the doc nodes that specified them.
- **At the end of every roadmap phase** (see `ROADMAP.md`): run `/graphify . --update`
  (incremental — only re-extracts new/changed files, cheap). This is a required step in each
  phase's Definition of Done, not optional cleanup.
- **At the start of any new work session or task**, before grepping around the codebase by
  hand: run `/graphify query "<question>"` against the existing graph first. Examples that
  will actually come up during this build:
  - `/graphify query "What implements the RestorationNode interface?"`
  - `/graphify query "What calls the pipeline executor?"`
  - `/graphify query "Where is VRAM tier checked before a node runs?"`
- **When documenting a core abstraction** for other contributors (or future AI sessions):
  run `/graphify explain "PipelineExecutor"` (or `WeightManager`, `DegradationAnalyzer`, etc.)
  to get a plain-language explanation seeded from the actual graph rather than writing prose
  from memory that can drift from the real code.
- **When verifying the architecture hasn't drifted**: run
  `/graphify path "SimpleMode" "WeightManager"` occasionally to confirm the intended layering
  in `ARCHITECTURE.md` still holds — e.g. Simple Mode should only ever reach the Weight
  Manager *through* the pipeline executor, never directly. If a shortest path shows a direct
  edge that shouldn't exist, that's a real architecture violation to fix before it calcifies,
  not a false positive to ignore.
- **After each phase**, skim the God Nodes and Surprising Connections sections of
  `graphify-out/GRAPH_REPORT.md`. A god node appearing somewhere unexpected (e.g. a UI
  component becoming a dependency hub that half the backend imports from) is an early,
  cheap signal of a layering problem — much cheaper to catch here than after Phase 6's
  plugin SDK has three plugins depending on that same accidental hub.

## Repo setup already in place

- `.graphify_hook_installed` — the post-commit auto-rebuild hook marker already exists in
  this repo. Once real commits start landing, the graph rebuilds itself automatically; no one
  needs to remember to run `--update` by hand on every commit (the phase-end `--update` above
  is still worth doing explicitly, since it's the checkpoint where you actually go read the
  report, not just regenerate it).
- `.graphifyignore` was adjusted for this project (see the diff in the same commit as this
  file) to **include** markdown docs rather than exclude them, which is graphify's usual
  default for software repos. That default exists to cut noise on typical projects where docs
  are secondary; here, during the planning-heavy early phases, the docs *are* the spec, so
  excluding them would mean graphify only ever sees an empty or near-empty corpus. Once the
  codebase is substantial and the docs are stable reference material rather than active spec,
  it's fine to revisit that call — but don't flip it back by default just because it matches
  graphify's stock template.

## What not to do

- Don't skip the phase-end `--update` because "nothing important changed" — let the graph
  and its god-node/surprising-connections analysis be the judge of that, not assumption.
  Cheap incremental updates exist specifically so this isn't a costly step to run often.
  - Don't treat a graphify query answer as ground truth if it's answering from a stale graph
  — if you know real code changed since the last `--update` and haven't rebuilt, say so and
  rebuild before trusting the query result over your own recent memory of the change.
- Don't hand-author a "how the pieces connect" doc from scratch when `/graphify explain` can
  generate a first draft grounded in what's actually in the code — edit that draft for
  clarity, don't skip straight to writing prose from assumption.
