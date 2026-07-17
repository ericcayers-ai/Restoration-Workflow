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

## Phase 1 — Core Engine — *complete as of 0.3.0 / maintained through 0.6.0*

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

## Phase 2 — Simple Mode (instant automation, drag-and-drop MVP) — *complete; 0.6.0 polish*

**Goal:** the actual "drop a photo, get it fixed" deliverable. This is the phase most worth
getting exactly right — it's the app's first impression.

Tasks:
- Implement the **DegradationAnalyzer v1** exactly as specified in `docs/ARCHITECTURE.md` §4:
  heuristic (blur variance, noise estimate, face detection, JPEG blockiness, exposure
  histogram) → `DegradationProfile` → rule-table lookup → default node chain. Ship it as a
  real, inspectable heuristic — not a stub that fakes intelligence.
- Add the three Phase-2-tier face/matting nodes from `docs/MODEL_STACK.md`: **GFPGAN**,
  **RestoreFormer** (v1 — see the implementation note in `docs/MODEL_STACK.md` for why not
  ++), **BiRefNet** — ~~only **BiRefNet** remains~~ **done in 0.4.0**.
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

## Phase 3 — Studio Mode (full node canvas, full customizability) — *complete; 0.6.0 Studio UX harden*

**Goal:** every choice Simple Mode made, made visible and editable — plus real DAG authoring
power Simple Mode never needs.

Tasks:
- Integrate a node-canvas library and retheme it deeply per `docs/UI_DESIGN.md` §8 — no
  library default styling should be visible in the shipped UI.
- Build the four-region layout: Model Stack rail (searchable, category-grouped, VRAM-tier
  badged), Canvas, Inspector (auto-generated from each node's `param_schema`), and the
  Contact Sheet run-history strip.
- Implement branch/merge DAG editing — *done in 0.4.0* (graph editor + dual-face blend template).
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

## Phase 4 — Full Model Stack Integration — *complete as of 0.5.1*

**Goal:** ship the rest of `docs/MODEL_STACK.md`'s launch tiering.

**Status as of 2026-07-14:** Runnable inference paths for GPEN (vendored), MambaIRv2
(`[stretch]`), diffusion-tier nodes via `[diffusion]` + diffusers (tiled img2img,
PowerPaint BrushNet when weights are local), spandrel fallback for regression checkpoints,
and classical `old_photos_scratch`. Weight manifests pin real SHA-256 where upstream
publishes them without gating (GPEN, MambaIR, PowerPaint BrushNet). Gated Hugging Face
models use trust-on-first-use (TOFU) pinning after download with a valid `HF_TOKEN`:

| Node | SHA pin | Notes |
|------|---------|-------|
| GPEN, MambaIR, PowerPaint BrushNet | Pinned | Public mirrors |
| DiffBIR (`ai-forever/DiffBIR-v2`) | TOFU | Gated HF repo |
| SUPIR, FLUX Fill, InstantIR, RealRestorer | TOFU | Gated HF repos |
| OSDFace | TOFU | No single weight file on upstream HF card |
| DarkIR, UniRestore, DreamClear | TOFU | HF-hosted; filenames corrected in 0.5.1 |

Full upstream DiffBIR/SUPIR/FLUX quality still requires vendored architectures beyond
the diffusers fallback — tracked as stretch engineering, not launch blockers.


Tasks, in the order `docs/MODEL_STACK.md`'s tiering recommends:
1. Remaining permissive-tier models: **HAT** (blocked on weight sourcing — see above),
   **PowerPaint**, **DiffBIR** (classified as a
   general/background node here, not a face node — see `docs/MODEL_STACK.md`'s Face
   Restoration Stack section for why).
2. License-gated opt-in models, each behind the acknowledgement flow from
   `docs/ARCHITECTURE.md` §6: ~~**CodeFormer**~~ (shipped), **GPEN**, **OSDFace** (resolve
   its license question directly with the upstream author before shipping it, per
   `docs/MODEL_STACK.md`), **SUPIR**, **FLUX Fill / tile**.
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

## Phase 4.5 — Restoration Completeness, Presets, Adaptive Performance & Batch — *complete as of 0.5.x–0.6.0*

**Goal:** close the gap between "a good model stack" and "a tool that reliably gets *this
photo, right now* to its best possible restored version with no manual pipeline-building,"
across the specific degradation families real old photos and video captures actually arrive
in — plus the performance and workflow scaffolding (hardware-adaptive quality, batch,
portable data) that makes the tool usable at real scale rather than one photo at a time.

This phase was scoped in response to a real usage gap, not spec-written from nothing:
Simple Mode's rule table already routes competently on *measured* degradation (blur, noise,
JPEG blocking, faces) but has no concept of *source-format* degradation — a photo scanned
from a scratched film negative, a frame grabbed from a VHS capture, or a flat digitally-shot
photo all want materially different chains, and asking a first-time user to hand-build one
in Advanced Mode defeats Simple Mode's entire premise.

