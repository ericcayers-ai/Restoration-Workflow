# Restoration Workflow Revamp — Design Spec

**Date:** 2026-07-20
**Version:** 1.0
**Status:** In Progress (verified 2026-07-27: Phase 1 cleanup, Phase 2A OpenAPI codegen fully implemented. Phase 3B i18n infra fully implemented but locale coverage is partial — see note under 3B. Follow-up deep-audit pass same day found and fixed a real CI-breaking bug in the frontend a11y pipeline — see 2B/3F notes. Remaining sub-phases 2B-2F, 3A, 3C-3G audited at a survey level; concrete code-only fixes applied where found; most component/visual/translation work remains open pending human design/translation input — see per-phase notes below.)

### 2026-07-27 follow-up audit notes

- **Real bug found & fixed (2B/2C/3F overlap):** `frontend/src/lib/useWeightDownloads.tsx`'s poll loop did `for (const row of rows)` inside a `setTracker` React-state updater. Because the updater runs during React's render phase (not synchronously inside the calling `try`), a non-array `rows` (e.g. any malformed/legacy `/api/weights/downloads` response) threw an uncaught `TypeError: ... is not iterable` that escaped the surrounding `try/catch` and crashed the whole app to the `ErrorBoundary`. Fixed by guarding `Array.isArray(rows)` before entering the updater.
- **Real bug found & fixed (3F/CI):** `frontend/scripts/a11y-check.mjs` (the `npm run a11y` / `axe-core` WCAG check wired into `.github/workflows/ci.yml`) mocked `/api/analyze` but not `/api/auto/plan` — the endpoint Simple Mode's default (no-preset) upload flow actually calls. Every request fell through to the mock's default `{}` response, so `result.routing` was `undefined`, crashing to the ErrorBoundary and then timing out waiting for the "Review workflow" screen. **This means the a11y/axe-core CI check has been silently failing to reach or audit the Simple-Mode review screen, Studio InstructIR Inspector, and ensemble-confirm screens** (all gated behind this same flow) since `/api/auto/plan` was introduced — i.e. 3F's stated "axe-core audit (zero violations)" claim was unverified for most of the app's states. Fixed by adding the missing mock route (reusing the already-correct `/api/analyze` response shape, which matches `AutoPipeline` in `frontend/src/lib/types.ts`). Also added a missing `/api/weights/downloads` GET mock (was falling through to `{}` too, triggering the bug above during the mocked run itself).
- Added defense-in-depth in `frontend/src/components/simple/SimpleMode.tsx`: `autoPlan()` result is now validated (`result?.routing?.reasons` / `result.pipeline` present) before use, throwing a catchable, user-facing error (`simple.error.malformedPlan`, added to `en.json`/`es.json`) instead of crashing to the ErrorBoundary on any future backend/frontend type drift.
- After these fixes: `npm run a11y` passes cleanly for empty-shell, Settings dialog, Simple review, and Studio InstructIR/ensemble screens (previously it errored/timed out before reaching any of those — confirms none of them had been axe-audited in CI). Full test/build status is in the "Final verification" section below.
- **3B correction:** i18n *infrastructure* (locale switcher, ICU-style `{{var}}` interpolation, RTL-ready seam, 5 catalogs wired into `I18nProvider`) is fully implemented and correct, as previously verified. However, catalog *coverage* is uneven: `en.json` has 288 keys, `es.json` 204, `de.json` 79, `ja.json` 78, `mi.json` 58 (counts as of this pass). Missing keys silently fall back to the raw key string (by design, per `i18n.tsx`), so German/Japanese/Māori users see many literal English-ish keys instead of translated text today. **Blocked on human input:** completing de/ja/mi translation coverage requires a native/fluent speaker (or a reviewed MT pass) per locale — this is a translation-content task, not a code task, so it is intentionally not attempted here.

### Per-remaining-sub-phase status (2026-07-27 follow-up pass)

