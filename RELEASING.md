# Releasing

How to cut a Restoration Workflow release. Versioning follows SemVer for the
`0.x` line (minor bumps may include breaking pipeline-JSON changes). Current line:
**0.6.1**.

## Supported artefacts

| Artefact | How it is produced | Status |
|----------|--------------------|--------|
| `RestorationWorkflow-Setup-*-windows-x64.exe` | Release CI → PyInstaller + Inno Setup | **Supported** Windows install |
| `RestorationWorkflow-*-macos-*.dmg` | Release CI → PyInstaller + `.app` + `hdiutil` | **Supported** macOS (unsigned) |
| `RestorationWorkflow-*-linux-*.AppImage` | Release CI → PyInstaller + appimagetool | **Supported** Linux |
| Source / `pip install -e` + frontend build | documented in README | Supported for contributors |
| Docker image | `Dockerfile` on Linux release job | Headless / server; verify inference extras |
| `src-tauri/` native shell + updater endpoints | scaffold only | **Not** a shipping updater product — do not advertise auto-update |

## Pre-flight checklist

1. Version strings agree: `backend/pyproject.toml`, `backend/src/restoration/__init__.py`,
   `frontend/package.json`, `backend/packaging/bundle_common.py` (`APP_VERSION`), and
   (if present) `src-tauri` metadata — keep **0.6.1** until you intentionally bump.
2. [`CHANGELOG.md`](CHANGELOG.md) has a dated section for the release; encoding is clean.
3. Backend: `pip install -e ".[dev]"` then `pytest -q` and `ruff check src/ tests/`.
4. Frontend: `npm ci && npm run typecheck && npm run build && npm run a11y`.
5. Manual smoke (as time allows): Simple restore, licence-gated download refuse/ack,
   Studio list editor, one Download action, Windows Setup launch, macOS DMG first-open,
   Linux AppImage execute bit.
6. Docs: README install path still matches installer asset names; no lingering claims of a
   working Tauri updater.
7. [`docs/QA_LAUNCH.md`](docs/QA_LAUNCH.md) corpus / beta notes for majors.

## Tag and publish

Releases are driven by **git tags** matching `v*`:

```bash
git tag -a v0.6.1 -m "Release v0.6.1"
git push origin v0.6.1
```

The Release workflow:

1. Builds the frontend and runs backend tests on Windows, macOS, and Linux.
2. On each OS: installs `[inference,packaging]`, runs PyInstaller, then wraps the
   onedir into the platform installer (Inno Setup / DMG / AppImage).
3. A `publish` job attaches all three installers to the GitHub Release and removes
   any legacy `RestorationWorkflow-windows.zip` asset.
4. Linux also builds and smoke-tests the Docker image.

### Rebuild installers onto an existing tag (no version bump)

Use **workflow_dispatch** on the Release workflow (Actions → Release → Run workflow)
with `tag` set to e.g. `v0.6.1`. That rebuilds installers from the current default
branch commit and uploads them to the existing release — useful for packaging fixes
without cutting `v0.6.2`.

Do **not** force-push release tags. Do not ship a minisign / Tauri `latest.json`
updater flow unless that product decision is revisited and actually buildable in CI.

## After publish

- Spot-check each Release asset downloads and launches (or installs) cleanly.
- Confirm the UI reaches `GET /api/health` after launch.
- Confirm packaged data (JSON presets / prompt libraries), `LICENSE`, and
  `NOTICE` / third-party notices are present in the installed tree.
- Confirm legacy zip is gone from the release asset list.
- If screenshots were regenerated after UI QA, commit them in a follow-up.

## Hotfix

Bump patch version, changelog entry, tag `v0.6.x`, push tag. Prefer fixing `main`
first, then tagging from the commit that contains the fix.
