# System Architecture

Local-first desktop app. All inference runs on the user's own hardware; nothing is uploaded
anywhere by default. This document specifies the backend, frontend, execution engine, and
packaging decisions an implementer should follow. The choices below were checked against
real prior art (ComfyUI, InvokeAI, Fooocus, ComfyUI Desktop, Jan.ai) as of 2026-07-09 —
version numbers should be re-verified at implementation time, but the design decisions
themselves are settled, not placeholders.

**Why not just build on top of ComfyUI as a headless backend?** It's a real, seriously
considered option — ComfyUI is documented as runnable headlessly via a REST+WebSocket API
(`POST /prompt`, `GET /history`, `WS /ws`), and products like ComfyDeploy and RunComfy already
drive it that way. Two things rule it out here: it's **GPL-3.0 licensed**, which is a real
entanglement risk for an app whose own orchestration layer is meant to ship Apache-2.0; and
its "API format" workflow JSON is version-fragile across custom-node updates the app wouldn't
control. Instead, this architecture deliberately **clones ComfyUI's execution-engine design**
(topological-sort DAG, per-node output caching, WebSocket progress events — all genuinely
good ideas, proven at scale) without inheriting its license or its general-purpose UI, which
would fight against a curated "just fix this photo" Simple Mode anyway.

```mermaid
flowchart LR
    subgraph Desktop["Desktop / browser shell"]
        UI[React + TypeScript UI]
    end
    UI <-->|REST + WebSocket, localhost only| API[FastAPI Backend]
    API --> Analyzer[Degradation Analyzer]
    API --> Executor[Pipeline Executor / DAG Engine]
    Executor --> Nodes[RestorationNode plugins]
    Nodes --> Weights[Weight Manager]
    Weights -->|first-use download| HF[(HuggingFace Hub / model sources)]
    API --> HW[Hardware Detector]
    Executor --> GPU[(Local GPU / CPU)]
```

**As shipped (0.6.1+):** supported desktop artefacts are **PyInstaller onedir** wraps —
Windows Inno Setup installer, macOS DMG (unsigned `.app`), and Linux AppImage — each
launching the local FastAPI process and opening a browser. `restore serve` is the same
stack without the wrapper. An experimental `src-tauri/` tree may exist; it is **not** a
shipping multi-OS updater shell — see [`RELEASING.md`](../RELEASING.md).

---

## 1. Process model

Three logical pieces:

1. **Desktop / browser shell (as shipped: installer + browser)** —
   Windows Setup / macOS `.app` / Linux AppImage start the backend and open a
   browser tab. There is no required native WebView shell for day-one use. An optional
   Tauri scaffold under `src-tauri/` is experimental only — not a product updater path.
2. **Backend (Python / FastAPI)** — bound to `127.0.0.1` only (fixed default port `8765` in
   current builds, overridable). Owns the pipeline executor, model plugins, weight manager,
   hardware detection, and job state.
3. **Frontend (React + TypeScript, served by the backend or by Vite in dev)** — talks to the
   backend only over `localhost`. The same frontend build works as a plain browser tab in
   **server mode** (see §7). Studio Mode supports an ordered list editor and a DAG graph
   editor for branch/merge pipelines.

This split means "the app" and "the engine" are independently testable: the backend has a
full REST/WebSocket API that works with `curl`/Postman/a Python script with zero UI running,
which matters for the CLI/automation surface in §6 and for testing (§9).

---

## 2. Backend: FastAPI + async job engine

- **No Celery/Redis.** This is a single-user local app; an in-process `asyncio` queue plus a
  GPU-lock `asyncio.Semaphore(1)` (raised only if the hardware detector finds multiple usable
  GPUs and the user opts in) is sufficient and avoids an unnecessary infra dependency the user
  would have to install.
- **WebSocket per job** streams structured progress events: `{node_id, status: queued |
  loading_weights | running | done | error, progress: 0.0-1.0, preview_url?, message}`. The
  frontend's status line (Simple Mode) and per-node progress fill (Studio Mode) both consume
  this same event stream — one source of truth for progress, not two.
- **REST endpoints** cover: list available nodes (with VRAM tier + license + install state),
  submit a pipeline (DAG JSON) for execution, get/cancel job status, list/download/remove
  model weights, list/save/load presets, hardware info.

---

## 3. The `RestorationNode` plugin interface

Every model — whether shipped in the box or added later by a user — implements the same
interface. This is the single most important abstraction in the app: it's what makes the
system "customizable" rather than a hardcoded pipeline, and it's what makes Phase 4's model
integrations additive instead of bespoke each time.

```python
class RestorationNode(Protocol):
    id: str                      # stable, unique — used in saved pipeline JSON
    category: NodeCategory       # generative | face | regression | masking | orchestration
    display_name: str
    license: LicenseInfo         # spdx_id | "non-commercial" | "custom", + source URL
    vram_tier: VramTier          # LOW (<6GB) | MID (6-12GB) | HIGH (12-24GB) | VERY_HIGH (24GB+)
    param_schema: JSONSchema     # drives the auto-generated Inspector form
    weight_manifest: list[WeightFile]  # files + source URLs + checksums, for the Weight Manager

    def supports(self, image: ImageMeta) -> bool: ...
    async def run(self, image: Tensor, params: dict, ctx: RunContext) -> Tensor: ...
```