- **2B (VLM/Local LLM "just works"):** Partial. The download-polling crash above was found and fixed (this is exactly the class of "just works" bug the sub-phase targets). Did not complete a full audit of VLM download/inference error-message copy or an automated end-to-end download→describe→plan→suggest test in this pass — that requires exercising real model downloads/inference (network- and hardware-dependent) which is out of scope for a code-only, non-interactive pass. **Needs human/CI-with-network decision:** whether to add a marked-slow/integration pytest that actually downloads a small VLM and runs describe→plan→suggest, or keep relying on the existing mocked unit tests (`backend/tests/test_auto_vlm.py`).
- **2C (Model downloads — all implementations work):** Not separately re-audited this pass beyond the shared download-polling fix above (which benefits every download UI surface: Settings, Simple auto-bootstrap, Studio Inspector). Auditing all 19 active + 11 legacy `BUILTIN_NODES` weight paths individually (disk-full/network/checksum/license-gate/cancel per node) is a large matrix; not attempted in this pass. **Needs human decision:** prioritize which of the 30 nodes' download paths are worth dedicated integration tests vs. relying on the existing generic `backend/tests/test_weights.py` coverage.
- **2D (Speed optimization):** Not profiled this pass. Profiling executor/tiling/I/O and building a benchmark suite is inherently measurement-driven (needs representative hardware/images to be meaningful) rather than a pure code-correctness fix, so it's deferred. **Needs human decision:** target hardware profile and acceptable benchmark thresholds before a benchmark suite can be written meaningfully.
- **2E (Best presets):** Not audited in this pass (backend `builtin_presets.py`/`presets.py` and `rule_table.json` routing were not reviewed line-by-line for parameter quality this round). This is a judgment call on restoration-quality tuning per preset, which needs either photographic-QA judgment or a reference corpus with expected outputs — deferred pending a human decision on what "optimal params" means per preset (there's no automated ground truth for image-quality correctness).
- **2F (Backend tests):** Verified: `python -m pytest` in `backend/` passes 449 passed, 1 skipped (no regressions from this pass's changes). No backend code was modified this pass, so no new backend tests were needed.
- **3A (Bolder Safelight identity):** Not attempted — display serif font choice, color palette refinement, and new micro-interaction motion are subjective visual-design decisions with no objective acceptance criteria in the spec. **Needs human decision:** pick a specific serif font (Fraunces vs Newsreader vs Source Serif) and confirm target motion/color direction before implementation.
- **3C (18-component overhaul):** Not attempted this pass beyond the SimpleMode/useWeightDownloads robustness fixes above (which touch 2 of the 18 listed components). A full per-component audit for objective issues (duplicate logic, missing states, prop API cleanup) across all 18 was not done in this pass's time budget. **Recommend as next concrete step:** a follow-up pass that greps each of the 18 named components for TODO/FIXME, duplicate fetch/loading-state logic, and missing empty/error states — that is code-only and well-specified, just not completed here.
- **3D (QOL additions):** Not audited this pass. Undo/redo, batch queue UI, toast notifications, keyboard cheatsheet, and connection-status indicator all need to be checked against current code for existing-vs-missing status individually; not done in this time budget.
- **3E (New features):** Not audited this pass (preset export/import, comparison view, historical job browser).
- **3F (Accessibility — WCAG 2.2 AA):** Partial, but with a significant finding: the automated `npm run a11y` (axe-core via `@axe-core/puppeteer`) CI check existed but was **not actually passing/exercising most app states** due to the `/api/auto/plan` mock gap described above — now fixed, and it passes cleanly (zero critical/serious violations) across empty-shell, Settings dialog, Simple review, and Studio InstructIR/ensemble-confirm states. Manual screen-reader (NVDA) testing, full keyboard-navigation walkthrough, touch-target audit, and the newer WCAG 2.2-specific success criteria (e.g. 2.4.11 Focus Not Obscured, 2.5.7 Dragging Movements, 3.3.7/3.3.8) were not manually re-verified this pass. **Needs human decision/input:** manual NVDA pass requires a human with a screen reader; new 2.2 criteria need a targeted manual review checklist, ideally as a follow-up task with axe-core's ruleset extended once its 2.2 rule coverage is confirmed current.
- **3G (Frontend tests):** Verified: `npx vitest run` passes 23/23 tests across 5 files (all in `frontend/src/lib/*.test.ts` — lib-level only, no component-level tests exist yet). Adding real component tests (e.g. for `SimpleMode`, `SettingsPanel`) would require adding `@testing-library/react` (a new dependency) and a test-renderer harness, which per the task's own guidance ("new dependency with licensing/security implications... stop and note as blocked") is flagged rather than added speculatively in this pass. **Needs human decision:** approve adding `@testing-library/react` + `@testing-library/user-event` as devDependencies (both MIT-licensed, very widely used) so component tests can be added in a follow-up pass.

### Final verification (2026-07-27 follow-up pass)

- Backend: `python -m pytest` → 449 passed, 1 skipped (no failures).
- Frontend: `npm run typecheck` → clean. `npx vitest run` → 23/23 passed. `npm run build` → succeeds. `npm run a11y` → passes (previously crashed/timed out before reaching most screens; root cause fixed, see above).
- No commits made; working tree left uncommitted per instructions.

## Vision

Evolve the mature v0.6.1 Restoration Workflow app into a polished, bold, fully-featured local-first photo restoration studio. Three sequential phases, each verified with screenshots + full logs before the next begins. The Safelight darkroom spirit stays; the execution gets bolder.

## Phase 1: Cleanup & Cruft Removal

Goal: Remove all dead code, debug instrumentation, and cruft. Unblocks clean diffs for phases 2-3.

| # | Item | Detail |
|---|------|--------|
| 1.1 | Remove dead telemetry block | `frontend/src/App.tsx:32-172`: `agentLog()`, `measureUiLayout()`, POST to `127.0.0.1:7278/ingest/...`, `window.__rwMeasureUi`, resize listener. ~140 lines of debug cruft. |
| 1.2 | Remove debug log artifact | `debug-6c8d32.log` at repo root. Add to gitignore. |
| 1.3 | Remove empty top-level `tests/` | Backend tests in `backend/tests/`, frontend in `frontend/src/lib/*.test.ts`. |
| 1.4 | Reformat `api.ts` | Remove double-blank-lines between every line in `frontend/src/lib/api.ts` (698→~350 lines). |
| 1.5 | Reformat `types.ts` | Same cleanup for `frontend/src/lib/types.ts` (564→~280 lines). |
| 1.6 | Remove `src-tauri/` entirely | Cargo.toml, tauri.conf.json, updater.key, updater.key.pub. README says "not a shipping product". |
| 1.7 | Remove Tauri references from docs | README.md, ARCHITECTURE.md, ROADMAP.md. |
| 1.8 | Replace `window.prompt` with modal | `PresetBar.tsx:58` → focus-trapped `<dialog>`. |
| 1.9 | Audit for other cruft | Grep for debug/telemetry leftovers. |

## Phase 2: Backend Hardening

Goal: Every model download works. VLM/local LLM "just works". OpenAPI codegen kills types.ts drift. Speed optimized. Presets are best-in-class.

### 2A: OpenAPI Schema Export + TS Codegen
- Expose `/api/openapi.json` (FastAPI auto-generates)
- Add `openapi-typescript` codegen script (`frontend/scripts/gen-types.mjs`)
- Replace hand-synced `types.ts` with generated `api-types.ts`
- CI drift check: run gen-types, git diff on committed types

### 2B: VLM / Local LLM — "Just Works"
- Audit download flow, inference, error messages, progress UI
- End-to-end test: download → describe → plan → suggest
- Graceful fallback to heuristic when VLM unavailable

### 2C: Model Downloads — All Implementations Work
- Audit every BUILTIN_NODES weight path (19 active + 11 legacy)
- Test error states (disk full, network, checksum, license gate, cancel)
- Test batch download, removal, progress events

### 2D: Speed Optimization
- Profile executor, optimize tiling, image I/O, per-node cache
- Benchmark suite, configuration tuning (tile size, cache, env vars)

### 2E: Best Presets
- Audit all 30 builtin presets for optimal params
- Audit rule_table.json routing accuracy
- Audit quality tiers (draft/balanced/high)

### 2F: Backend Tests
- All existing pytest (~409 tests) pass
- Add VLM, weight download, OpenAPI schema, speed regression tests

## Phase 3: Frontend Evolution

Goal: Bolder Safelight identity. Full i18n (5 locales). Every component polished. QOL additions. New features. WCAG 2.2 AA compliance.

### 3A: Bolder Safelight Identity Evolution
- Add display serif font for headings (Fraunces/Newsreader/Source Serif)
- Enrich motion tokens (slow, stagger, spring)
- Refine color palette across 3 themes
- Add motion to key transitions, micro-interactions
- Refine typography hierarchy, empty states, loading states (skeletons)

### 3B: Full i18n — 5 Locales + RTL
- es (Spanish), mi (Maori), ja (Japanese), de (German), en (base)
- Locale preference in Settings, locale switcher UI
- RTL infrastructure for future Arabic/Hebrew
- ICU message formatting for pluralization

### 3C: UI Component Overhaul (18 components)
App, SimpleMode, StudioMode, ModelStackRail, StageList/StageRow, Inspector, PipelineCanvas, PresetBar, ContactSheet, MaskEditor, SettingsPanel, CommandPalette, LightTable, JobLogPanel, FlowSteps, StatusLine, Button/Icon, PreferencesBar

### 3D: QOL Additions
Undo/redo in Studio, batch queue UI, error/empty/loading states, keyboard shortcut cheatsheet, toast notifications, connection status indicator

### 3E: New Features
Preset sharing (export/import .json), comparison view (multi-restoration), historical job browser, export presets as shareable files

### 3F: Accessibility — WCAG 2.2 AA
axe-core audit (zero violations), keyboard navigation, screen reader (NVDA), focus management, color contrast, touch targets (24px min, 44px rec), reduced motion, high-contrast theme, new 2.2 criteria

### 3G: Frontend Tests
All existing vitest pass, add component tests, i18n tests, new feature tests

## Verification Strategy

At end of each phase: lint, test, build, run, screenshot every state/mode/theme/locale, capture full logs, manual walkthrough. Evidence saved to `docs/revamp-verification/`.

## Execution Order

Phase 1 (Cleanup) → verify → Phase 2 (Backend) → verify → Phase 3 (Frontend) → verify
