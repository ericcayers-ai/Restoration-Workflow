# Model Stack — Verified

Every model in the original README planning notes was fact-checked against live sources
(GitHub, arXiv, Hugging Face) on **2026-07-09**, not recalled from training memory — model
repos, stars, and licenses change fast enough that guessing is not good enough for a
redistribution decision. Sources are linked inline. Treat this document as a snapshot:
before Phase 4 (full model integration) actually starts, re-verify licenses and repo activity
— `GRAPHIFY_WORKFLOW.md` explains how to fold that re-check into the graphify loop instead of
redoing it from scratch.

**Two corrections to the original README worth flagging up front:**
- **"DarkIRv2" does not exist.** DarkIR ships size variants (`-m`/`-l`), not a v2 release.
  Plan around DarkIR (v1) only.
- **"Restore-R1" is real** (Amazon Science, Dec 2025 / CVPR 2026 workshop,
  [arXiv:2512.18599](https://arxiv.org/abs/2512.18599)) — an RL-trained agent that picks a
  restoration tool-call sequence using an MLLM as a no-reference perceptual reward — but it
  has **no released code, weights, or license**. It's a research direction to track, not a
  dependency. `ARCHITECTURE.md` §4 already specifies an in-house heuristic degradation
  analyzer for this exact role, independent of whether/when Restore-R1 ships code — this is
  the correct call, not a fallback.
- **"Progressive Fusion (StyleGAN → Diffusion → VAE)"** matches no paper or repo — it reads as
  a description of a pipeline pattern, not a named project. Treat it as an in-house recipe
  (chain a GAN-tier face model → a diffusion-tier face model → standard decode) rather than
  something to source.

---

## Licensing tiers (read this before wiring up Phase 4)

License is the binding constraint on this stack far more than raw quality is. A surprising
number of the strongest models here are **non-commercial-only**, which directly shapes how
the app can ship:

| Tier | Meaning | Members |
|---|---|---|
| **Permissive** (Apache-2.0 / MIT / BSD) | Safe to bundle, redistribute, and use commercially | RealESRGAN, HAT, MambaIRv2, FBCNN, LaMa, PowerPaint, BiRefNet, DiffBIR, RestoreFormer++, GFPGAN, UniRestore, DreamClear* |
| **Non-commercial only** | App can download/run locally with license acknowledgement; cannot be bundled into a paid product or offered as a hosted commercial service without a separate deal | SUPIR, FLUX.1-Fill-dev + tile ControlNet, CodeFormer (S-Lab NTU 1.0), GPEN (Alibaba academic) |
| **Unclear / unverified** | No LICENSE file found — do not ship until confirmed directly with the author | OSDFace, DarkIR, RealRestorer (Apache-2.0 claimed on the HF card, but the GitHub repo itself has no LICENSE file) |
| **Restricted upstream base** | Code license is permissive but the base checkpoint it fine-tunes carries its own restrictions | InstantIR (Apache-2.0 code, SDXL RAIL++-M base), DreamClear (Apache-2.0 claimed, PixArt-α base — re-verify) |

**Product implication:** the orchestration engine, plugin SDK, and UI are the app's own code
and can be licensed however the user wants (Apache-2.0 recommended, matching the README's
existing "Core orchestration: Apache 2.0" line). Model weights are a separate matter per
`ARCHITECTURE.md` §6 — the Weight Manager gates every non-permissive download behind an
explicit, per-model license acknowledgement, and Simple Mode's *default* auto-pipeline
(Phase 2) should be built from the **Permissive** tier wherever a permissive option is
competitive, reserving non-commercial models (SUPIR, CodeFormer, FLUX Fill) as opt-in
"maximum quality" choices a user consciously reaches for in Studio Mode. This keeps the
out-of-the-box experience legally uncomplicated while still giving power users access to the
best available quality.

---

## Generative & Diffusion Restoration

| Model | Repo | License | VRAM | ComfyUI node | Role |
|---|---|---|---|---|---|
| [RealRestorer](https://github.com/yfyang007/RealRestorer) | 298★, active | Apache-2.0 (HF card; no LICENSE file in repo — verify) | ~34GB @ 1024px | Unofficial ([StartHua](https://github.com/StartHua/Comfyui_RealRestorer)) | Blind restoration across 9 real-world degradations; brand-new (Mar 2026 paper), small community, single-point-of-failure risk — treat as **experimental/opt-in**, not a default |
| [SUPIR](https://github.com/Fanghua-Yu/SUPIR) | 5.6k★ | Non-commercial | ~24GB (fp8: <10GB) | [kijai/ComfyUI-SUPIR](https://github.com/kijai/ComfyUI-SUPIR), actively maintained | Best-in-class generative upscale/restoration; the highest-VRAM-tier "maximum quality" option |
| [InstantIR](https://github.com/instantX-research/InstantIR) | 531★, **stale since Nov 2024** | Apache-2.0 code / SDXL RAIL++-M base | ~12-16GB+ | [smthemex wrapper](https://github.com/smthemex/ComfyUI_InstantIR_Wrapper) | Blind restoration + text-guided "creative" mode; dormant upstream, low priority |
| [DreamClear](https://github.com/shallowdream204/DreamClear) | 1.2k★ | Apache-2.0 (PixArt-α base — verify) | Not documented (1024px DiT) | None found | Degradation-routed DiT restoration; would need a custom node written from scratch |
| [UniRestore](https://github.com/unirestore/UniRestore) | 95★ | MIT | Not documented | None found | Unifies perceptual + task-oriented restoration; most permissive license here, least production-hardened |
| FLUX Fill / Tile | [FLUX.1-Fill-dev](https://huggingface.co/black-forest-labs/FLUX.1-Fill-dev), [jasperai tile upscaler](https://huggingface.co/jasperai/Flux.1-dev-Controlnet-Upscaler) | Non-commercial | ~24GB fp16 / ~12GB quantized | **Native** in ComfyUI core | Best text-guided inpaint/outpaint + tile super-res; non-commercial blocks default-tier use |

**Recommended default for this category:** none of these are cheap enough or permissively
licensed enough to be Simple Mode's default. Gate the entire "Generative & Diffusion" category
behind Studio Mode / explicit opt-in, with SUPIR as the flagship "maximum quality" node once a
user accepts its license — this category is inherently a HIGH/VERY_HIGH VRAM tier regardless
of licensing.

---

## Isolated Face Restoration Stack

| Model | Repo | License | VRAM/Speed | ComfyUI node | Role |
|---|---|---|---|---|---|
| [DiffBIR](https://github.com/XPixelGroup/DiffBIR) | 4.1k★ | Apache-2.0 | Diffusion, slow, tileable | [jtscmw01](https://github.com/jtscmw01/ComfyUI-DiffBIR) | **Not face-specific** — use as a general/background pre-stage feeding into the face nodes below, not as a face-stack member itself |
| [OSDFace](https://github.com/jkwang28/OSDFace) | 284★, active | Unclear — verify before shipping | One-step diffusion, near-GAN speed | None found | The diffusion-quality-at-GAN-speed tier; needs a custom node and a license answer before it can ship |
| SDFace | No installable repo (NTIRE 2025 challenge entry) | N/A | — | — | Real but unreleased — **use OSDFace instead**, do not plan around this name |
| [CodeFormer](https://github.com/sczhou/CodeFormer) | 17.9k★ | **Non-commercial** (S-Lab NTU 1.0) | Fast, ~2-3GB | [mav-rik/facerestore_cf](https://github.com/mav-rik/facerestore_cf), ReActor | Most popular/controllable face restorer; license blocks it from Simple Mode's default path |
| [RestoreFormer / RestoreFormer++](https://github.com/wzhouxiff/RestoreFormerPlusPlus) | 284★, stale since 2023 | **Apache-2.0** | GAN-class speed | None found | Same codebook-transformer family as CodeFormer, commercial-safe — **the default "quality" face node**. See the implementation note below: **v1 ships, ++ does not (yet)** |
| [GFPGAN](https://github.com/TencentARC/GFPGAN) | 37.5k★, unmaintained since Apr 2024 | Apache-2.0 | Fast, ~2-4GB, real-time | [comfyorg](https://github.com/comfyorg/comfyui_gfpgan), ReActor | Most battle-tested baseline — **the default "fast" face node** for Simple Mode |
| [GPEN](https://github.com/yangxy/GPEN) | 2.6k★ | Non-commercial (Alibaba academic) | Fast, high-res variants (1024/2048) | Bundled in ReActor | Useful for severely degraded high-res faces; opt-in only |

**Recommended default:** **GFPGAN → RestoreFormer** as the Simple Mode default face path
(both Apache-2.0), with CodeFormer/GPEN/OSDFace available as opt-in "try alternate face model"
choices in Studio Mode once their license/verification status is accepted. DiffBIR sits in the
*general* regression category functionally, despite the README grouping it with faces —
reclassify it there in the plugin registry.

**Implementation note — RestoreFormer v1 vs. ++ (found during Phase 1, 2026-07-10).**
This document originally named RestoreFormer**++** the default quality face node. That was
wrong in practice, not in principle: `spandrel`'s `RestoreFormer` architecture — the whole
reason these models are cheap to integrate — cannot load the ++ checkpoint. Its `load()`
hardcodes `head_size=8` and `attn_resolutions=(16,)`, while `RestoreFormer++.ckpt` carries
extra decoder attention blocks (`decoder.up.4.attn.*`) and fails `load_state_dict`. Both
checkpoints are Apache-2.0 and both are published on the repo's
[v1.0.0 release](https://github.com/wzhouxiff/RestoreFormerPlusPlus/releases/tag/v1.0.0)
(the README's Google Drive link is stale). Phase 1 therefore ships **RestoreFormer v1** as the
`restoreformer` node — same family, same licence, same speed class. Shipping ++ means
vendoring its architecture rather than leaning on spandrel; that is Phase 4 work, tracked as a
stretch item, not a Phase 1 line item. Note also that neither checkpoint is stored the way
spandrel's architecture detector expects: the weights live under a `vqvae.` prefix inside a
Lightning checkpoint, alongside a `quantize.utility_counter` buffer that is not part of the
module. The node strips both.

---

## Regression & All-in-One Frameworks

| Model | Repo | License | VRAM | ComfyUI node | Role |
|---|---|---|---|---|---|
| [RealESRGAN](https://github.com/xinntao/Real-ESRGAN) | 36.1k★ | BSD-3-Clause | ~2-4GB, tiled | **Native** (Spandrel) | De-facto standard blind SR — **the default general upscaler** |
| [HAT](https://github.com/XPixelGroup/HAT) | 1.6k★ | Apache-2.0 | ~6-8GB+ | Native via Spandrel | SOTA SR quality, slower than RealESRGAN — the "quality" alternative |
| [MambaIRv2](https://github.com/csguoh/MambaIR) | 1.1k★ | Apache-2.0 | ~4-6GB | None — not in Spandrel, needs custom node work | Efficient SOTA SR; real engineering cost to integrate, defer past initial launch |
| BioIR | No public code (NeurIPS'25 poster only) | Unknown | Unknown | None | Real, distinct project — **do not plan around a repo that doesn't exist yet**; revisit later |
| [FBCNN](https://github.com/jiaxi-jiang/FBCNN) | 522★ | Apache-2.0 | <2GB, fast | [ComfyUI-FBCNN](https://www.runcomfy.com/comfyui-nodes/ComfyUI-FBCNN) | Reference model for adjustable-strength JPEG artifact removal — ship as default |
| [DarkIR](https://github.com/cidautai/DarkIR) | — | Unconfirmed — verify LICENSE directly | ~2-4GB (m/l variants) | None found | All-in-one low-light/noise/blur; needs a custom node and a license check. **"DarkIRv2" does not exist** — this is v1 only |

**Recommended default:** RealESRGAN (general upscale) + FBCNN (JPEG) ship in Phase 1 as the
first two working nodes — both permissive, both lightweight, both already proven in ComfyUI.
HAT is the natural Phase 4 "quality" upscale option. MambaIRv2, BioIR, and DarkIR all require
real integration engineering (no existing ComfyUI node to reference) — schedule them as
stretch goals within Phase 4, not launch blockers.

---

## Masking, Matting & Inpainting

| Model | Repo | License | VRAM | ComfyUI node | Role |
|---|---|---|---|---|---|
| [LaMa](https://github.com/advimman/lama) | 10.1k★ | Apache-2.0 | ~2-4GB, fast | [Acly/comfyui-inpaint-nodes](https://github.com/Acly/comfyui-inpaint-nodes) | Fast large-mask object removal — **default inpaint/fill node** |
| [PowerPaint](https://github.com/open-mmlab/PowerPaint) | 1.1k★ | MIT | ~6-8GB (SD1.5-based) | [BrushNet PowerPaint node](https://www.runcomfy.com/comfyui-nodes/ComfyUI-BrushNet/PowerPaint) | Text-guided inpaint/removal/outpaint/shape-fill in one model — the "advanced" inpaint option |
| [BiRefNet](https://github.com/ZhengPeng7/BiRefNet) | 3.9k★, active | MIT | ~2-6GB | Multiple forks ([viperyl](https://github.com/viperyl/ComfyUI-BiRefNet), [rubi-du](https://github.com/rubi-du/ComfyUI-BiRefNet-Super)) | High-resolution matting (hair/fur/fine edges), outperforms rembg — **default matting node** |

All three are permissively licensed with real, maintained ComfyUI precedent — this is the
easiest category to ship early and completely.

**Implementation note — LaMa weight distribution (found during Phase 1, 2026-07-10).**
LaMa's code and weights are Apache-2.0, but neither of its two commonly-cited weight
distributions can be loaded safely:

- Upstream's `big-lama.zip` (mirrored at [`smartywu/big-lama`](https://huggingface.co/smartywu/big-lama),
  Apache-2.0) holds a PyTorch Lightning checkpoint that embeds pickled trainer objects. It is
  rejected by `torch.load(weights_only=True)` — correctly, since unpickling it would execute
  code from a downloaded file.
- The widely-mirrored `big-lama.pt` ([Sanster/models](https://github.com/Sanster/models/releases))
  is a **TorchScript archive**, not a state dict. `spandrel` cannot load it at all, and
  TorchScript is code rather than data.

Phase 1 therefore loads a `safetensors` export of the same generator weights — a container
format that cannot carry executable content — with its digest pinned in the node's weight
manifest. The licence is upstream's; only the container changed. If an Apache-2.0-labelled
`safetensors` export appears under an official account, switch the manifest's `hf_repo_id` to
it; the digest pin makes that a one-line, verifiable change.

---

## Workflow Orchestration

The README's own "Restore-R1: auto-agent that chains restoration models" is, per the research
above, a real but code-less research paper. Closest real, inspectable prior art if the
in-house heuristic router (`ARCHITECTURE.md` §4) later wants a learned upgrade path:

- [saic-fi/RAR](https://github.com/saic-fi/RAR) (CVPR'26) — an assess→restore→reassess loop
  in latent space.
- [yuke93/RL-Restore](https://github.com/yuke93/RL-Restore) (CVPR'18) — the historical
  ancestor: an RL agent crafting a per-image restoration toolchain.
- [Q-Agent](https://arxiv.org/abs/2504.07148) — a quality-driven chain-of-thought restoration
  agent using an MLLM.

None are drop-in. **Build the v1 auto-analyzer in-house** as specified in `ARCHITECTURE.md`
§4 (heuristic degradation profile → rule-table pipeline selection); revisit a learned router
in Phase 5 once real usage data exists to train or distill one against, and cite this section
if RAR/RL-Restore/Restore-R1 code ever ships and becomes worth adopting instead.

---

## Suggested launch tiering

| Phase | Ships |
|---|---|
| Phase 1 (core engine) | RealESRGAN, FBCNN, LaMa — all permissive, all lightweight, all ComfyUI-precedented |
| Phase 2 (Simple Mode) | + GFPGAN, RestoreFormer (v1, see note), BiRefNet — enough for a real default auto-pipeline across the common degradation types (low-res, JPEG, faces, background matting) |
| Phase 4 (full stack) | + HAT, PowerPaint, DiffBIR, CodeFormer/GPEN/OSDFace/SUPIR/FLUX (all opt-in behind license acknowledgement) |
| Phase 4 stretch | MambaIRv2, DarkIR, InstantIR, DreamClear, UniRestore, RealRestorer — each needs custom node engineering with no existing reference implementation to build from |
| Watch, don't build | BioIR (no code yet), Restore-R1 (no code yet) |
