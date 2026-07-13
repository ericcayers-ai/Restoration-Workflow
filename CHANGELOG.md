# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/) once past 0.x (pre-1.0, minor bumps may
include breaking changes to the JSON pipeline shape).

## [0.5.1] — 2026-07-14

### Added
- **Tauri updater signing key** — real minisign pubkey in `src-tauri/tauri.conf.json`; private key
  gitignored (`src-tauri/updater.key`, set `TAURI_SIGNING_PRIVATE_KEY` in release CI).
- **Puppeteer-based axe-core** (`@axe-core/puppeteer`) replacing flaky selenium CLI on Windows.

### Changed
- **Diffusion runtime** — tiled img2img for large restores, PowerPaint BrushNet path when weights
  are present, clearer gated-model errors referencing `HF_TOKEN`.
- **Weight manifests** — DiffBIR/DreamClear/DarkIR/UniRestore corrected to real Hugging Face
  filenames; TOFU SHA pinning retained where upstream is gated (see ROADMAP.md).
- **Drop zone a11y** — `<label>` pattern fixes `nested-interactive` axe violation.

### Notes
- Microsoft **Bringing-Old-Photos** remains deferred (vendored triplet architecture); classical
  `old_photos_scratch` ships instead.

## [0.5.0] — 2026-07-13

### Added
- **Phase 4 full inference** — GPEN (vendored architecture), MambaIRv2 (`[stretch]` extra),
  diffusion-tier nodes via `[diffusion]` + diffusers, spandrel checkpoint fallback for
  regression models, and `old_photos_scratch` classical scratch restoration.
- **Real SHA-256 pins** for GPEN, MambaIR, and PowerPaint BrushNet weights; TOFU pinning for
  gated Hugging Face models.
- **Studio Mode folder batch** — apply one authored pipeline across every image in a folder.
- **Loadable theme files** (`frontend/public/themes/`) plus built-in high-contrast theme.
- **Canvas undo/redo** (Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z) in Studio Mode.
- **API contract 1.0.0** — semver-stabilized REST/WebSocket surface.
- **axe-core** in CI (`npm run a11y`); `docs/ACCESSIBILITY.md` manual pass checklist.
- **Tauri v2 scaffold** (`src-tauri/`) with updater plugin config; release workflow for
  Windows/macOS/Linux.
- **Regression corpus** (`backend/tests/corpus/`) and `docs/QA_LAUNCH.md` beta/graphify gate.

### Changed
- Optional extras: `[diffusion]` (diffusers) and `[stretch]` (mamba-ssm, einops).
- MambaIR weight file corrected to `mambairv2_classicSR_Small_x4.pth` (official release).

## [0.4.0] — 2026-07-13

### Added
- **BiRefNet** matting node (MIT, Hugging Face weights via `transformers`).
- **HAT** super-resolution (Apache-2.0, Acly/hat mirror on Hugging Face).
- **Phase 4 model stack** — integration scaffolds with weight manifests and licence
  gates for GPEN, OSDFace, PowerPaint, DiffBIR, SUPIR, FLUX Fill, and stretch-tier
  nodes (MambaIRv2, DarkIR, InstantIR, DreamClear, UniRestore, RealRestorer).
- **Sixteen built-in workflow presets** (eight base + eight full-stack variants) seeded
  on first run.
- **DAG graph editor** in Studio Mode — branch/merge pipelines including a dual-face
  blend template; list editor retained for linear chains.
- **Simple Mode batch** — drop a folder for per-image auto-analysis and restoration.
- **Result presentation** — fade reveal on completion, zoom/pan on the light table,
  expandable per-stage log during processing, separate Try again / New photo actions.
- **Plugin SDK** (`docs/PLUGIN_SDK.md`) and `plugins/example/` invert demo.
- **Phase 5 decision** documented in `docs/PHASE5_DECISION.md` (keep v1 heuristic router).
- Router override telemetry (`core/router_telemetry.py`).
- Docker headless image (`Dockerfile`), `NOTICE` license bundle.

### Changed
- Studio Mode toggles between ordered list and graph editor.
- `transformers` added to the `[inference]` optional dependency for BiRefNet.

### Notes
- Diffusion and stretch-tier nodes ship with manifests and UI integration; full upstream
  inference for several models remains tracked work where vendoring is required — see
  ROADMAP.md Phase 4 for per-model status.