### 4.5.1 — Exposure recovery — *done (classical `exposure_correct`; DarkIR companion when installed)*

**Research finding (2026-07-12):** no learned exposure-correction model clears this repo's
bar for a *default/auto-download* node. Every serious candidate is either non-commercial
research code (`mahmoudnafifi/Exposure_Correction`, CVPR'21 — explicitly research-only) or,
like RetinexFormer (MIT-licensed, spandrel-native architecture — genuinely close), has no
GitHub-release weight source, only Google Drive/Baidu — the exact disqualifying pattern
already established for HAT in `docs/MODEL_STACK.md`. Applying that same bar here rather
than relaxing it for convenience is the point of having the bar.

**Decision:** ship a classical (non-learned) exposure-recovery node — adaptive local tone
mapping (CLAHE on a perceptual lightness channel, plus a highlight-compression and
shadow-lift pass) via `opencv-python-headless`, which the `[inference]` extra already
depends on. This is real, well-established computational photography (the same family of
technique real photo-editing tools use for shadow/highlight recovery), it needs no weight
download, and — importantly — it should be *described honestly* in its UI copy as
recovering compressed dynamic range, not as AI-generated detail hallucination, which is a
different (and not yet available) claim. Revisit RetinexFormer if an official direct-download
mirror of its weights appears.

**Task:** analyzer already computes `low_light` / `blown_highlights` (Phase 2) but nothing
routes on them — wire an `exposure_correct` node into the rule table gated on those flags,
ordered before denoise/upscale (correcting exposure first avoids amplifying compressed
noise in the process).

### 4.5.2 — Scratch and dust detection — *classical path done; Microsoft Bringing-Old-Photos still deferred*

**Research finding (2026-07-12):** the strongest learned candidate is Microsoft's
`Bringing-Old-Photos-Back-to-Life` (CVPR'20, MIT, real GitHub-release weights
— `global_checkpoints.zip` / `face_checkpoints.zip`, still meets every sourcing bar this
project holds). It is **not** shipped in this pass: it's a bespoke triplet-domain-translation
architecture with no spandrel support, meaning integration means vendoring its actual
`nn.Module` definitions (not just a weight manifest) and independently auditing checkpoint
safety without spandrel's architecture-detection layer doing that work — real, multi-day
engineering, not a config change. **This is the single highest-value tracked follow-up in
this document; do it properly rather than rushing it into this pass.**

**Shipped instead:** classical defect detection — morphological top-hat/black-hat filtering
for thin line-like scratches, isolated high-contrast speckle detection for dust — added as
analyzer metrics, with a `defect_mask` node (no weights, same family as `mask_from_image`)
that auto-routes into LaMa when defects are detected, with no manual mask-drawing required.
Genuinely useful and honestly scoped as "classical CV," not oversold as the Microsoft model's
learned quality bar.

### 4.5.3 — Workflow presets — *done in 0.4.0; expanded to ~34 lanes in 0.6.0*

Eight presets built from the *base* permissive stack (no extra downloads beyond what Simple
Mode already fetches), covering the degradation *families* the rule table's per-image
heuristics don't fully capture on their own (a VHS capture and a scanned film negative can
have similar blur/noise numbers and still want different chains):

Animation/Cartoon · VHS Capture · 35mm Film Scan · Digital Photo · Old Film (pre-video-era
motion picture) · B&W Film · Damaged Print (scratches/dust-heavy) · Robust All-in-One.

Eight more presets reuse the same categories at maximum quality once the relevant extra
models are installed (CodeFormer instead of GFPGAN/RestoreFormer for faces, SwinIR-L over
RealESRGAN for upscale, defect removal always on) — "full-stack" is a quality tier of the
same eight categories, not eight unrelated new categories.

Each preset is a real, validated `PipelineJson` (the exact shape `PresetStore` already
persists) with its own independent node ordering and params — not the same chain with a
different name.

### 4.5.4 — Hardware-adaptive quality tiers — *done (API/CLI + Simple Mode draft/balanced/high)*

