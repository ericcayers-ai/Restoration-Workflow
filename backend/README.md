# Restoration Workflow — backend

The engine: a DAG pipeline executor, the `RestorationNode` plugin contract, a weight manager,
hardware detection, the degradation analyzer, a FastAPI REST/WebSocket surface, and the
`restore` CLI. No UI. Everything here is exercisable from a terminal, which is the point —
see [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for the design this implements.

## Install

```bash
pip install -e ".[dev]"           # engine, API, CLI, analyzer, tests
pip install -e ".[inference,dev]" # ...plus torch/spandrel/opencv, to actually run models
```

The `inference` extra is genuinely optional. Without it the API serves, the CLI runs, the
analyzer analyzes, and the nodes report themselves unrunnable rather than the app failing to
start.

## Use it

```bash
restore hardware                                  # what compute backend was detected
restore nodes                                     # every node, its licence, VRAM tier, install state
restore weights download realesrgan               # checksum-verified, resumable
restore analyze -i photo.jpg                      # the degradation profile and the chain it picks
restore run -i photo.jpg -o out/                  # Simple Mode: no configuration
restore run -i photos/ -o out/ --pipeline p.json  # batch, explicit DAG
restore serve --port 8765                         # headless API + WebSocket
```

`restore run` with no `--preset`/`--pipeline` is Simple Mode: the analyzer profiles the image
and the rule table picks the chain. It prints what it chose and why.

> On Git Bash for Windows, `/usr/bin/restore` shadows this command. Use the full path to
> `Scripts/restore.exe`, or `python -m restoration.cli`.

## In-box nodes

All permissively licensed; Simple Mode's default path never depends on anything else.

| Node | Model | Licence | Role |
|---|---|---|---|
| `realesrgan` | RealESRGAN x2/x4 | BSD-3-Clause | Default general upscaler |
| `fbcnn` | FBCNN | Apache-2.0 | JPEG artifacts, adjustable quality factor |
| `gfpgan` | GFPGAN v1.4 | Apache-2.0 | Fast face restoration |
| `restoreformer` | RestoreFormer | Apache-2.0 | Quality face restoration |
| `lama` | LaMa | Apache-2.0 | Large-mask inpainting (needs a `mask` input) |
| `mask_from_image` | — | Apache-2.0 | Builds a mask from alpha or luminance |
| `blend` | — | Apache-2.0 | Merges two DAG branches |

Face detection and alignment use OpenCV's YuNet (MIT), a detector — never a restoration model.

## Pipelines

A pipeline is a DAG, not a chain. Any node with no incoming `image` edge receives the input
image; exactly one node may have no outgoing edge.

```json
{"version": 1,
 "nodes": [{"id": "m", "type": "mask_from_image", "params": {"source": "alpha"}},
           {"id": "l", "type": "lama"}],
 "edges": [{"from": "m", "to": "l", "to_input": "mask"}]}
```

Branch and merge, which is why the executor is a DAG:

```json
{"version": 1,
 "nodes": [{"id": "g", "type": "gfpgan"},
           {"id": "r", "type": "restoreformer"},
           {"id": "b", "type": "blend", "params": {"alpha": 0.5}}],
 "edges": [{"from": "g", "to": "b", "to_input": "image"},
           {"from": "r", "to": "b", "to_input": "image_b"}]}
```

## Plugins

Drop `plugins/<name>/{manifest.json,plugin.py}` into the data directory. In-box nodes and
third-party nodes register through the same path; no core-code change is required. A plugin
that fails to load is recorded and skipped, never fatal.

```json
{"name": "my-plugin", "version": "1.0.0", "module": "plugin.py", "nodes": ["MyNode"]}
```

## Tests

```bash
python -m pytest      # 229 tests, no GPU, no weights, seconds
python -m ruff check src/ tests/
```

The suite deliberately never downloads a checkpoint: executor, registry, weights, analyzer,
rules, presets, tiling and the HTTP surface are all covered with fakes and mock transports.
Node *contracts* are asserted; node *inference* is verified out-of-band against real weights.

## Two things worth knowing

**Weights are never unpickled.** Checkpoints load via `torch.load(weights_only=True)` or as
`safetensors`, never `spandrel.ModelLoader.load_from_file`. A checksum proves a file is the one
we expected; it does not prove the file is safe. Both gates are enforced in `WeightManager` and
`nodes/_torch.py`. This rule is why LaMa ships from a `safetensors` export — see the note in
`docs/MODEL_STACK.md`.

**Architectures come from `spandrel`'s main registry only.** That package is MIT and excludes
the non-commercial architectures (CodeFormer, MAT, …) that upstream ships in
`spandrel_extra_arches`. The dependency boundary is itself a licensing guardrail.
