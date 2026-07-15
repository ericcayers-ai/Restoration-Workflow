# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/) once past 0.x (pre-1.0, minor bumps may
include breaking changes to the JSON pipeline shape).

## [0.6.0] - 2026-07-14

### Added
- **InstructIR Master Restorer** -- MIT instruction-guided node with prompt library
  (`instructir_prompts.json`, 24 presets), Inspector preset/custom UI, modes
  (`finish_only` / `instruct_only` / `guide_and_finish`), ensemble conductor
  (`POST /api/pipelines/ensemble`, CLI `--instructir-preset`), and swappable
  `InstructionRestorer` protocol for future Defusion/AutoDIR backends.
- **DDColor** colourization (Apache-2.0) with Auto routing on `is_grayscale` and
  Colorize B&W / Colorize Artistic presets.
- **Analyzer v2** -- multi-scale blur, anisotropy, continuous exposure / clip mask,
  chroma/grayscale, per-metric confidence; richer Simple Mode "why this stage".
- **Blown Highlight Rescue** preset + companion overlays (InstructIR -> DiffBIR ->
  SUPIR when installed) with soft clip-mask blend helper.
- **Download all** in Settings with permissive / restricted / grand totals and
  bulk licence acknowledgement.
- **Simple Mode quality tiers** -- draft / balanced / high mapped to the existing Phase 4.5.4 adaptive engine (tile size + upscale/face model swaps).
- **Equal lanes** -- Instruct category on the Model Stack; diffusion peers share
  prompt / negative / strength params; ~34 workflow presets spanning all lanes;
  Simple Mode preset picker; versioned builtin force-refresh.

### Fixed
- **A11y** — Master Restorer rail badge (MR) uses theme-aware fill/ink tokens so axe color-contrast passes on dark/light/high-contrast.

### Changed
- Licence gate copy: "Accept licence and allow download" with clear NC/Restricted
  explanation (no "download anyway").
- Classical exposure recovery dual-tone harden; DarkIR preferred for low-light when
  installed+acked (rule table stays all-permissive).
- DiffBIR elevated to generative peer category.

## [0.5.4] - 2026-07-14

### Added
- **Windows portable zip** -- Release builds ship `RestorationWorkflow-windows.zip` with
  double-click **`Run.bat`**, a short `README.txt`, and the PyInstaller onedir app.
  GitHub Releases now attach that zip as the downloadable asset.

## [0.5.3] - 2026-07-14

### Fixed
- **CI / Release (Windows)** -- install `[packaging]` (PyInstaller) and `[inference]` before the PyInstaller bundle step so `build-windows` no longer fails with `ModuleNotFoundError: No module named 'PyInstaller'`.

## [0.5.2] - 2026-07-14

### Fixed
- **CI / Release** -- lazy OpenCV and GPEN/torch imports so base and release jobs no longer fail at collection/import time; light-theme axe contrast fixes for accessibility CI.

## [0.5.1] — 2026-07-14

### Added
- **Puppeteer-based axe-core** (`@axe-core/puppeteer`) replacing flaky selenium CLI on Windows.
- **Experimental `src-tauri/` scaffold** -- Tauri v2 config and updater *plugin wiring*
  were sketched here; **they are not a shipping multi-OS auto-updater**. The supported
  desktop artefact remains the PyInstaller Windows zip (`Run.bat`). See `RELEASING.md`.

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
- **Experimental Tauri v2 scaffold** (`src-tauri/`) — not the supported desktop distribution;
  release workflow publishes the **PyInstaller Windows zip** (and runs macOS/Linux test builds).
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
  `docs/ARCHITECTURE.md` (Weight Manager / local binding).
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
- Studio pipeline builder: ordered stage list (reorder, Auto-order). React Flow was
  temporarily removed in this release and later returned as an optional graph editor.
- Simple Mode review step: the auto-picked pipeline is shown as an editable stage list
  (permissive models only) before the photo is processed, with an Auto-order action.
- Settings → Manage Downloads: every model in the stack, install state, and a
  download/remove control, in one place.
- Windows desktop build: `RestorationWorkflow.exe` (PyInstaller `--onedir`), a
  double-click launcher that starts the server and opens the browser once it's listening.
- `POST /api/pipelines/auto-order` endpoint exposing the ordering engine.

### Changed
- Bundle size dropped ~376KB → ~202KB with the node-graph canvas removed (later restored
  as an optional Studio graph mode in 0.4.0).

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
  `hardware` / `weights` / `presets` / `plugin` / `serve`), and an initial large pytest
  suite.
- Frontend: Simple Mode (drop a photo, zero configuration) and Studio Mode (pipeline
  authoring, model stack rail, parameter inspector, contact sheet, presets) built on Vite +
  React + TypeScript, themed to the "Safelight" darkroom identity in
  `docs/UI_DESIGN.md`.
- `docs/ARCHITECTURE.md`, `docs/UI_DESIGN.md`, `docs/MODEL_STACK.md` — the fact-checked
  model research and system design the build plan (`ROADMAP.md`) executes against.
