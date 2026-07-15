# Third-party notices

This file lists third-party software and fonts **bundled or vendored** with
Restoration Workflow. For **downloadable model weights** (fetched on demand from
upstream hosts), see [`docs/MODEL_STACK.md`](docs/MODEL_STACK.md) — those files
are not shipped inside the Windows zip or the source tree as binary payloads.

Core orchestration code in this repository is **Apache-2.0** — see [`LICENSE`](LICENSE)
and [`NOTICE`](NOTICE).

---

## Bundled fonts (UI)

| Font | Files | Licence |
|------|-------|---------|
| Public Sans | `frontend/public/fonts/PublicSans-Variable.woff2` | SIL OFL 1.1 |
| IBM Plex Mono | `frontend/public/fonts/IBMPlexMono-Regular.woff2`, `…-Medium.woff2` | SIL OFL 1.1 |

Copyright and reserved-font-name details: [`frontend/public/fonts/FONT_NOTICES.txt`](frontend/public/fonts/FONT_NOTICES.txt).  
Full OFL text: [`frontend/public/fonts/OFL.txt`](frontend/public/fonts/OFL.txt).

---

## Vendored model architecture code

These Python modules are packaged with the app so inference can run without
cloning upstream repos at runtime. **Weights remain separate downloads.**

| Component | Path | Upstream | Licence (code) |
|-----------|------|----------|----------------|
| InstructIR (+ NAFNet lineage) | `backend/src/restoration/nodes/vendored/instructir_arch.py` | [mv-lab/InstructIR](https://github.com/mv-lab/InstructIR) | MIT |
| GPEN | `backend/src/restoration/nodes/vendored/gpen_model.py`, `gpen_op.py` | [yangxy/GPEN](https://github.com/yangxy/GPEN) | Academic / non-commercial upstream terms for weights; vendored ops follow upstream |
| MambaIRv2 | `backend/src/restoration/nodes/vendored/mambairv2_arch.py`, `mambair_stubs.py` | [csguoh/MambaIR](https://github.com/csguoh/MambaIR) | Apache-2.0 |

Always confirm the live upstream `LICENSE` before redistributing a fork or
re-publishing vendored files outside this project.

---

## Major runtime / library dependencies (not redistributed as copies here)

Installed via `pip` / `npm` when building from source or during the packaging
pipeline. Representative licences (verify in each package’s metadata):

| Package | Typical role | Licence (verify upstream) |
|---------|--------------|---------------------------|
| FastAPI / Uvicorn / Pydantic | Local API | MIT |
| PyTorch | Inference | BSD-style (see pytorch.org) |
| spandrel / spandrel_extra_arches | Architecture loaders | MIT |
| OpenCV (headless) | Classical CV / face detect | Apache-2.0 |
| React / Vite / TypeScript | Frontend | MIT |
| Hugging Face Hub | Weight downloads | Apache-2.0 |

A frozen Windows build also embeds transitive packages collected by PyInstaller;
treat the installed environment’s licence metadata as authoritative for those
binaries.

---

## Downloadable weights (not bundled)

Nodes declare weight manifests (URL / Hugging Face repo, size, sha256). Examples
of **permissive** default-path models: FBCNN, SCUNet, SwinIR, RealESRGAN, GFPGAN,
RestoreFormer, LaMa, DDColor, InstructIR, HAT (via Hugging Face mirror). Examples
of **acknowledgement-gated** models: CodeFormer, GPEN, SUPIR, FLUX Fill, and other
non-commercial or restricted-base checkpoints.

Product rule: Simple Mode’s automatic rule table stays on the permissive path;
Studio Mode may offer gated models after the user acknowledges upstream terms.
