## What does this change and why?

<!-- The "why" matters more than the "what" — the diff already shows what changed. -->

## Checklist

- [ ] `pytest` and `ruff check src/ tests/` pass in `backend/` (or CI will show it)
- [ ] `npm run typecheck` and `npm run build` pass in `frontend/` (or CI will show it)
- [ ] If this changes `core/data/rule_table.json` (the default auto-pipeline), the
      routing assertions in `tests/test_rules.py` were updated to match
- [ ] If this adds a model, its license and weight source were verified directly (not
      taken from a paper's README) — see `docs/MODEL_STACK.md` and `CONTRIBUTING.md`
- [ ] If this touches weight loading (`nodes/_torch.py`), it still never unpickles a
      checkpoint — see `SECURITY.md`

## Testing

<!-- How did you verify this works? A failing test that now passes, a manual repro
     steps list, a screenshot/recording for UI changes — whatever actually proves it. -->
