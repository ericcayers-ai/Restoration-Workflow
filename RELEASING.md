# Releasing

How to cut a Restoration Workflow release. Versioning follows SemVer for the
`0.x` line (minor bumps may include breaking pipeline-JSON changes). Current line:
**0.6.0**.

## Supported artefacts

| Artefact | How it is produced | Status |
|----------|--------------------|--------|
| `RestorationWorkflow-windows.zip` | `.github/workflows/release.yml` → PyInstaller (`backend/packaging/build_exe.py`) | **Supported** desktop install |
| Source / `pip install -e` + frontend build | documented in README | Supported for contributors |
| Docker image | `Dockerfile` on Linux release job | Headless / server; verify inference extras |
| `src-tauri/` native shell + updater endpoints | scaffold only | **Not** a shipping updater product — do not advertise auto-update |

## Pre-flight checklist

1. Version strings agree: `backend/pyproject.toml`, `backend/src/restoration/__init__.py`,
   `frontend/package.json`, and (if present) `src-tauri` metadata — keep **0.6.0** until
   you intentionally bump.
2. [`CHANGELOG.md`](CHANGELOG.md) has a dated section for the release; encoding is clean.
3. Backend: `pip install -e ".[dev]"` then `pytest -q` and `ruff check src/ tests/`.
4. Frontend: `npm ci && npm run typecheck && npm run build && npm run a11y`.
5. Manual smoke (as time allows): Simple restore, licence-gated download refuse/ack,
   Studio list editor, one Download action, Windows zip launch via `Run.bat`.
6. Docs: README install path still matches the zip layout; no lingering claims of a
   working Tauri updater.
7. [`docs/QA_LAUNCH.md`](docs/QA_LAUNCH.md) corpus / beta notes for majors.

## Tag and publish

Releases are driven by **git tags** matching `v*`:

```bash
git tag -a v0.6.0 -m "Release v0.6.0"
git push origin v0.6.0
```

The Release workflow:

1. Builds the frontend and runs backend tests.
2. On Windows: installs `[inference,packaging]`, runs PyInstaller, uploads
   `RestorationWorkflow-windows.zip`.
3. Opens / updates the GitHub Release with that zip and short Run.bat instructions.
4. On Linux/macOS: builds frontend + tests; Linux also builds the Docker image.

Do **not** force-push release tags. Do not ship a minisign / Tauri `latest.json`
updater flow unless that product decision is revisited and actually buildable in CI.

## After publish

- Spot-check the Release asset downloads and extracts cleanly.
- Confirm `Run.bat` reaches `GET /api/health` and serves the UI.
- Confirm packaged data (JSON presets / prompt libraries), `LICENSE`, and
  `NOTICE` / third-party notices are present when packaging includes them.
- If screenshots were regenerated after UI QA, commit them in a follow-up.

## Hotfix

Bump patch version, changelog entry, tag `v0.6.x`, push tag. Prefer fixing `main`
first, then tagging from the commit that contains the fix.
