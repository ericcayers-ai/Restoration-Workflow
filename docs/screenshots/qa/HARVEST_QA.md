# Harvest Scan_12 QA (Phase 5)

Date: 2026-07-18  
Branch: `cursor/chore-ui-polish-harvest-qa`  
Source: `docs/screenshots/qa/Scan_12_harvest_source.png` (copied from Cursor assets Scan_12)

## How it was run

```bash
# From repo root — isolated data dir, CPU, heuristic VLM (no Qwen weights)
PYTHONPATH=backend/src python docs/screenshots/qa/run_harvest_qa.py
```

Also: `pytest tests/test_auto_vlm.py tests/test_mask_editor.py` (23 passed).  
`frontend/scripts/visual-qa.mjs` is **not present** in this repo; frontend `tsc -b` passed after polish.

## Coverage checklist

| Expectation | Result |
|---|---|
| Downscale / print DPI advice | **Worked.** Heuristic: long edge 1024px → upscale before large print; ~300 DPI target. Native size ≈ 3.4×2.4 in at 300 DPI. |
| Denoise / grain | **Partial.** Analyzer `noise_score=0` / `grain_or_noise=false` on this downscaled preview — no denoise node in Auto plan. Path exists in skill/presets when grain is detected. |
| Scratch via Mask Editor | **Path validated.** Classical scratch detect API + mask export covered by unit tests; on this image `scratch_mask_mean=0` (detector found no defects at current thresholds). Overlay/mask PNGs saved for inspection. |
| Highlight rescue / exposure | **Not triggered.** `blown_highlights=false`, `over_exposure≈0.013`. Exposure/highlight presets remain available in Studio. |
| Face (OSD) | **Not triggered.** `face_count=0` on this crop — OSDFace would gate if faces were detected and licence ack’d. |
| Optional colorize | **Worked (plan).** Goal `colorize` → pipeline `[ddcolor, realesrgan]`. Archival goal stayed B&W (`[realesrgan]` + DPI reason). |

## Artifacts

- `Scan_12_harvest_source.png` — source scan
- `Scan_12_scratch_mask.png` — classical defect mask (empty for this frame)
- `Scan_12_scratch_overlay.png` — amber overlay preview
- `Scan_12_harvest_qa.json` — full JSON report
- `run_harvest_qa.py` — reproducible script

## Gaps

1. **No full GPU E2E restore** — RealESRGAN/LaMa/OSDFace weights not exercised on this machine for a pixel before/after.
2. **Qwen2.5-VL not installed** — describe/plan/suggest used `force_heuristic=True`; VLM download path still available in Settings → Vision.
3. **Heuristic under-calls damage** on this 1024px preview (clean photo summary). Full-res scan + installed VLM would be the next fidelity step.
4. **visual-qa.mjs** missing — polish verified via typecheck + axe-oriented a11y script availability (`npm run a11y` after build).
