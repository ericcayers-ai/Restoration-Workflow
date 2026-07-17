# Restoration Workflow

[![CI](https://github.com/ericcayers-ai/Restoration-Workflow/actions/workflows/ci.yml/badge.svg)](https://github.com/ericcayers-ai/Restoration-Workflow/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/ericcayers-ai/Restoration-Workflow?include_prereleases)](https://github.com/ericcayers-ai/Restoration-Workflow/releases)

**Local-first photo restoration.** Drop a damaged photo, review the auto-picked
pipeline, restore it — or open Studio and author every stage yourself. One FastAPI
engine and DAG executor behind both. No cloud account, no subscription; photos stay
on your machine unless you send them elsewhere.

**[Download the latest release](https://github.com/ericcayers-ai/Restoration-Workflow/releases/latest)**
· [Run from source](#from-source)
· [Model stack](docs/MODEL_STACK.md)

---

## At a glance

| | Simple Mode | Studio Mode |
|---|---|---|
| Who it's for | Fix one photo with almost no setup | Build, tweak, and reuse pipelines |
| Flow | Drop → analyze → review stages → restore | Attach photo → order nodes → Inspect → Run |
| Defaults | Permissive Auto path + quality tiers | Full Model Stack, presets, import/export |
| Same engine | Yes — both submit the same pipeline JSON | Yes |

```mermaid
flowchart LR
  A[Drop photo] --> B[Analyze]
  B --> C[Review stages]
  C --> D[Restore]
  D --> E[Save / Open in Studio]
```

---

## Screenshots

<p align="center">
  <img src="docs/screenshots/simple-mode-review.png" alt="Simple Mode: review the auto-picked pipeline as an editable stage list before restoring" width="900" />
</p>

<p align="center"><em>Simple Mode — review the analyzer’s pipeline, reorder or drop stages, then restore.</em></p>

<p align="center">
  <img src="docs/screenshots/advanced-pipeline-builder.png" alt="Studio Mode: ordered stage list with Inspector open on a node’s parameters" width="900" />
</p>

<p align="center"><em>Studio Mode — Model Stack, ordered workflow, Inspector parameters, contact sheet.</em></p>

<details>
<summary>Settings → Manage Downloads (weights on demand)</summary>

<p align="center">
  <img src="docs/screenshots/manage-downloads.png" alt="Manage Downloads: model stack with install state and download controls" width="900" />
</p>

<p align="center"><em>Nothing is fetched until you ask. Licence status is visible per model.</em></p>
</details>

> Screenshots may lag the latest Safelight UI polish (chrome, step rail, toolbar density
> from the 0.6.x QOL pass). Intended behaviour matches the running app and
> [`CHANGELOG.md`](CHANGELOG.md) — if a capture disagrees, trust the app.

---

## Two ways in

### Simple Mode

1. Drop or browse for a photo.
2. The analyzer picks a stage chain (deblock → denoise → upscale → face → …).
3. Review the editable list — add, remove, or auto-order before you commit.
4. Restore, then save, compare, or hand the same pipeline to Studio.

Quality tiers (draft / balanced / high) adapt tiling and model swaps to hardware
without rewriting the stages the analyzer chose.

### Studio Mode

- **Model Stack** — searchable nodes by category, with VRAM-tier cues.
- **Workflow** — ordered list (and graph) of stages; auto-order can insert a mask
  source when inpainting needs one.
- **Inspector** — parameters from each node’s schema; download weights when missing.
- **Contact sheet** — prior runs on this photo, ready to recall or fork.
- **Workflows as text** — export, edit, share, import.

Master Restorer (InstructIR) lives here for instruction-guided finish passes and
guided ensembles; DDColor colourizes grayscale on the Auto path when appropriate.

---

## What you get

| Capability | Detail |
|---|---|
| One engine, two UIs | Simple and Studio submit the same pipeline JSON to the same executor |
| Auto-order | Stage ranks arrange a chosen set; mask sources inserted when needed |
| Downloads on demand | Settings → Manage Downloads; gated models require acknowledgement |
| Quality tiers | Simple Mode Auto: draft / balanced / high |
| Safe weight loading | `torch.load(..., weights_only=True)` or safetensors, with sha256 pins — [`SECURITY.md`](SECURITY.md) |
| CPU works | CUDA speeds things up; it does not gate basic functionality |

---

## Privacy

Inference runs locally. The default server binds to `127.0.0.1` only. There is no
telemetry by default and no account system. Optional upstream downloads (weights)
occur only when you request a model.

---

## Model lanes

Permissive models power the default Simple Mode Auto path. Non-commercial and
restricted models stay opt-in in Studio / Downloads behind acknowledgement.

| Model | Role | Licence (code/weights) |
|---|---|---|
| FBCNN | JPEG artifact removal | Apache-2.0 |
| SCUNet | Blind real-world denoising | Apache-2.0 |
| SwinIR | SR / denoise / JPEG (3 nodes) | Apache-2.0 |
| RealESRGAN | Fast general super-resolution | BSD-3-Clause |
| HAT | Higher-quality SR (HF mirror weights) | Apache-2.0 |
| GFPGAN / RestoreFormer | Face restoration | Apache-2.0 |
| LaMa | Large-mask inpainting | Apache-2.0 |
| DDColor | Grayscale colourization | Apache-2.0 |
| InstructIR | Master Restorer / guided ensembles | MIT |
| BiRefNet, PowerPaint, DiffBIR, … | Matting, text-guided inpaint, diffusion peers | See stack doc |
| CodeFormer, GPEN, SUPIR, FLUX Fill, … | Opt-in / gated quality | Non-commercial or restricted — ack required |

Full research notes and tiers: [`docs/MODEL_STACK.md`](docs/MODEL_STACK.md).
Notices for bundled code/fonts vs downloadable weights: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

---

## Install

### Windows: portable zip (supported desktop build)

1. Download **`RestorationWorkflow-windows.zip`** from
   [Releases](https://github.com/ericcayers-ai/Restoration-Workflow/releases/latest).
2. Extract anywhere.
3. Double-click **`Run.bat`**.

That starts the local PyInstaller-bundled server and opens the UI in your browser.
No separate Python install required. A GPU is optional. Nothing downloads until you
ask for a model.

> **Desktop packaging note:** the supported double-click experience is this Windows
> portable zip. A `src-tauri/` scaffold may exist for experiments; it is **not** a
> shipping multi-OS updater product. Prefer Releases + `Run.bat` (or run from source).

### From source

Requirements: **Python 3.10+**, **Node 18+** (Node 20 used in CI). CUDA optional.

```bash
git clone https://github.com/ericcayers-ai/Restoration-Workflow.git
cd Restoration-Workflow/backend
pip install -e ".[inference]"

cd ../frontend
npm install && npm run build

cd ../backend
restore serve
```

`restore serve` listens on `http://127.0.0.1:8765` by default and serves the built
frontend from the same origin. For a hot-reload UI against a running API, use
`npm run dev` in `frontend/` (see [`CONTRIBUTING.md`](CONTRIBUTING.md)).

CLI (same engine): `restore run -i photo.jpg -o out/`, `restore nodes`,
`restore weights list` — `restore --help`.

### Docker (headless / server)

A root `Dockerfile` builds a headless image for `restore serve`-style use. Confirm
the image’s optional `[inference]` extras match what you need before expecting GPU
inference; smoke-test a real restore after build.

---

## Documentation

| Doc | Contents |
|-----|----------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Engine, API, plugins, packaging (as-shipped) |
| [`docs/UI_DESIGN.md`](docs/UI_DESIGN.md) | Safelight visual identity |
| [`docs/ACCESSIBILITY.md`](docs/ACCESSIBILITY.md) | a11y bar and checklist |
| [`docs/MODEL_STACK.md`](docs/MODEL_STACK.md) | Models, licences, verification notes |
| [`docs/QA_LAUNCH.md`](docs/QA_LAUNCH.md) | Corpus / beta / launch gates |
| [`RELEASING.md`](RELEASING.md) | How to cut a release |
| [`SUPPORT.md`](SUPPORT.md) | Where to get help |
| [`CHANGELOG.md`](CHANGELOG.md) | What shipped per version |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Dev setup and PR expectations |
| [`SECURITY.md`](SECURITY.md) | Vulnerability reporting |
| [`ROADMAP.md`](ROADMAP.md) | Longer-range build plan |

---

## Contributing

Issues and PRs are welcome. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) and the
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Security issues: [`SECURITY.md`](SECURITY.md)
only (no public issues).

---

## License

Core orchestration: **Apache-2.0** — [`LICENSE`](LICENSE) (copyright holder:
Eric Ayers). Individual model weights and some vendored architectures retain
upstream terms — [`NOTICE`](NOTICE), [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md),
and [`docs/MODEL_STACK.md`](docs/MODEL_STACK.md).
