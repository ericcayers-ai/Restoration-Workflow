# Accessibility verification (ROADMAP.md Phase 7)

This document records the accessibility bar for Restoration Workflow and how it is verified in CI and manually.

## Automated checks (CI)

- **axe-core** runs against the production frontend build after `npm run build`.
- The job fails on any **critical** or **serious** violation in Simple Mode and Studio Mode shells.
- Run locally: `npm run a11y` from `frontend/`.

## Manual pass (required before release)

Perform once per major release with:

| Tool | Scope |
|------|--------|
| **NVDA** (Windows) or **VoiceOver** (macOS) | Full Simple Mode drop → restore → save flow; Studio Mode add stage → run |
| **Keyboard only** | Command palette (Ctrl/Cmd+K), drop zone (Enter/Space), theme toggle, all primary actions |

### Checklist

- [ ] Drop zone announces status via `aria-live` during analysis and processing
- [ ] Light table slider is keyboard-operable
- [ ] Studio canvas nodes are focusable; inspector form fields have associated labels
- [ ] High-contrast theme meets 4.5:1 body text contrast (UI_DESIGN.md section 6)
- [ ] No information conveyed by color alone in the model stack rail (icons + labels)

Record the date and tester initials in the release checklist when complete.

## i18n seam

All user-visible strings flow through `frontend/src/locales/en.json` via `useT()`. Additional locales are additive JSON files; English ships at launch.
