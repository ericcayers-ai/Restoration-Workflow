# Graph Report - .  (2026-07-10)

## Corpus Check
- Corpus is ~10,196 words - fits in a single context window. You may not need a graph.

## Summary
- 112 nodes · 198 edges · 12 communities (10 shown, 2 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 2 edges (avg confidence: 0.8)
- Token cost: 0 input · 149,208 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Core Engine & Default Model Tier|Core Engine & Default Model Tier]]
- [[_COMMUNITY_Phase 4 Model Stack & Licensing|Phase 4 Model Stack & Licensing]]
- [[_COMMUNITY_Backend Execution Engine & Prior Art|Backend Execution Engine & Prior Art]]
- [[_COMMUNITY_Product Identity & Mode UX|Product Identity & Mode UX]]
- [[_COMMUNITY_Customization & Accessibility|Customization & Accessibility]]
- [[_COMMUNITY_Roadmap Meta & Vision|Roadmap Meta & Vision]]
- [[_COMMUNITY_Desktop Packaging & Distribution|Desktop Packaging & Distribution]]
- [[_COMMUNITY_Auto-Routing & Degradation Analysis|Auto-Routing & Degradation Analysis]]
- [[_COMMUNITY_Graphify Tooling Setup|Graphify Tooling Setup]]
- [[_COMMUNITY_Typography System|Typography System]]
- [[_COMMUNITY_CLI & Server Mode|CLI & Server Mode]]
- [[_COMMUNITY_Iconography System|Iconography System]]

## God Nodes (most connected - your core abstractions)
1. `Phase 4 — Full Model Stack Integration` - 18 edges
2. `RestorationNode plugin protocol` - 15 edges
3. `Model licensing tiers (Permissive / Non-commercial / Unclear / Restricted-base)` - 14 edges
4. `Pipeline Executor / DAG engine` - 12 edges
5. `Degradation Analyzer (v1 heuristic)` - 11 edges
6. `Phase 1 — Core Engine` - 11 edges
7. `Restoration Workflow — Planning (README)` - 10 edges
8. `Phase 2 — Simple Mode` - 9 edges
9. `Definition of Done` - 9 edges
10. `System Architecture` - 8 edges

## Surprising Connections (you probably didn't know these)
- `README ASCII UI concept (Model Stack / Workflow Canvas mockup)` --semantically_similar_to--> `Studio Mode screen (Model Stack rail / Canvas / Inspector / Contact Sheet)`  [INFERRED] [semantically similar]
  README.md → docs/UI_DESIGN.md
- `Phase 4 — Full Model Stack Integration` --references--> `HAT`  [EXTRACTED]
  ROADMAP.md → docs/MODEL_STACK.md
- `Phase 4 — Full Model Stack Integration` --references--> `BioIR`  [EXTRACTED]
  ROADMAP.md → docs/MODEL_STACK.md
- `Model licensing tiers (Permissive / Non-commercial / Unclear / Restricted-base)` --references--> `README license note (Core orchestration Apache 2.0)`  [EXTRACTED]
  docs/MODEL_STACK.md → README.md
- `Model Stack — Verified` --references--> `Restoration Workflow — Planning (README)`  [EXTRACTED]
  docs/MODEL_STACK.md → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Phase 1 seed nodes implementing the RestorationNode contract** — roadmap_phase1, docs_architecture_restorationnode, docs_model_stack_realesrgan, docs_model_stack_fbcnn, docs_model_stack_lama [EXTRACTED 1.00]
- **Phase 2 Simple Mode default auto-pipeline (analyzer + face/matting nodes)** — roadmap_phase2, docs_architecture_degradationanalyzer, docs_model_stack_gfpgan, docs_model_stack_restoreformerplusplus, docs_model_stack_birefnet [EXTRACTED 1.00]
- **Safelight darkroom metaphor design language** — docs_ui_design_safelight, docs_ui_design_darkroom_metaphor, docs_ui_design_light_table, docs_ui_design_contact_sheet, docs_ui_design_simple_mode [EXTRACTED 1.00]

## Communities (12 total, 2 thin omitted)

### Community 0 - "Core Engine & Default Model Tier"
Cohesion: 0.18
Nodes (21): Hardware Detector, Node contract tests, RestorationNode plugin protocol, RunContext, VRAM tiering (LOW/MID/HIGH/VERY_HIGH), God Nodes analysis section, graphify-out/GRAPH_REPORT.md, /graphify query "<question>" (+13 more)

### Community 1 - "Phase 4 Model Stack & Licensing"
Cohesion: 0.21
Nodes (16): CodeFormer, DiffBIR, DreamClear, FLUX Fill / Tile, GPEN, InstantIR, Model licensing tiers (Permissive / Non-commercial / Unclear / Restricted-base), MambaIRv2 (+8 more)

