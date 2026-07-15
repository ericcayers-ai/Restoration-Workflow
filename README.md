# Restoration Workflow

[![CI](https://github.com/ericcayers-ai/Restoration-Workflow/actions/workflows/ci.yml/badge.svg)](https://github.com/ericcayers-ai/Restoration-Workflow/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/ericcayers-ai/Restoration-Workflow?include_prereleases)](https://github.com/ericcayers-ai/Restoration-Workflow/releases)

**Version 0.6.0** — local-first photo restoration. Drop a photo and restore it with
almost no setup (Simple Mode), or author a pipeline in Studio Mode. Both UIs drive
the same FastAPI engine and DAG executor. No cloud account, no subscription; photos
stay on your machine unless you send them elsewhere.

## Screenshots

| Simple Mode — review the auto pipeline | Studio Mode — build a custom pipeline |
|---|---|
| ![Simple Mode: auto-picked workflow as an editable stage list before running](docs/screenshots/simple-mode-review.png) | ![Studio Mode: ordered stage list with Inspector open on a node’s parameters](docs/screenshots/advanced-pipeline-builder.png) |

<details>
<summary>Settings → Manage Downloads</summary>

![Model stack with install state and download controls](docs/screenshots/manage-downloads.png)
</details>

> Screenshots may lag the latest Safelight UI polish. Intended shipped behaviour for
> 0.6.0 is described below; if a screenshot disagrees with the running app, trust the
> app and [`CHANGELOG.md`](CHANGELOG.md).

## What you get

- **One engine, two entries.** Simple Mode (auto-analyze → review stages → restore)
  and Studio Mode (Model Stack + list/graph editors + Inspector) submit the same
  pipeline JSON to the same executor.
- **Auto-order, not just a model list.** Nodes carry restoration-stage ranks
  (deblock → denoise → upscale → face → …). “Auto-order” arranges a chosen set and
  can insert a mask source when inpainting needs one.
- **Downloads on demand.** Weights are not installed with the app. Settings → Manage
  Downloads lists models, sizes, and licence status; missing weights download when
  needed (gated models require acknowledgement first).
- **Quality tiers.** Simple Mode Auto can run draft / balanced / high — tiling and model swaps adapt to hardware without changing the stages the analyzer chose.
- **Master Restorer (InstructIR).** Instruction-guided finish / guided ensembles and
  prompt presets; DDColor handles grayscale colourization on the Auto path.
- **Workflows as text.** Export a pipeline, edit it, share it, import it back.
- **Safe weight loading.** Checkpoints load via `torch.load(..., weights_only=True)`
  or safetensors, with sha256 pins — see [`SECURITY.md`](SECURITY.md).
- **CPU works.** A CUDA GPU speeds things up; it does not gate basic functionality.

## Privacy

Inference runs locally. The default server binds to `127.0.0.1` only. There is no
telemetry by default and no account system. Optional upstream downloads (weights)
occur only when you request a model.

## Model lanes (out of the box)

Permissive models power the default Simple Mode Auto path. Non-commercial and
restricted models remain opt-in in Studio / Downloads behind acknowledgement.

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

Full research notes and tiers: [`docs/MODEL_STACK.md`](docs/MODEL_STACK.md). Notices for
bundled code/fonts vs downloadable weights: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Install

### Windows: portable app (supported desktop build)

Download **`RestorationWorkflow-windows.zip`** from
[Releases](https://github.com/ericcayers-ai/Restoration-Workflow/releases), extract
anywhere, and double-click **`Run.bat`**. That starts the local PyInstaller-bundled
server and opens the UI in your browser. No separate Python install required. A GPU
is optional. Nothing downloads until you ask for a model.

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

## Contributing

Issues and PRs are welcome. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) and the
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Security issues: [`SECURITY.md`](SECURITY.md)
only (no public issues).

## License

Core orchestration: **Apache-2.0** — [`LICENSE`](LICENSE) (copyright holder:
Eric Ayers). Individual model weights and some vendored architectures retain
upstream terms — [`NOTICE`](NOTICE), [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md),
and [`docs/MODEL_STACK.md`](docs/MODEL_STACK.md).
