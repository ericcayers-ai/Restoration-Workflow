# Contributing

Thanks for considering a contribution. Restoration Workflow is one engine
(`backend/`) driving Simple Mode, Studio Mode (`frontend/`), and the `restore`
CLI — all over the same REST + WebSocket API. Read
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) before structural changes.

By participating you agree to the [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## Development setup

**Backend** (Python 3.10+)

```bash
cd backend
pip install -e ".[dev]"              # engine, API, CLI, tests — no torch required
# pip install -e ".[dev,inference]"  # optional: run real model inference
pytest -q                            # ~409 tests collected without [inference] extras
ruff check src/ tests/
```

Without `[inference]`, nodes report themselves unrunnable rather than crashing
startup. Most of the suite (engine, API, CLI, analyzer) runs without torch.
Inference-only tests skip cleanly when dependencies are missing.

**Frontend** (Node 18+; CI uses 20)

```bash
cd frontend
npm install
npm run typecheck
npm run build
# optional: npm run a11y   # after build; axe-core against the production bundle
# optional: npm run dev    # Vite against a running `restore serve`
```

**Version:** keep package / app metadata at **0.6.0** unless a release explicitly
bumps it (`backend/pyproject.toml`, `frontend/package.json`,
`backend/src/restoration/__init__.py`).

## Adding a restoration model

If [spandrel](https://github.com/chaiNNer-org/spandrel)’s `MAIN_REGISTRY` already
supports the architecture, wrapping it is one call:

```python
from restoration.nodes.wrappers import spandrel_image_node
from restoration.core.ordering import STAGE_UPSCALE
from restoration.core.types import LicenseInfo, LicenseKind, NodeCategory, VramTier, WeightFile

MyModelNode = spandrel_image_node(
    id="my_model",
    display_name="My Model",
    description="One line describing what it restores.",
    category=NodeCategory.REGRESSION,
    stage=STAGE_UPSCALE,
    vram_tier=VramTier.MID,
    license=LicenseInfo("Apache-2.0", LicenseKind.PERMISSIVE, "https://.../LICENSE"),
    weights=[WeightFile(filename="my_model.pth", size_bytes=..., sha256="...",
                        url="https://.../my_model.pth")],
)
```

Register in `BUILTIN_NODES` (`backend/src/restoration/nodes/__init__.py`) or via
`plugins/<name>/manifest.json` — same path (`docs/ARCHITECTURE.md` §7,
`docs/PLUGIN_SDK.md`).

**Licence and weight source are yours to verify** — do not trust a paper README
alone. `docs/MODEL_STACK.md` explains tiers: Simple Mode Auto (`RuleTable.validate()`)
must not depend on non-permissive nodes. Prefer author-hosted or Hugging Face mirrors
with a real sha256; Google-Drive-only distributions are a poor fit for defaults.

For non-trivial nodes (second input, face align/paste-back, vendored arch), subclass
`SpandrelNode` / `BaseRestorationNode` — see `face_nodes.py`, `lama.py`,
`instructir.py`.

## Security and licence rules

Non-negotiable anywhere weights are read (`nodes/_torch.py`):

- Never unpickle checkpoints. Use `torch.load(..., weights_only=True)` or safetensors —
  never `spandrel.ModelLoader.load_from_file`.
- Checksum proves identity, not safety; both gates are required.
- Do not bypass licence acknowledgement for restricted weights (API, CLI, Simple presets,
  or “Download all”).

Report vulnerabilities privately — [`SECURITY.md`](SECURITY.md). Do not open a public issue.

## Accessibility and UI expectations

- Follow [`docs/UI_DESIGN.md`](docs/UI_DESIGN.md) (Safelight) and
  [`docs/ACCESSIBILITY.md`](docs/ACCESSIBILITY.md).
- Prefer tokens from `frontend/src/styles/tokens.css`; avoid one-off colours.
- User-visible strings belong in `frontend/src/locales/en.json` via `useT()`.
- UI PRs should note keyboard / screen-reader impact; run `npm run a11y` when the
  change touches shell, Settings, Simple review, or Inspector.

Describe **shipped or clearly intended** behaviour only — do not document unfinished
controls as if they already work.

## Changelog

User-visible behaviour changes need a `CHANGELOG.md` entry under the current
unreleased / next version section (Keep a Changelog style). Prefer “why” over a
file dump. Fix encoding (use ASCII `--` or proper Unicode em dashes consistently).

## Pull requests

Use the [PR template](.github/PULL_REQUEST_TEMPLATE.md). Before opening:

- Backend: `pytest -q` and `ruff check src/ tests/`
- Frontend: `npm run typecheck` and `npm run build`
- Keep the diff scoped; update `tests/test_rules.py` if you change
  `core/data/rule_table.json`
- New models: verified licence + weight source in the PR description
- Packaging / docs: do not claim a Tauri auto-updater as a shipping product — the
  supported desktop artefact is the PyInstaller Windows zip (`RELEASING.md`)

## Code style

- Backend: [ruff](https://docs.astral.sh/ruff/) (`line-length = 96`) per
  `backend/pyproject.toml`
- Frontend: TypeScript strict, CSS Modules, no component library
- Comments explain *why*, not *what*
