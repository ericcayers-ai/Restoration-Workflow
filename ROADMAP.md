# Roadmap

This is the build plan for turning [`docs/ORIGINAL_IDEA.md`](docs/ORIGINAL_IDEA.md)'s
planning notes into a real, shipped application (now `README.md` describes the shipped
app itself, not the plan). It's written for an AI coding agent to execute phase by phase — each phase has
a goal, concrete tasks, an acceptance criterion you can actually check against (not "looks
done"), and a graphify checkpoint. Supporting detail lives in four sibling documents; this
file is the spine that ties them together and sequences the work:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — backend, frontend, execution engine, packaging
- [`docs/UI_DESIGN.md`](docs/UI_DESIGN.md) — visual identity, layout, accessibility rules
- [`docs/MODEL_STACK.md`](docs/MODEL_STACK.md) — every restoration model, fact-checked, licensed, tiered
- [`docs/GRAPHIFY_WORKFLOW.md`](docs/GRAPHIFY_WORKFLOW.md) — how graphify is used at every phase boundary

## Vision

A photo restoration tool that is genuinely two things at once, not a compromise between them:

1. **Instant.** Drop a photo in, get a materially better photo out, with zero configuration.
   This is Phase 2 and it is not optional or secondary to the "real" product — it's the first
   thing most users will ever experience, and it needs to work with no manual selected on a
   fresh photo the first time.
2. **Completely open underneath.** Every choice the instant path made is inspectable and
   overridable in a full node-based studio, and the whole model stack is extensible by anyone
   without touching core code (`docs/ARCHITECTURE.md` §3, §7).

Both modes share one engine — Simple Mode is not a stripped-down separate app, it's Studio
Mode with the auto-analyzer driving the wheel (`docs/ARCHITECTURE.md` §4).

The identity is deliberate, not decorative: see `docs/UI_DESIGN.md` in full before writing any
component. The one-line version — this should read as a piece of well-made equipment, not
another purple-gradient AI SaaS product, and it should not oversell itself in its own copy
either.

## Guardrails (read before every phase, not just once)

- **License tiers in `docs/MODEL_STACK.md` are binding, not advisory.** Simple Mode's default
  pipeline must never silently depend on a non-commercial-only model. Non-commercial and
  unclear-license models are always opt-in, always behind the acknowledgement gate in
  `docs/ARCHITECTURE.md` §6.
- **Don't rebuild what already exists** in this doc set. If a phase's guidance conflicts with
  something you're about to independently decide, the existing doc wins unless you have a
  concrete reason it's wrong — in which case, update the doc in the same change, don't let
  code and docs drift apart. `docs/GRAPHIFY_WORKFLOW.md` exists specifically to make drift
  visible early.
- **Dates matter.** `docs/MODEL_STACK.md` is a snapshot from 2026-07-09. Repo activity and
  licenses change; re-verify anything you're about to build real integration work against if
  meaningful time has passed, rather than trusting a stale snapshot.
- **No feature works "in theory."** Every phase's acceptance criterion is something you can
  actually run and observe, per this repo's own engineering norms — don't mark a phase done
  because the code compiles.

---

## Phase 0 — Foundation, Research & Identity — *complete as of this document set*

**Goal:** ground every later decision in verified facts and a deliberate design identity
before any product code exists.

- [x] Fact-check the entire model list from the original README against live sources
  (`docs/MODEL_STACK.md`).
- [x] Decide the system architecture (`docs/ARCHITECTURE.md`).
- [x] Define the visual/interaction identity (`docs/UI_DESIGN.md`).
- [x] Establish how graphify is used through the rest of the build (`docs/GRAPHIFY_WORKFLOW.md`).
- [x] Build the first graphify knowledge graph over this planning corpus.

**Graphify checkpoint:** `/graphify .` (full build, not incremental — this is the first run).

---

## Phase 1 — Core Engine

**Goal:** a working backend with zero UI — provable entirely from a terminal.

Tasks:
- Scaffold the Python package (backend app, plugin loader, CLI entry point).
- Implement the `RestorationNode` protocol and a plugin registry that discovers nodes from a
  `plugins/` directory (`docs/ARCHITECTURE.md` §3) — build this contract now, even though
  only in-box nodes exist yet, so Phase 6 doesn't require retrofitting it.
- Implement the three Phase-1-tier nodes from `docs/MODEL_STACK.md`: **RealESRGAN**, **FBCNN**,
  **LaMa** — all permissive-licensed, all lightweight, all with existing reference
  implementations to build from.
- Implement the **WeightManager** (`docs/ARCHITECTURE.md` §6): resumable downloads, disk-space
  pre-check, checksum verification, license acknowledgement gate.
- Implement the **HardwareDetector** and VRAM tiering (`docs/ARCHITECTURE.md` §5).
- Implement the **PipelineExecutor** as a general DAG runner, not a linear-only chain, with the
  GPU semaphore and OOM-fallback path from `docs/ARCHITECTURE.md` §4 — build the general case
  now; Phase 2 will only exercise the linear subset of it.
- Stand up the FastAPI app: REST endpoints for node listing/pipeline submission/job status,
  WebSocket progress stream.
- CLI: `restore run --input <file> --preset <json> --output <dir>`.
- Tests: node contract smoke tests (each node runs on a synthetic degraded image without
  error and produces a same-shape output), executor unit tests (topo-sort correctness, OOM
  fallback, pin/unload).

**Acceptance criteria:** `restore run` executes a real RealESRGAN pipeline end-to-end from a
cold terminal, on both a CUDA machine and a CPU-only machine (CPU falls back correctly rather
than erroring).

**Graphify checkpoint:** `/graphify . --update`; confirm `RestorationNode` doesn't already
show up as an unexpected god node this early — if half the codebase already imports it
directly instead of going through the registry, that's a layering leak worth fixing now.

---

## Phase 2 — Simple Mode (instant automation, drag-and-drop MVP)

**Goal:** the actual "drop a photo, get it fixed" deliverable. This is the phase most worth
getting exactly right — it's the app's first impression.

Tasks:
- Implement the **DegradationAnalyzer v1** exactly as specified in `docs/ARCHITECTURE.md` §4:
  heuristic (blur variance, noise estimate, face detection, JPEG blockiness, exposure
  histogram) → `DegradationProfile` → rule-table lookup → default node chain. Ship it as a
  real, inspectable heuristic — not a stub that fakes intelligence.
- Add the three Phase-2-tier face/matting nodes from `docs/MODEL_STACK.md`: **GFPGAN**,
  **RestoreFormer** (v1 — see the implementation note in `docs/MODEL_STACK.md` for why not
  ++), **BiRefNet** — enough category coverage (upscale, JPEG, face, matting) for a genuinely
  useful default auto-pipeline. GFPGAN and RestoreFormer landed early, in Phase 1, because the
  rule table's face stages need them to route anywhere; only **BiRefNet** remains.
- Scaffold the frontend (Vite + React + TypeScript), wire the design tokens from
  `docs/UI_DESIGN.md` §9 into the build's theme layer — component code should reference
  tokens, never hardcoded hex values.
- Build the Simple Mode screen exactly per `docs/UI_DESIGN.md` §7: drop zone → quiet analysis
  status line → staged status text (Developing/Fixing/Washing/Done, mapped to the real
  running node under the hood) → light-table before/after slider (+ side-by-side and
  difference-heatmap toggles) → Save / Compare / Open in Studio / Export actions.
- Wire the WebSocket progress stream from Phase 1 into that status line and the light-table's
  "in progress" state — one source of truth for progress, per `docs/ARCHITECTURE.md` §2.
- Get to a "double-click and it works" local experience — full installer polish is Phase 8,
  but by the end of this phase a non-technical tester should be able to launch the app and
  use it without a terminal.
- Accessibility pass scoped to this screen: keyboard-operable drop zone, ARIA live region
  status announcements, verified contrast on every new component (`docs/UI_DESIGN.md` §6).

**Acceptance criteria:** hand a real degraded photo (not a curated best-case demo image) to
someone with no technical background, with no instructions beyond "try this." They should
get a visibly better photo out with zero configuration, and the screen they used should be
recognizable against `docs/UI_DESIGN.md` §7 point by point, not just "looks fine."

**Graphify checkpoint:** `/graphify . --update`; spot-check the God Nodes section — the
frontend's WebSocket client and the analyzer are reasonable candidates for legitimately high
centrality here, but a UI component showing up as a backend-wide dependency hub would not be.

---

## Phase 3 — Studio Mode (full node canvas, full customizability)

**Goal:** every choice Simple Mode made, made visible and editable — plus real DAG authoring
power Simple Mode never needs.

Tasks:
- Integrate a node-canvas library and retheme it deeply per `docs/UI_DESIGN.md` §8 — no
  library default styling should be visible in the shipped UI.
- Build the four-region layout: Model Stack rail (searchable, category-grouped, VRAM-tier
  badged), Canvas, Inspector (auto-generated from each node's `param_schema`), and the
  Contact Sheet run-history strip.
- Implement branch/merge DAG editing — the executor already supports this from Phase 1, so
  this phase is purely the editor UI catching up to engine capability. Prove it with a real
  use case: run two face-restoration nodes on the same crop and blend the results.
- "Open in Studio" handoff from Simple Mode: load the exact auto-picked pipeline as a fully
  editable graph, not a re-guessed approximation of it.
- Preset save/load/import/export as versioned JSON (`docs/ARCHITECTURE.md` §7).

**Acceptance criteria:** a user can take any Simple Mode result, open it in Studio, see the
real pipeline that ran with real parameter values (not placeholders), change one parameter,
re-run just the affected downstream nodes, and save the result as a named preset they can
reuse on a different photo.

**Graphify checkpoint:** `/graphify . --update`; this phase adds a large, cohesive frontend
subsystem — check that it clusters as its own community rather than bleeding into unrelated
parts of the graph, which would suggest coupling that wasn't intended.

---

## Phase 4 — Full Model Stack Integration

**Goal:** ship the rest of `docs/MODEL_STACK.md`'s launch tiering.

Tasks, in the order `docs/MODEL_STACK.md`'s tiering recommends:
1. Remaining permissive-tier models: **HAT**, **PowerPaint**, **DiffBIR** (classified as a
   general/background node here, not a face node — see `docs/MODEL_STACK.md`'s Face
   Restoration Stack section for why).
2. License-gated opt-in models, each behind the acknowledgement flow from
   `docs/ARCHITECTURE.md` §6: **CodeFormer**, **GPEN**, **OSDFace** (resolve its license
   question directly with the upstream author before shipping it, per `docs/MODEL_STACK.md`),
   **SUPIR**, **FLUX Fill / tile**.
3. Stretch-tier models with no existing ComfyUI/reference node to build from — real
   engineering cost each, schedule independently rather than as one block: **MambaIRv2**,
   **DarkIR** (v1 only — "DarkIRv2" does not exist, see `docs/MODEL_STACK.md`), **InstantIR**,
   **DreamClear**, **UniRestore**, **RealRestorer** (treat as experimental/opt-in given its
   very small community and ~34GB VRAM footprint).

Explicitly out of scope for this phase: **BioIR** and **Restore-R1** have no public code as
of the Phase 0 research — don't build integration work against a repo that doesn't exist.
Re-check before starting this phase in case that's changed.

Each new node needs: a `RestorationNode` implementation, a weight manifest, a `param_schema`,
and a contract test — the same bar Phase 1's three seed nodes met, no exceptions for "it's
just one more model."

**Acceptance criteria:** category coverage and licensing match `docs/MODEL_STACK.md`'s launch
tiering table; on real test hardware across at least three VRAM classes (e.g. 6GB / 12GB /
24GB) plus CPU-only, the VRAM-tier gating in the Model Stack rail accurately reflects what
will and won't run — no silent OOM crashes on a model the UI presented as available.

**Graphify checkpoint:** mandatory, not optional — this phase is the largest single code
addition in the whole roadmap. Run `/graphify . --update` and actually read the report, not
just regenerate it.

---

## Phase 5 — Smart Orchestration v2 *(conditional — do not build speculatively)*

**Goal:** revisit the v1 heuristic degradation analyzer only if real usage justifies it.

The v1 heuristic router from Phase 2 may simply be good enough permanently — treat that as a
legitimate outcome, not a stopgap that must be replaced on principle. Before starting any work
here:
- Instrument how often Studio Mode users manually override the auto-picked pipeline, and on
  what kind of input — that correction signal is the actual training data a learned router
  would need, and its absence is a reason to not build one yet.
- Re-check `docs/MODEL_STACK.md`'s Workflow Orchestration section for whether Restore-R1,
  RAR, or RL-Restore have since published usable code — adopting real prior art beats
  building a router from scratch.

**Acceptance criteria:** either a shipped, measurably-better router with before/after
selection-accuracy numbers against the v1 heuristic, or an explicit written decision to leave
v1 as-is with the usage data that justified it — both are valid outcomes of this phase.

---

## Phase 6 — Customization & Extensibility Hardening

**Goal:** prove the plugin system works for someone who isn't you.

Tasks:
- Write the Plugin SDK doc (the `plugins/<name>/manifest.json` + module contract from
  `docs/ARCHITECTURE.md` §3, §7) as standalone reference documentation, plus one complete
  example third-party-style plugin that isn't one of the in-box models.
- Theming: ship the loadable theme-file mechanism from `docs/UI_DESIGN.md`, with the
  high-contrast variant from `docs/UI_DESIGN.md` §2 as proof it actually works for something
  other than a simple accent-color swap.
- CLI polish: `restore serve` (headless server mode), `restore plugin list`, batch/folder
  execution.
- Stabilize the REST/WebSocket contract (semver it) — third-party scripts and plugins are
  about to start depending on it.
- Command palette (`Cmd/Ctrl+K`) reaching every action across both modes; canvas undo/redo.

**Acceptance criteria:** a plugin author who has only read the Plugin SDK doc — not this
repo's source — can add a new restoration model and see it appear correctly tiered in the
Model Stack rail, with zero core-code changes.

---

## Phase 7 — Accessibility, i18n Scaffold & Polish

**Goal:** the accessibility bar from `docs/UI_DESIGN.md` §6 was a requirement from Phase 2
onward, not a checklist to backfill — this phase is verification and the parts that only make
sense once the whole product surface exists.

Tasks:
- Automated accessibility checks (e.g. axe-core) in CI across both modes.
- Manual screen-reader pass (NVDA/VoiceOver) and keyboard-only pass across both modes.
- Wire the message-catalog i18n seam that was reserved back in Phase 2 into actual use, even
  though only English ships at launch — retrofitting this later is far more expensive than
  finishing the seam now.
- Performance profiling: cold start time, hardware-detection speed, canvas render performance
  with 50+ nodes on screen.
- First-run onboarding: short, non-modal, doesn't block the first photo drop behind a forced
  tutorial.
- Privacy pass: confirm zero network calls beyond explicit model downloads and (opt-in only)
  crash reporting.

**Acceptance criteria:** automated a11y checks pass with zero critical violations; a full
manual screen-reader walkthrough of both Simple and Studio Mode completes without sighted
assistance.

---

## Phase 8 — Packaging & Distribution

**Goal:** the "double-click and it works" experience from Phase 2, finished properly.

Tasks:
- Finalize the Tauri v2 installer and the managed-Python-venv first-run flow from
  `docs/ARCHITECTURE.md` §8, with a real progress UI during first-run setup — not a frozen
  window.
- Per-OS builds (Windows/macOS/Linux) and an auto-update mechanism.
- Package `restore serve` as a headless/server-mode option (e.g. a Docker image) for users
  running on a remote GPU box rather than locally.
- Produce a license-compliance bundle: an aggregate NOTICE file listing every bundled and
  every downloadable model's license, matching `docs/MODEL_STACK.md`'s tiers exactly.
- Write the contribution guide for the plugin ecosystem opened up in Phase 6.

**Acceptance criteria:** a clean machine with no pre-existing Python or CUDA setup reaches a
working Simple Mode first-drop in a reasonable, clearly-communicated amount of time, on each
target OS — the user should never be staring at a frozen window wondering if it's broken.

---

## Phase 9 — Testing, QA & Launch Readiness

**Goal:** close the loop.

Tasks:
- Assemble a fixed test-image corpus spanning every degradation type the analyzer targets
  (blur, noise, low-res, JPEG artifacts, low-light, face-heavy, mixed/compound degradation).
- Run that corpus as a regression check on every release — a change that quietly makes
  results worse should be caught before a user notices, not after.
- Audit crash/OOM handling across the *entire* model stack from Phase 4, not just Phase 1's
  three seed nodes.
- Run a structured beta feedback loop before calling this done.
- Final full `/graphify .` pass (not incremental) and an actual read of `GRAPH_REPORT.md` as
  a literal launch-readiness gate: no unexplained god nodes, no unreviewed surprising
  connections.

---

## Definition of Done

The project is launch-ready when all of the following are true at once, not individually:

- A non-technical user can drag a real degraded photo onto the app and get a visibly better
  result with zero configuration (Phase 2's bar, still true after everything built on top of
  it in later phases).
- A power user can build, save, and share a fully custom multi-branch restoration pipeline
  without touching source code (Phase 3, Phase 6).
- A third party can add a new restoration model via the Plugin SDK alone (Phase 6).
- Every default-path model is permissively licensed; every non-permissive model is clearly
  labeled and opt-in (`docs/MODEL_STACK.md` licensing tiers, enforced throughout).
- The UI is recognizably built from `docs/UI_DESIGN.md`, not a generic component-kit
  reskin — this is a judgment call, but it's a real one: hold a finished screen next to the
  "explicitly avoid" list in `docs/UI_DESIGN.md` §1 and confirm none of it snuck back in.
- Automated and manual accessibility checks pass (Phase 7).
- Install-to-first-result works on a clean machine on every target OS (Phase 8).
- The graphify knowledge graph is current, and its own analysis (god nodes, surprising
  connections) doesn't surface an unresolved architectural surprise (Phase 9,
  `docs/GRAPHIFY_WORKFLOW.md`).

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Best-quality models (SUPIR, FLUX Fill, CodeFormer) are non-commercial-only | Never in the default path; opt-in with explicit acknowledgement (`docs/ARCHITECTURE.md` §6) |
| Several stretch-tier models have no existing ComfyUI/reference node | Scheduled as independent Phase 4 stretch items, not launch blockers |
| Small-community/experimental models (RealRestorer) are a maintenance/availability risk | Plugin architecture decouples the core app from any single model's survival — losing one node degrades, not breaks, the app |
| User hardware VRAM varies enormously | Hardware detection + VRAM tiering gates model availability visibly, never silently (`docs/ARCHITECTURE.md` §5) |
| Bundling PyTorch/CUDA in the installer is fragile across GPU driver versions | Managed first-run Python setup instead of a bundled binary blob (`docs/ARCHITECTURE.md` §8) |
| Docs and code drifting apart as the codebase grows | Mandatory phase-end graphify checkpoints surface drift early (`docs/GRAPHIFY_WORKFLOW.md`) |
