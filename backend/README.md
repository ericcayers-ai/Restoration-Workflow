# Restoration Workflow — backend

The engine: a DAG pipeline executor, the `RestorationNode` plugin contract, a weight manager,
hardware detection, the degradation analyzer, a FastAPI REST/WebSocket surface, and the
`restore` CLI. No UI. Everything here is exercisable from a terminal — see
[`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

**Package version:** `0.6.1` (`pyproject.toml` / `restoration.__version__`).

## Install

```bash
pip install -e ".[dev]"           # engine, API, CLI, analyzer, tests
pip install -e ".[inference,dev]" # ...plus torch/spandrel/opencv, to actually run models
```

Optional extras: `[diffusion]` (diffusers-tier nodes), `[stretch]` (MambaIRv2 and peers),
`[packaging]` (PyInstaller Windows zip).

The `inference` extra is optional. Without it the API serves, the CLI runs, the analyzer
analyzes, and nodes report themselves unrunnable rather than the app failing to start.

## Use it

```bash
restore hardware                                  # what compute backend was detected
restore nodes                                     # every node, licence, VRAM tier, install state
restore weights download realesrgan               # checksum-verified, resumable
restore analyze -i photo.jpg                      # degradation profile and chosen chain
restore run -i photo.jpg -o out/                  # Simple Mode: no configuration
restore run -i photos/ -o out/ --pipeline p.json  # batch, explicit DAG
restore serve --port 8765                         # local API + WebSocket (+ built frontend if present)
```

`restore run` with no `--preset`/`--pipeline` is Simple Mode: the analyzer profiles the image
and the rule table picks the chain.

> On Git Bash for Windows, `/usr/bin/restore` shadows this command. Use the full path to
> `Scripts/restore.exe`, or `python -m restoration.cli`.

## In-box nodes (illustrative)

Simple Mode’s default Auto path stays on permissively licensed nodes. Studio Mode exposes
the wider stack (including acknowledgement-gated models). For the verified research table
see [`../docs/MODEL_STACK.md`](../docs/MODEL_STACK.md). Core permissive examples:

| Node | Model | Licence | Role |
|---|---|---|---|
| `fbcnn` | FBCNN | Apache-2.0 | JPEG artifacts |
| `realesrgan` | RealESRGAN | BSD-3-Clause | Fast general upscaler |
| `mambair` | MambaIRv2 | Apache-2.0 | Quality upscale (High tier) |
| `lama` | LaMa | Apache-2.0 | Large-mask inpainting |
| `ddcolor` | DDColor | Apache-2.0 | Grayscale colourization |
| `instructir` | InstructIR | MIT | Master Restorer / ensembles |
| `rmbg2` | RMBG-2.0 | CC BY-NC (gated) | Background removal / matting |
| `osdface` | OSDFace | Unclear (gated) | Active face rail |
| `flux_fill` | FLUX Fill | NC (gated) | Text-guided inpaint (masking) |
| `blend` / `exposure_correct` | — | Apache-2.0 | Orchestration / classical |
| *Legacy* | SCUNet, SwinIR*, GFPGAN, … | various | Settings → Legacy only |
| *Removed* | DiffBIR, HAT | — | Not registered |

Face detection uses OpenCV YuNet (MIT) — a detector, not a restoration model. Full registry:
`restore nodes` or `nodes/__init__.py` (`BUILTIN_NODES`).

## Pipelines

A pipeline is a DAG. Any node with no incoming `image` edge receives the input image; exactly
one node may have no outgoing edge. See root [`README.md`](../README.md) and
`docs/ARCHITECTURE.md` for examples (mask→LaMa, dual-face blend).

## Plugins

Drop `plugins/<name>/{manifest.json,plugin.py}` into the data directory. Same registration
path as in-box nodes. A plugin that fails to load is recorded and skipped, never fatal.
See [`../docs/PLUGIN_SDK.md`](../docs/PLUGIN_SDK.md).

## Tests

```bash
python -m pytest -q     # currently ~409 tests collected (no GPU, no weight downloads)
python -m ruff check src/ tests/
```

The suite deliberately never downloads a checkpoint: executor, registry, weights, analyzer,
rules, presets, tiling and the HTTP surface use fakes and mock transports. Node *contracts*
are asserted; node *inference* is verified out-of-band against real weights when needed.

## Two things worth knowing

**Weights are never unpickled.** Checkpoints load via `torch.load(weights_only=True)` or
`safetensors`, never `spandrel.ModelLoader.load_from_file`. A checksum proves identity, not
safety. Both gates live in `WeightManager` and `nodes/_torch.py`. See
[`../SECURITY.md`](../SECURITY.md) and the LaMa note in `MODEL_STACK.md`.

**Downloadable weights ≠ bundled code.** Orchestration is Apache-2.0; fonts and vendored
architectures are attributed in [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md);
weights stay under upstream terms after on-demand download.