### Community 2 - "Backend Execution Engine & Prior Art"
Cohesion: 0.15
Nodes (15): ComfyUI (prior art, execution-engine design source), Why not build on ComfyUI headless (GPL-3.0 entanglement + version-fragile API), Executor tests (topo-sort, OOM fallback, pin/unload), GPU semaphore (asyncio.Semaphore(1)), huggingface_hub (resumable downloads), InvokeAI (starter-model importer consent-flow precedent), litegraph.js (ComfyUI's Canvas2D node renderer), No Celery/Redis — in-process asyncio queue decision (+7 more)

### Community 3 - "Product Identity & Mode UX"
Cohesion: 0.18
Nodes (13): DarkIR (v1), "Progressive Fusion" (StyleGAN→Diffusion→VAE) — in-house recipe, not a real project, Contact sheet (batch/run-history grid), Darkroom structural metaphor system, Light table (before/after comparison surface), "Safelight" identity / codename, Simple Mode screen (drop zone → light table), Studio Mode screen (Model Stack rail / Canvas / Inspector / Contact Sheet) (+5 more)

### Community 4 - "Customization & Accessibility"
Cohesion: 0.20
Nodes (11): Plugin SDK (plugins/<name>/manifest.json + module), Presets (versioned JSON pipeline DAGs), Theming (user-overridable CSS token file), Accessibility requirements (contrast/keyboard/screen-reader/motion/scale/i18n), Color system (dark/light theme tokens, verified contrast), Command palette (Cmd/Ctrl+K), Design tokens (CSS custom properties block), High-contrast theme variant (+3 more)

### Community 5 - "Roadmap Meta & Vision"
Cohesion: 0.53
Nodes (9): System Architecture, Using graphify to build this project, Model Stack — Verified, UI & Product Identity — Safelight, Roadmap — Build Plan, Definition of Done, Guardrails (license tiers binding, docs-vs-code drift, snapshot dates, no theoretical done), Phase 0 — Foundation, Research & Identity (+1 more)

### Community 6 - "Desktop Packaging & Distribution"
Cohesion: 0.32
Nodes (8): ComfyUI Desktop (Electron + relocatable Python/PyTorch precedent), Desktop packaging (Tauri v2 sidecar / Electron fallback), Electron as proven fallback if Tauri sidecar blocks, Jan.ai (Electron→Tauri installer-size precedent), Managed first-run Python/PyTorch venv setup (not a bundled binary), Pinokio (managed first-run install precedent), Tauri v2 desktop shell, Phase 8 — Packaging & Distribution

### Community 7 - "Auto-Routing & Degradation Analysis"
Cohesion: 0.54
Nodes (8): Degradation Analyzer (v1 heuristic), DegradationProfile data structure, Q-Agent, RAR (saic-fi), Restore-R1, RL-Restore, README Workflow Orchestration concept (Restore-R1 auto-agent chain example), Phase 5 — Smart Orchestration v2 (conditional)

### Community 8 - "Graphify Tooling Setup"
Cohesion: 0.50
Nodes (4): graphify-out/graph.json (persistent graph artifact), graphify (knowledge-graph tool), .graphifyignore (adjusted to include markdown docs), .graphify_hook_installed (post-commit auto-rebuild hook)

### Community 9 - "Typography System"
Cohesion: 0.67
Nodes (3): IBM Plex Mono / JetBrains Mono (technical-readout typeface), Public Sans / IBM Plex Sans (UI chrome typeface), Typography system (UI sans + technical mono)

## Knowledge Gaps
- **30 isolated node(s):** `UniRestore`, `DiffBIR`, `SDFace`, `MambaIRv2`, `PowerPaint` (+25 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Definition of Done` connect `Roadmap Meta & Vision` to `Core Engine & Default Model Tier`, `Phase 4 Model Stack & Licensing`, `Product Identity & Mode UX`, `Customization & Accessibility`, `Desktop Packaging & Distribution`?**
  _High betweenness centrality (0.275) - this node is a cross-community bridge._
- **Why does `Phase 4 — Full Model Stack Integration` connect `Phase 4 Model Stack & Licensing` to `Core Engine & Default Model Tier`, `Product Identity & Mode UX`, `Auto-Routing & Degradation Analysis`?**
  _High betweenness centrality (0.174) - this node is a cross-community bridge._
- **Why does `Pipeline Executor / DAG engine` connect `Backend Execution Engine & Prior Art` to `Core Engine & Default Model Tier`, `Product Identity & Mode UX`, `Auto-Routing & Degradation Analysis`?**
  _High betweenness centrality (0.165) - this node is a cross-community bridge._
- **What connects `UniRestore`, `DiffBIR`, `SDFace` to the rest of the system?**
  _32 weakly-connected nodes found - possible documentation gaps or missing edges._