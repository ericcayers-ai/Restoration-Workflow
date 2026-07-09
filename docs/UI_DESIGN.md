# UI & Product Identity — "Safelight"

This document defines the visual and interaction identity of the app. It exists to stop an
implementer (human or AI) from defaulting to the generic look every AI tool ships with today:
purple-to-blue gradients, glassmorphism cards, bouncy spring animations, rounded pill buttons,
a hero section with a marketing tagline. None of that appears here. Everything below should
feel more like a piece of darkroom equipment than a SaaS landing page.

Working codename: **Safelight**. Not a brand mandate — the repo name, package name, and
public name can stay whatever the user picks later. "Safelight" is used in this doc and
internal comments only, as a stand-in that keeps the identity coherent while building.
No logo lockup, no tagline, no marketing copy is specified here on purpose.

---

## 1. The idea the identity is built from

A darkroom is a workspace, not a showroom. The safelight (a dim red/amber lamp) exists so a
photographer can see what they're doing without ruining the print. That's the tone: a
workspace lit for focus. Structural metaphors borrowed from the darkroom — used functionally,
never as decoration:

| Darkroom concept | Maps to |
|---|---|
| Safelight | The ambient dark theme itself — dim, warm, non-glaring |
| Contact sheet | Grid view of batch jobs / run history |
| Light table | The before/after comparison surface |
| Enlarger easel | Crop / frame tool |
| Developer → Stop → Fix → Wash | The four-stage language used for auto-pipeline status text |
| Grain | A literal, sparing noise texture on large empty surfaces (never on text or controls) |

Rule of thumb: if a UI decision can't be justified by "this helps someone restore a photo
faster or with more control," it doesn't ship — including this metaphor. It's a naming and
mood device, not a theme park. No skeuomorphic film-strip borders, no fake scratches, no
sepia filters on the UI chrome itself.

**Explicitly avoid:** purple/blue gradients, glassmorphism/frosted-glass panels, drop-shadow
heavy "floating card" layouts, spring/bounce easing, emoji as UI iconography, a hero section,
upsell banners, confetti/celebration animations, rounded-pill buttons with gradient fills,
default-Inter-everything typography.

---

## 2. Color

Base surfaces are a warm near-black, never pure `#000`. Two accent colors carry all
meaning-bearing color in the UI — deliberately limited so color stays legible as signal, not
decoration.

### Dark theme (default)

| Token | Hex | Role |
|---|---|---|
| `--surface-950` | `#14120F` | App background |
| `--surface-900` | `#1B1815` | Panel background (sidebars, inspector) |
| `--surface-800` | `#242019` | Raised surface (cards, node bodies) |
| `--surface-700` | `#322C22` | Hover / active raised surface |
| `--border-hairline` | `#3A3327` | 1px borders — always hairline, never a shadow |
| `--text-primary` | `#F2EDE4` | Primary text — warm off-white |
| `--text-secondary` | `#B8AF9E` | Secondary / muted text |
| `--accent-amber` | `#E8873A` | Primary accent — active states, primary actions, focus ring, progress |
| `--accent-teal` | `#4FA79A` | Secondary accent — success/complete, used sparingly for contrast against amber |
| `--accent-brick` | `#C1523F` | Error/warning — desaturated, not a screaming red |

**Verified contrast** (WCAG relative-luminance formula, computed against `--surface-950`):
- `--text-primary` on `--surface-950`: **16.0:1** (AAA)
- `--text-secondary` on `--surface-950`: **8.6:1** (AAA)
- `--accent-amber` on `--surface-950`: **7.1:1** (AAA for normal text)
- `--accent-teal` on `--surface-950`: **6.5:1** (AA, near-AAA)

All four pass WCAG AA (4.5:1) for normal text without any adjustment. Re-verify with a
contrast checker (e.g. the `wcag-contrast` npm package) as part of CI once components exist —
don't take this table's word for it forever, treat it as the starting point.

### Light theme

| Token | Hex | Role |
|---|---|---|
| `--surface-950` | `#F7F3EA` | App background — warm paper white, not `#FFF` |
| `--surface-900` | `#EFE9DB` | Panel background |
| `--surface-800` | `#E5DDC9` | Raised surface |
| `--text-primary` | `#2B2620` | Ink-brown, not pure black |
| `--text-secondary` | `#665D4E` | Muted |
| `--accent-amber` | `#B85F19` | Deepened for contrast on light surface |
| `--accent-teal` | `#2E7A6E` | Deepened for contrast on light surface |
| `--accent-brick` | `#9E3A28` | Deepened for contrast on light surface |

