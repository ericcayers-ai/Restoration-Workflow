# Restoration Workflow - Planning

> This file is the original raw idea dump. The actual build plan — fact-checked model
> research, system architecture, UI identity, and a phased roadmap for an AI agent to
> execute — lives in **[`ROADMAP.md`](ROADMAP.md)** and `docs/`. Start there.

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
- **Progressive Fusion:** StyleGAN â†’ Diffusion â†’ VAE staged refinement.
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
Input â†’ Auto Analyzer â†’ Model Chain â†’ Output

Example:
Input Image â†’ DarkIRv2 â†’ BiRefNet â†’ OSDFace â†’ SUPIR â†’ Output

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

Input â†’ Restore-R1 â†’ Output

[ Run Auto Pipeline ]
```

---

## Setup

### Requirements
- NVIDIA GPU (CUDA 12.1+)
- Python 3.10+

### Install

```bash
git clone https://github.com/username/repo-name.git
cd repo-name
pip install -r requirements.txt
```

### Weights

```bash
python scripts/download_weights.py --all
```

### Run

```bash
python app.py
```

---

## License

Core orchestration: Apache 2.0  
Individual models: respect original licenses