A draft → balanced → high-quality axis, mapped to tile size (smaller tiles / more OOM
headroom in draft, larger contiguous inference in high) and model choice within a category
(RealESRGAN in draft/balanced, SwinIR in high, for example) — computed from
`HardwareDetector`'s existing VRAM read, not a fixed table blind to the machine it's running
on. Every tier must complete without OOM on the smallest VRAM class this repo already tests
against (`docs/ARCHITECTURE.md` §5's tiers) — an OOM on a tier the UI presented as safe is a
correctness bug, not a performance nitpick.

### 4.5.5 — Batch processing — *done in 0.4.0* (CLI + Simple Mode folder drop) and *0.5.0* (Studio folder batch)

Simple Mode: drop a folder, each image gets its own independent auto-analysis and pipeline —
this is not one pipeline "reused," it's Simple Mode's existing per-image logic run N times.
Advanced Mode: one authored (or preset) pipeline applied identically across every image in a
folder — the point being reproducibility across a batch, not per-image adaptation.

### 4.5.6 — Portable data directory — *done in 0.3.0*

When running as the packaged desktop build (`sys.frozen`), default the data directory
(weights, presets, downloads cache) to a folder next to the executable rather than
`%LOCALAPPDATA%` — "the app is the folder you extracted" is the portable-app convention
users of this class of tool (ComfyUI portable, etc.) already expect, and it's what makes
"back up/move the whole app" actually mean what it sounds like. `RESTORE_HOME` continues to
override for anyone who wants the old behavior.

### 4.5.7 — Result presentation — *done in 0.4.0*

The result view: fade from the "before" image to the restored result once the job
completes — matching the darkroom metaphor already established (`stageMessageKey`'s
Developing → Fixing → Washing → Done sequence, `docs/UI_DESIGN.md`), a photo "developing"
into its final state rather than a hard cut. An expandable/retractable log panel below the
preview surfaces per-stage timing and metrics live as a job runs (not only after). Cancel
must be immediately responsive — a queued cancel that appears to hang undermines trust in
every future cancel click — and a cancelled run can be resumed/restarted, not just discarded.
"Try again" (back to the reviewable pipeline, same photo) and "New photo" (full reset) are
two distinct actions, not one overloaded button. The before/after view supports zoom and pan
in addition to the existing slider/side-by-side/difference modes.

**Acceptance criteria:** builtin presets (~34 as of 0.6.0, including the original 16-family set) are real, independently-authored, validated
pipelines a user can pick and run with no further configuration; a folder of 10 mixed-format
images processes correctly in both Simple (per-image) and Advanced (identical-pipeline)
batch modes; the smallest tested VRAM class never OOMs at any quality tier; cancel-to-stopped
latency is sub-second in manual testing.

---

## Phase 5 — Smart Orchestration v2 — *decision documented in 0.4.0* (`docs/PHASE5_DECISION.md`: keep v1 router)

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

## Phase 6 — Customization & Extensibility Hardening — *done in 0.5.0*

**Goal:** prove the plugin system works for someone who isn't you.

Tasks:
- Write the Plugin SDK doc — *done in 0.4.0*
- Theming: loadable theme files from `frontend/public/themes/` with high-contrast built-in — *done in 0.5.0*
- CLI polish — *done in 0.4.0*
- Stabilize REST/WebSocket contract at API **1.0.0** — *done in 0.5.0*
- Command palette — *done in 0.4.0*; canvas undo/redo (Ctrl/Cmd+Z) — *done in 0.5.0*

**Acceptance criteria:** a plugin author who has only read the Plugin SDK doc — not this
repo's source — can add a new restoration model and see it appear correctly tiered in the
Model Stack rail, with zero core-code changes.

---

## Phase 7 — Accessibility, i18n Scaffold & Polish — *expanded in 0.6.0 QOL; NVDA/VoiceOver still deferred*

**Goal:** the accessibility bar from `docs/UI_DESIGN.md` §6 was a requirement from Phase 2
onward, not a checklist to backfill — this phase is verification and the parts that only make
sense once the whole product surface exists.

Tasks:
- Automated accessibility checks (axe-core via `@axe-core/puppeteer`) in CI — *done in 0.5.1*
- Manual screen-reader pass documented in `docs/ACCESSIBILITY.md` — *checklist in 0.5.0; NVDA/VoiceOver pass deferred to release QA*
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

## Phase 8 — Packaging & Distribution — *Win/macOS/Linux installers + Docker; Tauri updater de-scoped*

**Goal:** the "double-click and it works" experience from Phase 2, finished properly.

Tasks:
- **Supported:** PyInstaller onedir wrapped as Windows Inno Setup, macOS DMG, and Linux
  AppImage on GitHub Releases — *0.6.1*; keep packing `LICENSE` / notices with each artefact.
- Per-OS CI in `.github/workflows/release.yml` — all three OSes publish installers; Linux
  also builds Docker — *0.6.1*.
- Package `restore serve` as a headless/server-mode option (Docker image) for remote GPU boxes.
- Licence-compliance bundle: `NOTICE` + `THIRD_PARTY_NOTICES.md` for bundled code/fonts;
  downloadable-weight tiers stay in `docs/MODEL_STACK.md`.
- Contribution / community docs: CONTRIBUTING, SUPPORT, RELEASING, CoC — *see repo root*.
- **De-scoped:** shipping a Tauri multi-OS auto-updater. `src-tauri/` may remain as an
  experiment; do not wire release marketing or CI around `latest.json` updater artefacts
  until that path is deliberately rebuilt and verified.

**Acceptance criteria:** a clean machine with no pre-existing Python reaches a working
Simple Mode first-drop from a desktop installer in a reasonable, clearly-communicated
amount of time — the user should never be staring at a frozen window wondering if it's
broken.

---

## Phase 9 — Testing, QA & Launch Readiness — *corpus/docs in 0.5.0; regression + a11y expanded in 0.6.0*

**Goal:** close the loop.

Tasks:
- Fixed test-image corpus in `backend/tests/corpus/` with regression tests — *done in 0.5.0*
- Beta loop / graphify gate documented in `docs/QA_LAUNCH.md` — *done in 0.5.0*
- Audit crash/OOM handling across the *entire* model stack from Phase 4, not just Phase 1's
  three seed nodes.
- Run a structured beta feedback loop before calling this done.
- Final full `/graphify .` pass (not incremental) and an actual read of `GRAPH_REPORT.md` as
  a literal launch-readiness gate: no unexplained god nodes, no unreviewed surprising
  connections.

---

---

## Phase 10 — v0.6.0 QOL Overhaul & Master Restorer — *complete as of 0.6.0*

**Goal:** harden the already-shipped Phase 1–9 stack into a coherent 0.6 product without replacing
the FastAPI / React / CLI / PyInstaller architecture, and record truthful status for what remains.

### Shipped in this wrap-up

- **Master Restorer (InstructIR)** — MIT instruction-guided node, prompt library, finish / instruct /
  guide modes, guided-ensemble conductor (`POST /api/pipelines/ensemble`, CLI preset), soft clip-mask
  highlight blend; `InstructionRestorer` protocol left open for future backends.
- **DDColor** colourization with Auto routing on grayscale; Colorize presets.
- **Analyzer v2** — multi-scale blur, anisotropy, continuous exposure / clip mask, chroma, confidence;
  Blown Highlight Rescue companions (InstructIR → DiffBIR → SUPIR when ready).
- **Weights & jobs hygiene** — parameter/variant-aware readiness and download totals; download cancel +
  partial cleanup; bounded job retention / result TTL; licence gates that Simple presets cannot bypass.
- **Studio / Simple workflows** — canonical pipeline state across list + graph; batch completion /
  preflight; Light Table compare/export reuse; searchable Downloads inventory; Master Restorer UX copy.
- **Safelight UI / a11y / i18n** — responsive Studio easels, focus traps, keyboard parity, token hygiene,
  expanded axe coverage; English catalog remains the i18n seam.
- **Quality tiers in Simple Mode** — draft / balanced / high surface the existing Phase 4.5.4 engine.
- **Packaging & docs** — Windows zip packs LICENSE / notices; Docker installs advertised inference extra;
  community set refreshed (README, CoC, CONTRIBUTING, SUPPORT, RELEASING, issue/PR templates,
  THIRD_PARTY_NOTICES). `src-tauri/` stays an **experiment**, not a shipping updater.

### Explicitly still open (honest remaining items)

| Item | Status |
|---|---|
| Microsoft **Bringing-Old-Photos** learned scratch restore | Deferred — classical `old_photos_scratch` / defect→LaMa ships instead |
| Full vendor DiffBIR / SUPIR / FLUX architectures beyond diffusers fallback | Stretch engineering, not a 0.6 launch blocker |
| Defusion / AutoDIR / PromptIR as Master Restorer backends | Watch list; protocol ready, packaging/licence bar not met |
| Restore-R1 / learned Phase 5 router | No usable public code; keep v1 analyzer (`docs/PHASE5_DECISION.md`) |
| NVDA / VoiceOver manual screen-reader certification | Checklist exists; live pass remains release-QA |
| Native macOS/Linux desktop installers + Tauri auto-updater | De-scoped; use source, `restore serve`, or Docker |
| Structured external beta loop / full VRAM-matrix certification | Process in `docs/QA_LAUNCH.md`; not claimed finished by 0.6 alone |

**Acceptance for 0.6.0:** CI green on ruff/pytest (non-inference + inference where installed), frontend
test/typecheck/build/a11y; Windows zip path remains the documented double-click install; roadmap claims
above match the code rather than aspirational scaffolding.

**Graphify checkpoint:** `/graphify . --update` after this wrap if regenerating the knowledge graph for
launch gating (Phase 9); not a substitute for the verification commands above.

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
- Install-to-first-result works on a clean machine from a desktop installer (Phase 8:
  Windows Setup / macOS DMG / Linux AppImage); source/`restore serve` / Docker remain
  supported contributor and server paths.
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
