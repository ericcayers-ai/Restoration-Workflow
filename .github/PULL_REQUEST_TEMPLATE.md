## What does this change and why?

<!-- The "why" matters more than the "what" — the diff already shows what changed. -->

## Checklist

- [ ] `pytest -q` and `ruff check src/ tests/` pass in `backend/` (or CI will show it)
- [ ] `npm run typecheck` and `npm run build` pass in `frontend/` (or CI will show it)
- [ ] If UI-facing: `npm run a11y` considered / run after build; strings go through `en.json`
- [ ] If this changes `core/data/rule_table.json`, routing tests in `tests/test_rules.py` match
- [ ] If this adds a model, licence and weight source were verified directly — see
      `docs/MODEL_STACK.md` and `CONTRIBUTING.md`
- [ ] If this touches weight loading (`nodes/_torch.py`), checkpoints are still never
      unpickled — see `SECURITY.md`
- [ ] User-visible behaviour: `CHANGELOG.md` updated (Keep a Changelog)
- [ ] Docs do not claim a shipping Tauri auto-updater (desktop installers are the
      supported path — `RELEASING.md`)

## Testing

<!-- How did you verify this? Failing→passing test, manual repro steps, screenshot for UI. -->