Both themes are first-class, not a dark-mode-first afterthought — see Accessibility §6.
A **high-contrast mode** (pure black/white text, thicker hairlines, no texture) is a third
theme variant, not a toggle buried in an OS setting — expose it directly in-app.

Category color-coding (model stack categories in Studio Mode) uses a small fixed set of hues
distinct from the two accents, always paired with an icon shape — never color alone (see §6).

---

## 3. Typography

Two families, each doing one job:

- **UI chrome / headers** — a humanist grotesque sans with actual character, not the default
  "safe" choice. Recommendation: **Public Sans** or **IBM Plex Sans** (both open-license,
  self-hostable, avoid the "every AI app uses Inter" sameness). Weight range 400–600 only;
  no black/900 weights — restraint over impact.
- **Technical readouts** — a monospace for anything numeric or machine-precise: model names,
  file sizes, resolution, VRAM estimates, parameter values, timestamps. Recommendation:
  **IBM Plex Mono** or **JetBrains Mono**. This is what gives the UI its "lab equipment"
  precision instead of reading as a generic content app — numbers and identifiers visually
  announce themselves as data, not prose.

Type scale is modest and mostly static — 13/14px body, 12px mono metadata, headers topping
out around 20–24px. No 48px hero headline anywhere in the product; this is a tool, not a
landing page.

---

## 4. Iconography

A single custom line-icon set, 1.5px stroke, unfilled, ~24px grid. Start from **Phosphor
Icons** (open license) as a structural base but restyle stroke weight and corner treatment
so it doesn't read as the same icon set every other app ships — a slightly less mechanically
uniform corner radius reads as intentional rather than templated. Core icon vocabulary:
aperture (analysis/auto mode), contact-sheet grid (batch/history), loupe (inspect/zoom),
tray (queue/processing), splice (node connection), dial (parameter/manual control).

Never use emoji as functional UI (status icons, buttons, empty states). Emoji in this context
reads as unpolished and undermines the "not vibecoded" goal.

---

## 5. Motion

Photographic, not playful. Two rules cover almost everything:

1. **Dissolve, don't bounce.** Transitions are opacity/crossfade based, 180–260ms,
   `ease-out`. No spring/elastic easing anywhere — that's the signature motion language of
   generic AI-app UI kits and it undercuts the tool-not-toy tone.
2. **Progress reads as development, not loading.** A pipeline node's progress fill moves at a
   steady, slightly non-linear rate (like a print emerging in a tray) rather than an
   indeterminate spinner. Node connection edges "develop" in with an opacity ramp instead of
   snapping fully-opaque the instant a connection is made.