## [0.3.0] — 2026-07-13

### Added
- **CodeFormer** — the first license-gated node, behind the acknowledgement flow from
  `docs/ARCHITECTURE.md` §6.
- **Exposure recovery** (`exposure_correct`) — classical auto-gamma + CLAHE, no weights;
  the rule table routes on `low_light` / `blown_highlights` before denoise/upscale.
- **Scratch/dust detection** — classical defect scoring in the degradation analyzer, a
  `defect` mask source on `mask_from_image`, and automatic mask→LaMa routing when defects
  are detected.
- **Hardware-adaptive quality tiers** (draft / balanced / high) — tile size and model
  choice within a category adapt to detected VRAM.
- **Portable data directory** — packaged builds default weights/presets next to the exe;
  `RESTORE_HOME` still overrides.
- Repo health: Apache-2.0 `LICENSE`, GitHub Actions CI, community files, and a real
  `README.md`.

### Changed
- Simple Mode's auto-pipeline spec now uses `auto_order_pipeline()` so mask→LaMa edges
  wire correctly when the rule table appends both nodes.

### Fixed
- CI: missing `ruff` dev dependency and OpenCV 5.x API breakage in exposure recovery.

## [0.2.0] — 2026-07-12

### Added
- **SCUNet** and **SwinIR** nodes (Apache-2.0, author-hosted weights, sha256-pinned) —
  blind real-world denoising, transformer super-resolution, transformer denoise, and
  transformer JPEG-artifact removal. The default auto-pipeline now chains up to five
  models: FBCNN → SCUNet → SwinIR/RealESRGAN → GFPGAN → RestoreFormer.
- Auto-order engine (`core/ordering.py`): every node carries a canonical
  restoration-stage rank; `auto_order_pipeline()` arranges any set of chosen models into
  a correctly-wired pipeline, including auto-inserting a mask source for LaMa.
- Generic model wrapper (`nodes/wrappers.py`, `spandrel_image_node()`): wrapping a new
  spandrel-supported architecture is one function call.
- Workflows save/load as commented `.txt` files (`core/workflow_text.py`,
  `POST /api/workflows/{export,import}`).
- Advanced pipeline builder: replaces the React Flow node-graph canvas with an ordered
  stage list — reorder with two buttons, "Auto-order" calls the engine above. Removed
  `@xyflow/react` and everything that existed only to serve it.
- Simple Mode review step: the auto-picked pipeline is shown as an editable stage list
  (permissive models only) before the photo is processed, with an Auto-order action.
- Settings → Manage Downloads: every model in the stack, install state, and a
  download/remove control, in one place.
- Windows desktop build: `RestorationWorkflow.exe` (PyInstaller `--onedir`), a
  double-click launcher that starts the server and opens the browser once it's listening.
- `POST /api/pipelines/auto-order` endpoint exposing the ordering engine.

### Changed
- Bundle size dropped ~376KB → ~202KB with the node-graph canvas removed.

## [0.1.0] — 2026-07-11

### Added
- Core engine: DAG pipeline executor, node registry + third-party plugin discovery,
  weight manager (checksum-pinned downloads, license acknowledgement gate), hardware
  detection, and a heuristic degradation analyzer driving a data-file rule table for
  Simple Mode's automatic pipeline selection.
- Seven in-box nodes, all permissively licensed: RealESRGAN, FBCNN, GFPGAN,
  RestoreFormer, LaMa, plus the weightless `mask_from_image` and `blend` orchestration
  nodes.
- FastAPI REST + per-job WebSocket API, the `restore` CLI (`run` / `analyze` / `nodes` /
  `hardware` / `weights` / `presets` / `plugin` / `serve`), and 229 tests.
- Frontend: Simple Mode (drop a photo, zero configuration) and Studio Mode (a node-graph
  canvas, model stack rail, parameter inspector, contact sheet, presets) built on Vite +
  React + TypeScript, themed to the "Safelight" darkroom identity in
  `docs/UI_DESIGN.md`.
- `docs/ARCHITECTURE.md`, `docs/UI_DESIGN.md`, `docs/MODEL_STACK.md` — the fact-checked
  model research and system design the build plan (`ROADMAP.md`) executes against.
