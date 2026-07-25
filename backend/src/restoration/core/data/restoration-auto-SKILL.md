---
name: restoration-auto
description: >
  Skill-driven routing for local photo restoration Auto. Maps a structured
  photo description (from Qwen2.5-VL or the CPU analyzer) plus an optional user
  goal into an active-stack pipeline. Legacy nodes and unacked NC models never
  enter the default Auto path.
---

# Restoration Auto skill

## Inputs

- **description** — JSON from `describe_photo` / `POST /api/auto/describe`
- **goal** (optional) — free text normalized to:
  `""` | `archival` | `colorize` | `portrait` | `damaged` | `maximum`
- **installed / acknowledged** — which weights are on disk and licence-acked

## Planner modes

| Mode | When | Behaviour |
|------|------|-----------|
| **skill** | VLM installed *or* heuristic description available | This document’s rules → chain |
| **rule_table** | Caller requests CPU fallback | `core/data/rule_table.json` only (permissive nodes) |

`POST /api/auto/plan` prefers **skill** with VLM describe when weights exist; otherwise heuristic describe + skill rules. Pass `fallback=rule_table` to force the classic analyzer path.

## Active nodes (never Legacy)

| Id | Role | Params / gates |
|----|------|----------------|
| `exposure_correct` | Classical exposure / dual-tone | `clip_limit`, `strength` |
| `darkir` | Low-light companion | **Gated (unclear)** — only when installed + acked |
| `fbcnn` | JPEG deblock | `quality_factor` (50–90) |
| `realesrgan` | Fast blind SR | `scale` 2 or 4 |
| `mambair` | Quality denoise + SR | Prefer when installed |
| `ddcolor` | Colourize grayscale | Skip if `is_bw_intended` / goal `archival` |
| `lama` | Scratch / defect inpaint | Pair with Mask Editor mask |
| `instructir` | Prompt finish / highlight regen | MIT; use `blown_highlight_rescue` preset |
| `supir` | Generative upscale / highlight | **NC gated** — only when acked |
| `osdface` | Face restore (only face rail) | **Gated** — never on unacked Auto |
| `rmbg2` | Matting | **NC gated** — Studio / Mask Editor, not default Auto |
| `powerpaint` / `flux_fill` | Masked inpaint | Mask Editor / Studio; not default Auto |

**Removed forever:** `diffbir`, `hat`.  
**Legacy (Settings only):** `scunet`, `swinir*`, `old_photos_scratch`, `gfpgan`, `restoreformer`, `codeformer`, `gpen`, `birefnet`, `mask_from_image`.

## Routing rules

1. **Low light** → `darkir` if ready else `exposure_correct`.
2. **Blown highlights** → `exposure_correct` then `instructir` (or `supir` if ready).
3. **JPEG** → `fbcnn` with severity-scaled `quality_factor`.
4. **Grain / noise** → `mambair` when installed.
5. **Scratches / goal damaged** → `lama` (+ Mask Editor note).
6. **Grayscale + not archival** → `ddcolor`; **archival / bw_intended** → never colourize.
7. **Upscale** → `realesrgan` (or `mambair` for `maximum`).
8. **Faces + acked** → `osdface`; otherwise reason-only (no silent gated run).
9. **DPI** → attach `downscale_advice` / `recommended_print_dpi` as a reason, not a node.

## Licence gate

Simple Auto and skill plans must not insert a node with `requires_acknowledgement` unless that node is already acknowledged. Missing weights are allowed in the plan (UI prompts download); missing acknowledgement is not.

## Goals → emphasis

| Goal | Emphasis |
|------|----------|
| *(empty)* | Balanced skill route from description |
| `archival` | Mono-safe; no `ddcolor` |
| `colorize` | Force `ddcolor` when grayscale |
| `portrait` | Prefer face path when faces exist |
| `damaged` | Include `lama` |
| `maximum` | Prefer `mambair` / installed companions |

## Studio suggestions

`POST /api/auto/plan` (and `/api/auto/suggest`) returns named dynamic presets from describe+goal. User-saved presets remain in `/api/presets`; builtins stay seeded for Simple Mode but Studio surfaces **suggestions + user presets** first.