`prefers-reduced-motion: reduce` disables all non-essential transitions — the app must be
fully legible and operable with motion off (crossfades become instant swaps; the progress
fill becomes a plain percentage + numeric readout, since numeric feedback already exists in
the technical-readout mono font and isn't lost by turning animation off).

---

## 6. Accessibility (non-negotiable, not a later pass)

- **Contrast:** WCAG AA minimum everywhere; see verified ratios in §2. Re-check any new color
  pairing before it ships.
- **Keyboard:** the node canvas must be fully operable without a mouse — Tab cycles between
  nodes, arrow keys nudge a selected node, Enter opens the Inspector for the focused node,
  a command palette (`Cmd/Ctrl+K`) reaches every action a menu would. No feature may be
  mouse-only.
- **Screen reader:** the pipeline execution state is exposed via an ARIA live region with
  plain-language status ("Removing noise — step 2 of 4"), not just a visual progress bar.
  Every node has an accessible name combining category + model name + status.
- **Color independence:** category color-coding in the Model Stack and on canvas nodes is
  always paired with a distinct icon shape, so a colorblind user (or grayscale screenshot)
  never loses information.
- **Motion:** `prefers-reduced-motion` honored globally, see §5.
- **Scale:** an in-app UI-scale control (not just reliance on OS/browser zoom) since photo
  work happens across very different monitor setups and DPI.
- **Localization-readiness:** no text baked into images/icons; all UI strings routed through
  a message-catalog layer from the start even though only English ships initially (see
  Roadmap Phase 7) — retrofitting i18n after the fact is far more expensive than reserving
  the seam now.

---

## 7. Simple Mode (drag-and-drop, instant automation)

This is the first thing a new user sees and the literal MVP deliverable (Roadmap Phase 2).

**Layout:** a single full-bleed drop target, centered, minimal chrome. Copy reads "Drop a
photo" — plain, not "Unleash the power of AI-driven restoration." Below the fold, nothing —
no feature grid, no testimonials, no pricing. This is a tool opening to its own workspace,
not a landing page.

**Flow:**
1. User drops (or clicks to browse for) an image.
2. A quiet text status line runs the degradation-analysis pass: `Analyzing — checking noise,
   sharpness, faces, exposure…` (mono font, small, not a giant animated ring).
3. Once the auto-analyzer (see `ARCHITECTURE.md` §4) picks a pipeline, status updates to
   named stages using the darkroom stage language: `Developing → Fixing → Washing → Done`
   mapped under the hood to whatever real node chain was selected — so the user always has a
   legible mental model even with zero technical knowledge of which models ran.
4. Result appears on a **light-table**: the restored image sits on a neutral warm-gray mat
   with a draggable vertical divider revealing before/after. A secondary toggle offers
   side-by-side and (for the curious) a difference-heatmap view.
5. Actions below the light table, plain text buttons not gradient pills: `Save`, `Compare`,
   `Open in Studio` (hands the exact auto-picked pipeline off to Studio Mode for tweaking —
   see §8), `Export`.

No configuration is required to reach step 4. Every parameter the auto-analyzer chose is
still inspectable (via "Open in Studio") but never blocks the default path.

---

## 8. Studio Mode (full node canvas, full customizability)

**Layout — four regions:**

- **Left rail — Model Stack.** Searchable, grouped by the five categories already established
  in the README's own taxonomy: Generative & Diffusion, Face Restoration, Regression &
  All-in-One, Masking & Inpainting, Orchestration. Each entry shows name (mono font),
  category color tab, and a VRAM-tier badge (see `ARCHITECTURE.md` §5) so a node the user's
  hardware can't run is visibly greyed rather than silently failing later.
- **Center — Canvas.** The DAG editor. Nodes are rectangular cards with a hairline border
  (no drop shadows), a colored category tab on the left edge, model name in mono, a small
  live thumbnail once the node has executed, and a one-line parameter summary. Connections
  "develop" in per §5.
- **Right rail — Inspector.** Contextual parameter form for the selected node, generated from
  that node's `param_schema` (see `ARCHITECTURE.md` §3) — sliders/selects/toggles, never a
  bare JSON blob.
- **Bottom strip — Contact sheet.** A thumbnail history of runs on the current image (or
  batch), literally a contact-sheet grid, click to recall any prior result or fork a new
  pipeline from it.

**Customizability surface exposed here:** save/load pipelines as named presets, export/import
pipeline JSON, per-node parameter overrides, batch/folder execution, branch/merge in the DAG
(not just a linear chain — e.g. run two face-restoration models on the same crop and blend),
and adding third-party plugin nodes without touching core code (`ARCHITECTURE.md` §6).

---

## 9. Design tokens (starting point for implementation)

```css
:root[data-theme="dark"] {
  --surface-950: #14120F;
  --surface-900: #1B1815;
  --surface-800: #242019;
  --surface-700: #322C22;
  --border-hairline: #3A3327;
  --text-primary: #F2EDE4;
  --text-secondary: #B8AF9E;
  --accent-amber: #E8873A;
  --accent-teal: #4FA79A;
  --accent-brick: #C1523F;
  --font-ui: "Public Sans", "IBM Plex Sans", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", "JetBrains Mono", ui-monospace, monospace;
  --motion-fast: 180ms ease-out;
  --motion-base: 260ms ease-out;
}

:root[data-theme="light"] {
  --surface-950: #F7F3EA;
  --surface-900: #EFE9DB;
  --surface-800: #E5DDC9;
  --border-hairline: #D8CDB4;
  --text-primary: #2B2620;
  --text-secondary: #665D4E;
  --accent-amber: #B85F19;
  --accent-teal: #2E7A6E;
  --accent-brick: #9E3A28;
}

@media (prefers-reduced-motion: reduce) {
  :root { --motion-fast: 0ms; --motion-base: 0ms; }
}
```

These are a starting point, not gospel — Phase 3 (Studio Mode build) should treat this block
as the seed for a proper Tailwind theme config, and extend the category color set for the
five model-stack categories at that point.