`RunContext` gives a node a way to emit intermediate preview frames and progress fractions
back through the WebSocket stream without knowing anything about HTTP or the UI.

Plugins are discovered from a `plugins/` directory at startup (manifest.json + Python module,
no core-code edits required) in addition to the nodes shipped in the box — see
`GRAPHIFY_WORKFLOW.md` for how the plugin registry gets indexed as it grows, and
`MODEL_STACK.md` §"Licensing tiers" for why `license` is a required, surfaced field rather
than a footnote: several models in this project's own stack are non-commercial-only, and the
UI must show that *before* a user downloads multi-gigabyte weights, not after.

---

## 4. Pipeline executor & degradation analyzer

The executor is a **DAG**, not a linear chain — the README's own example
(`DarkIRv2 → BiRefNet → OSDFace → SUPIR`) is a chain, but Studio Mode's "run two face models
on the same crop and blend" use case (`UI_DESIGN.md` §8) requires branch/merge, so the
executor is built as a general topological-sort DAG runner from day one rather than special-
cased later.

Execution rules:
- Nodes run in topological order; independent branches may run concurrently for CPU-bound
  pre/post steps, but GPU-bound node execution is serialized by the GPU semaphore (§2) unless
  multi-GPU is detected and enabled.
- A node is unloaded from VRAM immediately after it completes unless the user pins it
  ("keep loaded" toggle in Studio Mode) — default behavior favors running on lower-VRAM
  hardware over raw speed on repeated runs.
