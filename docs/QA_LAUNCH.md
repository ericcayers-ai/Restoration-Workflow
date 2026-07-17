# QA, beta loop & graphify launch gate (ROADMAP.md Phase 9)

## Regression corpus

Synthetic degraded images live in `backend/tests/corpus/`. Generate or refresh:

```bash
cd backend
python tests/corpus/generate_corpus.py
pytest tests/test_corpus_regression.py -q
```

Run the full corpus on every release candidate before tagging. See also
[`RELEASING.md`](../RELEASING.md).

## Beta feedback loop

1. Recruit 3–5 testers (mix of non-technical Simple Mode and power-user Studio Mode).
2. Provide a desktop installer (Windows Setup / macOS DMG / Linux AppImage) or
   `restore serve` + frontend build. Do not ask testers to rely on an unfinished
   Tauri updater.
3. Collect: first-drop success, cancel responsiveness, OOM at declared VRAM tier, preset usefulness.
4. File issues for regressions; block release on critical data-loss or silent wrong-license downloads.

## Accessibility / visual QA

Before calling a UI-heavy release done:

- Run `npm run build && npm run a11y` in `frontend/` ([`ACCESSIBILITY.md`](ACCESSIBILITY.md)).
- Complete the manual checklist in that file (keyboard + one screen reader).
- Refresh `docs/screenshots/` if Simple Mode, Studio, or Settings layouts changed meaningfully.
  Until then, README may note that screenshots can lag polish.

## Graphify launch gate

Before calling the project launch-ready:

```bash
/graphify .   # full rebuild, not incremental
```

Read `GRAPH_REPORT.md` and confirm:

- No unexplained god nodes bridging frontend ↔ unrelated backend internals
- Phase 4 model nodes cluster as their own community
- Plugin SDK types are not imported from half the codebase

Unresolved surprises require an explicit note in this file or a fix before release.
