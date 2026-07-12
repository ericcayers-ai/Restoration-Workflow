# Contributing

Thanks for considering a contribution. This project is one engine (`backend/`) driving
two UIs (`frontend/`) and a CLI, all built from the same REST + WebSocket API — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the pieces fit together before
making a structural change.

## Development setup

**Backend**

```bash
cd backend
pip install -e ".[dev]"        # engine, API, CLI, tests — no torch/opencv needed
# pip install -e ".[dev,inference]"  # add this to actually run model inference
pytest                          # 264 tests, ~5s without [inference]
ruff check src/ tests/
```

Nodes report themselves as unrunnable rather than the app failing to start when
`[inference]` isn't installed — most of the test suite (and all of the engine, API,
CLI and analyzer) works without a 2GB torch install. Only `tests/test_tiling.py` needs
`[inference]`, and skips cleanly (via `pytest.importorskip`) without it.

**Frontend**

```bash
cd frontend
npm install
npm run typecheck
npm run build     # or `npm run dev` for a hot-reloading dev server against `restore serve`
```

## Adding a new restoration model

If it's already supported by [spandrel](https://github.com/chaiNNer-org/spandrel)'s
`MAIN_REGISTRY` (40+ architectures — HAT, DAT, SwinIR, SCUNet, NAFNet, RestoreFormer, and
more), wrapping it is one function call — no new module required:

```python
from restoration.nodes.wrappers import spandrel_image_node
from restoration.core.ordering import STAGE_UPSCALE
from restoration.core.types import LicenseInfo, LicenseKind, NodeCategory, VramTier, WeightFile

MyModelNode = spandrel_image_node(
    id="my_model",
    display_name="My Model",
    description="One line describing what it restores.",
    category=NodeCategory.REGRESSION,
    stage=STAGE_UPSCALE,   # where it sits in the auto-order restoration chain
    vram_tier=VramTier.MID,
    license=LicenseInfo("Apache-2.0", LicenseKind.PERMISSIVE, "https://.../LICENSE"),
    weights=[WeightFile(filename="my_model.pth", size_bytes=..., sha256="...",
                        url="https://.../my_model.pth")],
)
```

Add the returned class to `BUILTIN_NODES` in `backend/src/restoration/nodes/__init__.py`,
or register it from a third-party `plugins/<name>/manifest.json` — same registration path,
no core edits needed either way (`docs/ARCHITECTURE.md` §7).

**Before adding a model, verify the license and the weight source yourself** — don't take
a paper's README at face value. `docs/MODEL_STACK.md` documents the process and the
license tiers that gate what can ship as a *default*: the automatic pipeline
(`RuleTable.validate()`) refuses to route to anything but a permissively-licensed node.
Weights must come from a source you can pin a real sha256 against; a Google-Drive-only
distribution is not acceptable for a default/Studio node (see `MODEL_STACK.md`'s note on
why HAT isn't shipped yet).

For anything that isn't a straightforward `image -> image` call (a second input, a
multi-step pipeline like the face nodes' detect/align/restore/paste-back), subclass
`SpandrelNode` or `BaseRestorationNode` directly — see `nodes/face_nodes.py` and
`nodes/lama.py` for real examples.

## Security-sensitive code

Two rules are non-negotiable anywhere weights are read (`nodes/_torch.py`):

- Weights are **never unpickled**. Read via `torch.load(..., weights_only=True)` or
  `safetensors`, never `spandrel.ModelLoader.load_from_file`.
- A checksum proves a file is the one that was expected; it does not prove the file is
  safe. Both gates are required, not either/or.

See [`SECURITY.md`](SECURITY.md) for the full policy and how to report a vulnerability.

## Pull requests

- Run `pytest` and `ruff check` (backend) and `npm run typecheck && npm run build`
  (frontend) before opening a PR — CI runs the same checks, but catching it locally is
  faster for everyone.
- Keep the change scoped to what the PR describes; unrelated cleanup makes review harder,
  not easier.
- If you're changing the default auto-pipeline (`core/data/rule_table.json`), update the
  routing tests in `tests/test_rules.py` — they assert the exact chain for representative
  degradation profiles, on purpose.

## Code style

- Backend: [ruff](https://docs.astral.sh/ruff/) (`line-length = 96`), see
  `backend/pyproject.toml` for the enabled rule sets.
- Frontend: TypeScript strict mode, CSS Modules, no component library — see
  `docs/UI_DESIGN.md` for the visual identity before adding UI.
- Comments explain *why*, not *what* — a well-named function doesn't need a comment
  restating its name.