- **Per-node output caching:** each node's output is cached keyed by `(node_id, params_hash,
  upstream_output_hash)`, following ComfyUI's `execution.py` precedent. Changing one
  parameter on one node in Studio Mode re-runs only that node and whatever's downstream of
  it — this is what makes Phase 3's "tweak one parameter, re-run just the affected nodes"
  acceptance criterion actually true rather than aspirational.
- **OOM handling:** a `CUDA out of memory` from a node is caught, the node reports `error`
  with a specific message, and the executor offers a concrete fallback (tile-based
  processing if the node supports it, or "try the LOW/MID tier alternative for this
  category") rather than crashing the run or the app.

**Degradation analyzer** (the in-house answer to the README's "Restore-R1" auto-agent —
see `MODEL_STACK.md` for why this is built in-house rather than adopted from an external
project): a fast, cheap classification pass run before any heavy model loads.

v1 is deliberately simple and heuristic, not learned, so it ships in Phase 1 without a
training pipeline:
- Blur estimate: variance of Laplacian.
- Noise estimate: high-frequency residual after a light denoise pass.
- Face presence + count: a lightweight face detector (not a restoration model — just
  detection, e.g. a small ONNX face detector).
- Resolution / JPEG blockiness: DCT block-edge energy.
- Exposure: histogram skew (low-light / blown-highlight detection).

Output is a structured `DegradationProfile`, matched against a hand-authored rule table
(`profile → default node chain`) to pick Simple Mode's auto-pipeline. The rule table is a
plain data file (not hardcoded logic), so Phase 5 can evolve it — e.g. replacing rule lookup
with a learned router — without touching the executor. This keeps the "instant automation"
promise honest: it's a real, inspectable heuristic from day one, not a stub that fakes
intelligence, and it has a clear upgrade path instead of a rewrite.

---

## 5. Hardware detection & VRAM tiering

At startup, probe `torch.cuda` for device count, name, and total VRAM (and check for Apple
Silicon MPS / CPU-only as fallback paths). Every `RestorationNode.vram_tier` is compared
against the detected hardware to decide the node's UI state:

| Detected VRAM | Available tiers | UI treatment of higher tiers |
|---|---|---|
| CPU only | LOW only (regression models: RealESRGAN, FBCNN-class) | Greyed with tooltip explaining why, not hidden |
| < 8GB | LOW, some MID (with tiling) | Greyed + "requires tiling, will be slow" note |
| 8–16GB | LOW, MID, some HIGH (quantized) | HIGH shown with a "quantized" badge |
| 16GB+ | All tiers | — |

Never silently fail a run because of VRAM — gate at selection time with a clear reason, so a
user on a laptop GPU never drops a job halfway through Phase 4's heavier diffusion models.

---

## 6. Weight management

Wraps `huggingface_hub` (resumable downloads, works for the majority of this stack) plus a
generic URL+checksum path for anything not on the Hub. Before any download:

1. Show the model's `license` field from the plugin manifest and require explicit
   acknowledgement for anything not permissively licensed (Apache/MIT/BSD) — this directly
   answers the licensing risk `MODEL_STACK.md` surfaces (several stack members are
   non-commercial or unclear-license). There's no off-the-shelf API for this (Hugging Face's
   own gated-repo consent flow isn't replicable in a third-party app); the closest real
   precedent is InvokeAI's starter-model importer, which requires an explicit "commercial
   license attestation" click before downloading a restricted checkpoint — follow that
   pattern rather than inventing one from scratch.
2. Pre-check free disk space against the manifest's declared size; refuse to start a download
   that won't fit rather than filling the disk mid-transfer. `huggingface_hub`'s own
   disk-space check is advisory-only (it warns, it doesn't block), so this hard gate has to
   be the app's own logic, not something inherited for free from the download library.
3. Verify checksums post-download; a corrupt/partial weight file must never silently load.
   Every in-box model pins a SHA-256 in its manifest. Trust-on-first-use pinning exists for
   third-party plugins whose upstream publishes no checksum — it defers verification, it never
   skips it.
4. **Load weights without executing them.** A `.pth`/`.ckpt` file is a pickle, and unpickling
   is arbitrary code execution — a checksum proves a file is the one we expected, not that the
   file is safe. Checkpoints are therefore read with `torch.load(..., weights_only=True)`, or
   directly when they are `safetensors`, and handed to `spandrel` as a plain state dict;
   `spandrel.ModelLoader.load_from_file`, which permits arbitrary pickle globals, is never
   called. The two gates are complementary: the checksum stops a *substituted* file, safe
   deserialization stops a *malicious* one, and neither is sufficient alone. A checkpoint that
   cannot be loaded this way is not shipped — see `MODEL_STACK.md`'s LaMa note for a model this
   rule actually changed.

Model architectures come from `spandrel`'s main registry, which is MIT-licensed and
deliberately excludes the non-commercial architectures (CodeFormer, MAT, …) that upstream
ships separately in `spandrel_extra_arches`. Depending only on the main package is a licensing
guardrail that holds even if someone forgets to check a manifest.

Cache directory is user-configurable (defaults to a per-OS app-data location), and weights
can be listed/removed from Studio Mode settings — a user should be able to reclaim tens of
gigabytes without hunting through the filesystem manually.

---

## 7. Extensibility & scripting surface

- **Plugin SDK**: a `plugins/<name>/manifest.json` + Python module is the entire contract for
  adding a new restoration model — no core-repo PR required. This is the primary mechanism
  behind "customizable for the end user," not a settings panel with a fixed list of toggles.
- **Presets**: pipeline DAGs save/load as versioned JSON, shareable as files.
- **CLI**: `restore run --input <folder> --preset <name> --output <folder>` drives the same
  backend API a script or cron job could hit directly — batch/automation is a first-class
  path, not an afterthought bolted onto the GUI.
- **Server mode**: running `restore serve` starts the FastAPI backend (no native desktop
  shell) and serves the built frontend — the identical UI works headless on a Linux box or a
  remote GPU machine reached over SSH port-forward. One codebase, two deployment shapes
  (portable Windows zip vs. source/Docker server).
- **Theming**: the CSS custom-property tokens in `UI_DESIGN.md` §9 are loaded from a
  user-overridable theme file, not compiled into the bundle — an accent-color swap or a
  custom high-contrast variant doesn't require a fork.

---

## 8. Desktop packaging

**Supported path (0.6.1+):** PyInstaller `--onedir` bundles wrapped as platform
installers by `.github/workflows/release.yml`:

- Windows: Inno Setup (`RestorationWorkflow-Setup-*-windows-x64.exe`) via
  `backend/packaging/build_exe.py`
- macOS: unsigned `.app` in a DMG via `backend/packaging/make_macos_dmg.py`
- Linux: AppImage via `backend/packaging/make_linux_appimage.py`

Each starts a local server + browser UI. CPU wheels are enough to start; CUDA
accelerates when present. Model **weights are not** in the installer — they download
on demand through the Weight Manager. Builds are not code-signed.

**Not supported as a product:** Tauri / Electron auto-updater narratives. A `src-tauri/`
scaffold may remain for experiments; do not document or market it as a shipping multi-OS
updater. Prefer documenting Releases installers or `restore serve` from source/Docker.

**Licence bundle:** ship `LICENSE`, `NOTICE`, and `THIRD_PARTY_NOTICES.md` with binary
artefacts when packaging includes them; keep downloadable-weight terms in
`docs/MODEL_STACK.md` distinct from bundled code/fonts.

---

## 9. Testing & reliability

- **Node contract tests**: every `RestorationNode` plugin runs against a small fixed set of
  synthetic degraded test images (blur/noise/low-res/face-crop/JPEG-artifact) in CI on CPU
  where feasible, or gated to a GPU runner otherwise — a regression in output quality or a
  crash on a known input is caught before merge, not after a user reports it.
  Given the scale is a handful of nodes at launch and growing, this should stay cheap: a
  smoke test (does it run and produce a same-shape output without error) is the CI-gating
  bar; perceptual-quality regression checks are a manual/periodic pass, not blocking every PR.
- **Executor tests**: DAG topological-sort correctness, OOM-fallback path, node
  pin/unload behavior — pure logic, no GPU required.
- **No telemetry by default.** Crash reporting is opt-in and explicit; this is a private
  local tool handling personal photos, and that trust boundary is a product requirement, not
  a footnote.
