# QA, beta loop & graphify launch gate (ROADMAP.md Phase 9)

## Regression corpus

Synthetic degraded images live in `tests/corpus/`. Generate or refresh:

```bash
cd backend
python ../tests/corpus/generate_corpus.py
pytest tests/test_corpus_regression.py -q
```

Run the full corpus on every release candidate before tagging.

## Beta feedback loop

1. Recruit 3–5 testers (mix of non-technical Simple Mode and power-user Studio Mode).
2. Provide the portable Windows build or `restore serve` + frontend build.
3. Collect: first-drop success, cancel responsiveness, OOM at declared VRAM tier, preset usefulness.
4. File issues for regressions; block release on critical data-loss or silent wrong-license downloads.

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
