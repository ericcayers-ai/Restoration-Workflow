# Original idea (historical)

> This is the raw brainstorm this project started from, kept verbatim for context. It
> predates any actual research or engineering — several models named below were never
> shipped, some don't exist under the names given, and the "node-based drag-and-drop"
> concept was superseded by the Advanced pipeline builder (an ordered stage list, not a
> node graph — see `CHANGELOG.md` 0.2.0). **[`docs/MODEL_STACK.md`](MODEL_STACK.md) is
> the fact-checked version of this list; [`ROADMAP.md`](../ROADMAP.md) is the real build
> plan.** Start there, not here.

## Generative & Diffusion Restoration

- **RealRestorer:** Baseline for high-fidelity blind restoration.
- **SUPIR:** Heavy upscaling; best for raw landscape and texture generation.
- **InstantIR:** Blind generative reference using SDXL and DINOv2 features.
- **DreamClear:** Diffusion Transformer (DiT) with Mixture of Experts (MoAM).
- **UniRestore:** Balanced framework for perception + downstream utility.
- **FLUX Inpainting / Tile:** Structural coherence + complex masked inpainting.

---

## Isolated Face Restoration Stack

- **DiffBIR:** High realism skin texture synthesis.
- **OSDFace / SDFace:** Fast distilled diffusion + GAN hybrid.
- **CodeFormer:** Strong identity preservation under heavy degradation.
- **RestoreFormer++:** Multi-view facial consistency transformer.
- **Progressive Fusion:** StyleGAN → Diffusion → VAE staged refinement.
- **GFPGAN:** Fast general face restoration baseline.
- **GPEN:** Handles extreme geometric face distortion.

---

## Regression & All-in-One Frameworks

- **RealESRGAN:** General-purpose super-resolution workhorse.
- **HAT:** High-quality transformer-based SR.
- **MambaIRv2:** Efficient state-space model for large images.
- **BioIR:** Multi-distortion perceptual restoration.
- **FBCNN:** JPEG artifact removal control model.
- **DarkIR / DarkIRv2:** Low-light + noise + exposure correction.

---

## Masking, Matting & Inpainting

- **LaMa:** Fast object removal and scene fill.
- **PowerPaint:** Text-guided object-aware inpainting.
- **BiRefNet:** High-quality matting (hair, fur, edges).

---

## Workflow Orchestration

- **Restore-R1:** Auto-agent that chains restoration models based on degradation type.

---

## Concept Architecture

### Goal
Node-based drag-and-drop workflow system for chaining restoration models.

### Flow Example
Input → Auto Analyzer → Model Chain → Output

Example:
Input Image → DarkIRv2 → BiRefNet → OSDFace → SUPIR → Output

---

## UI Concept (Simplified)

```
MODEL STACK                WORKFLOW CANVAS
-------------------------------------------------------
[RealRestorer]
[SUPIR]
[DreamClear]
[OSDFace]
[MambaIRv2]
[BiRefNet]

Input → Restore-R1 → Output

[ Run Auto Pipeline ]
```
