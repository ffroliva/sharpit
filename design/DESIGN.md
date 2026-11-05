# sharpit UI design

The single source of the console's look. The views are built from these tokens and nothing else.

## Who and where

A Python developer in the middle of debugging. An editor sits on one half of the screen, and sharpit runs in a browser tab on the
other half or behind the editor. They glance at it between runs: which config source won, which logger is chatty, what depends on
this bean. It is often late in the day, and the editor is often dark. So both themes exist and the console follows
`prefers-color-scheme` by default. Sessions are short and the user's hands stay on the keyboard.

Register: product (the design serves the task). Strategy: **restrained**. Pure neutrals, one accent on at most about 10% of
the surface.

## What it must not look like (BootUI)

The owner rejected BootUI's look, so sharpit avoids all of it.

| BootUI | sharpit instead |
|---|---|
| Bootstrap blues (`#0a53be`, `#000080`, `#8fb7ff`), neon cyan/magenta (`#00e5ff`, `#ff2df7`), cool blue-grey borders (`#d7dce2`) | One ochre accent (hue 60) and chroma-0 neutrals. No blue anywhere. |
| Five switchable skins (graphite, minimal, cyberpunk, DSFR, Win95) | Two themes only: light and dark, from one token set. |
| Topbar with title, subtitle and lead heading over every panel | No topbar. Each panel has a single 36px header line: title, filter, counts. |
| `nav-pills` sidebar with a Bootstrap icon per entry and a collapse chevron | A text-only rail with no icons. The current panel gets a 1px accent outline and a tinted fill. |
| Cards on the overview | No cards. Content sits flush in tables and definition lists, separated by hairlines. |

## Colour tokens (OKLCH)

All text pairs were measured with WCAG 2 relative luminance. "rail" is the second neutral layer and "sel" is the
selected-row tint.

| Token | Light | Dark | Role | Contrast (bg / rail / sel), light · dark |
|---|---|---|---|---|
| `--bg` | `oklch(1 0 0)` | `oklch(0.17 0 0)` | Content surface | — |
| `--rail` | `oklch(0.965 0 0)` | `oklch(0.205 0 0)` | Rail, table header, palette | — |
| `--line` | `oklch(0.89 0 0)` | `oklch(0.30 0 0)` | Hairlines and borders (never text) | 1.39 · 1.40 vs bg |
| `--ink` | `oklch(0.22 0 0)` | `oklch(0.93 0 0)` | Body text and values | 17.3/15.6/14.9 · 15.6/14.6/12.7 |
| `--muted` | `oklch(0.48 0 0)` | `oklch(0.72 0 0)` | Labels, counts, secondary text, placeholders | 6.5/5.9/5.6 · 7.7/7.2/6.3 |
| `--accent` | `oklch(0.53 0.124 60)` | `oklch(0.78 0.13 65)` | Focus ring, current selection, primary action, links | 5.5/5.0/4.7 · 9.3/8.7/7.6 |
| `--on-accent` | `oklch(1 0 0)` | `oklch(0.17 0 0)` | Text on a filled accent control | 5.49 · 9.30 |
| `--sel` | `oklch(0.95 0.03 60)` | `oklch(0.26 0.04 60)` | Selected row or rail item fill | — |
| `--ok` | `oklch(0.50 0.12 150)` | `oklch(0.76 0.13 150)` | UP, scan clean | 5.7/5.1/4.9 · 9.4/8.8/7.7 |
| `--warn` | `oklch(0.52 0.12 75)` | `oklch(0.82 0.13 85)` | Read-only, masked, medium severity | 5.6/5.1/4.8 · 10.9/10.2/8.9 |
| `--danger` | `oklch(0.52 0.18 27)` | `oklch(0.72 0.16 27)` | DOWN, failed, high/critical | 6.0/5.5/5.2 · 7.2/6.7/5.9 |

Rules:
- Every text/background pair above passes 4.5:1. There is no lighter "faint" grey. `--muted` is the floor, including for
  placeholders and disabled labels, where disabled is shown by the `not-allowed` cursor plus a reason, never by low contrast.
- A status never relies on colour alone. It always carries its word (`UP`, `masked`, `read-only`, `HIGH`).
- Status colours appear only as text or as a 1px outline. Filled badges are reserved for the accent, so the one filled thing on a
  screen is the primary action.
- The accent never decorates: it marks focus, selection, the primary action, and links.

The values live in [`tokens.css`](tokens.css), the one source. This table documents them, and `tests/design` fails if the
two disagree.

The theme toggle sets `data-theme` on `<html>` from a module script, never from an inline one, because the CSP forbids inline
scripts.

## Other tokens

The rest of `tokens.css`. Names are the same on every surface.

| Token | Value | Role |
|---|---|---|
| `--ui` | `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` | UI text family |
| `--mono` | `ui-monospace, "Cascadia Mono", "SF Mono", Menlo, Consolas, monospace` | Values: config, beans, loggers, routes, CVE ids |
| `--s1` | `4px` | Space step 1 |
| `--s2` | `8px` | Space step 2 |
| `--s3` | `12px` | Space step 3 |
| `--s4` | `16px` | Space step 4 |
| `--s6` | `24px` | Space step 6 |
| `--row` | `28px` | Table and rail row height |
| `--head` | `36px` | Panel header height |
| `--rail-w` | `208px` | Rail width |
| `--radius` | `4px` | Inputs, buttons, palette |
| `--ease` | `cubic-bezier(0.25, 1, 0.5, 1)` | Easing for the only two transitions |
| `--dur` | `150ms` (`0ms` under reduced motion) | Transition duration |
| `--z-sticky` | `10` | Sticky table header |
| `--z-palette` | `100` | Command palette |

## Spacing and type rules

These apply on every surface unless a surface says otherwise.

- **Spacing:** `--s` tokens only. Exceptions: 1 to 3px optical offsets, each with a comment.
- **Containers:** left padding equals right, top equals bottom.
- **Headings:** space above is at least twice the space below. Console 12 and 4, slides 36 and 12, docs keep Material's 40 and 16.
- **Levels:** one h1 per panel or page, then h2. Levels are never skipped, and the console uses h1 and h2 only.
- **Weights:** 400 and 600, on every surface.
- **Slides:** spacing is the console's x3. Type is four steps of its own, with no text under 34px, so it stays at 12px or more at phone width.
- **Touch targets:** at least 24px, the WCAG 2.2 AA minimum. 44px does not apply to this dense desktop tool.
- **Numbers:** right aligned, tabular. Status words left aligned.

## Type

- UI text: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`. There is one family and no web fonts: the CSP allows only
  `font-src 'self' data:`, and system fonts load instantly.
- Values: `ui-monospace, "Cascadia Mono", "SF Mono", Menlo, Consolas, monospace`. Values are config values, bean names and types,
  logger names, routes, package coordinates, CVE ids. The brief requires mono here. It is a choice about content (values are
  copied into code), not a small-label decoration, so labels stay in the UI family.
- The sizes are a fixed set of plain sizes, not tokens: nothing in `ui/src` defines a `--t-*` variable. They are not a
  ratio scale.

| Name | Size / line height | Use |
|---|---|---|
| sm | 12px / 16px | Counts, hints, keyboard hints |
| base | 13px / 20px | Body, table cells, rail |
| md | 14.5px / 20px, weight 600 | Panel title |
| lg | 16.5px / 24px, weight 600 | Palette input, empty-state lead |
| metric | 20px / 24px | One large number per panel |
| mono | 12.5px | Values in `--mono` |
| graph | 11px | Graph labels |

- Weights are 400 and 600 only. Labels are sentence case and never uppercase. A label matching BootUI's contract text stays verbatim for compatibility. Numbers use `font-variant-numeric: tabular-nums`.

## Density and space

- Spacing uses a 4px base: `--s1` 4, `--s2` 8, `--s3` 12, `--s4` 16, `--s6` 24.
- Table rows are 28px with 8px horizontal cell padding. The header row is sticky on `--rail`.
- The rail is 208px. Rail items are 28px, and group gaps are 12px.
- The panel header is one 36px line holding the title, the filter input (which grows), and the "`37 of 412`" count in muted text.
- Run `npm run e2e:layout` by hand before UI changes merge.
- Radius is 4px on inputs, buttons and the palette, and 0 on tables and the rail. Hierarchy comes from surfaces, not from
  rounding everything.
- Shadows appear only on the command palette (one layer, `0 8px 24px oklch(0 0 0 / 0.18)`). Nothing else floats.

## Layout

```
+-----------+-----------------------------------------------+
| sharpit   | Config      [filter........]      37 of 412   |
|           |-----------------------------------------------|
| Overview  | name             value          source        |
| Health    | APP_ENV          dev            .env  *won    |
| Config  < | DATABASE_URL     ******  masked environ       |
| Loggers   | ...                                           |
| Beans     |                                               |
| Routes    |                                               |
| ---       |                                               |
| Metrics   |                                               |
|  disabled |                                               |
| [Ctrl K]  |                                               |
+-----------+-----------------------------------------------+
```

- Everything is left aligned. Numbers in tables are right aligned.
- Unavailable and read-only panels stay in the rail, in `--muted`, with their reason shown inline beneath them. They are never
  hidden.
- Below 720px the rail becomes a single row that scrolls horizontally above the panel. There is no hamburger menu.

## Runtime panels (0.2.0)

New pieces only; everything else reuses the tokens and patterns above.

- **Rail groups.** `lib/nav.ts` sorts the rail into Overview, Runtime, Database, Configuration and Advisors. A group title is a
  12px `--muted` line, not a heading and not clickable. A panel the server calls "Not built yet" is hidden; every
  other unavailable panel keeps its reason (see Layout). Below 720px the group titles are dropped with the rest of the chrome.
- **PanelShell.** One header line (title, controls, then a right-aligned muted count) over a scroll region. Its three states are fixed:
  loading is one muted "Loading…" line, error is a `--danger` lead with the server's text and a Retry button, and a read-only panel
  gets a `--warn` notice with the reason. Actions stay visible, are `disabled`, and carry the reason as their `title`.
- **Live panels** (Activity, Exceptions, HTTP Exchanges, Log Tail) show no connection badge: a planned stream rotation is
  invisible. Only a refused stream (`error`) shows a `--danger` notice, and it clears itself when the stream is back.
- **Log lines.** Monospace, one per row, wrapped. ERROR and above in `--danger`, WARNING in `--warn`, DEBUG in `--muted`. The level
  is also written as a word. Auto-follow stops on Pause.
- **Stack frames.** An ordered list in `--muted`; the application's own frames are `--ink` at weight 600. Frames are plain text.
- **Status chips.** The `.tag` outline in the status colour with its word (`UP`, `DOWN`, `OPEN`, `slow`). An HTTP status is a
  coloured number: 2xx `--ok`, 3xx `--muted`, 4xx `--warn`, 5xx `--danger`.
- **Expandable rows.** A `Details` link button (`aria-expanded`) opens a `--rail` row under the line. Nothing animates.
- **Probe.** Method select, path input (mono, with a route datalist), two mono textareas for headers and body, and one primary
  `Send` button. The response is a status line, the allow-listed headers, then the body in a wrapped `<pre>` on `--rail`.
  Headers and bodies are never stored; history keeps method and path.
- Every captured value is text. No view uses `{@html}` (`tests/test_ui_no_html.py`).

## States and motion

- Focus is a 2px `--accent` outline with a 1px offset on every interactive element, and it is never removed.
- Hover is a `--sel` fill on rows and rail items only.
- Loading shows the skeleton rows of the table in `--rail`. There are no centre spinners.
- Empty states say what to type or do next, for example: "No loggers match `sqlalch`. Clear the filter."
- Busy (409) shows the server's message inline next to the action, in `--warn`.
- Motion: 150ms `cubic-bezier(0.25, 1, 0.5, 1)` on the palette open and on row hover fills, nothing else. Under
  `prefers-reduced-motion: reduce`, durations are 0.

## The one memorable thing

The command palette (Ctrl/Cmd+K). It is the fastest way to reach any panel, logger or config key. The rest of the console stays
quiet so the palette can carry the personality: a wide 16.5px input, results grouped by kind, and the matched prefix in
`--accent`.

## Launch and social

Slides use the 1080×1350 format with 72px margins. Each slide has one wordmark line: `sharpit` at left and its position or
version at right. The cover opens with a real hook; each slide carries one idea, centred vertically. The template links
`../tokens.css` before `slide.css`, pins the dark theme on `<html>`, and exports dark.

`slide.css` contains no colour tokens. It scales spacing to `--s2` 24px, `--s3` 36px, `--s4` 48px and `--s6` 72px; type
steps are `--t-sm` 34px, `--t-base` 42px, `--t-lg` 84px and `--t-xl` 112px. Text never drops below 34px. The fit script
uses `document.documentElement.clientWidth`.

Cards are banned. A slide may show one `.cmd`, and the kit permits only the `.hit` finding and `.code` output blocks. Use
real commands, findings and screenshots with fake secrets. Claims trace to a Facts block in the campaign file; images have
alt text. Credit BootUI by Julien Dubois on launch material. Campaigns copy the `design/` folder, keeping its layout,
into a dated snapshot and record the source commit; later token changes do not rewrite published decks.

## Brand

- **One line:** “sharpit is a local developer console and pytest gate for FastAPI apps, a Python port of BootUI by Julien
  Dubois.” Use it or a shorter form in README, docs, PyPI and GitHub descriptions.
- **Name:** `sharpit`, always lower case, including at the start of a sentence.
- **Wordmark:** the word in `--ui` at weight 600. There is no logo.
- **Versions:** `0.5.0` in prose; `v0.5.0` for tags and launch headlines.
- **Credit:** “a Python port of BootUI by Julien Dubois” on the README, docs footer and launch material; include Apache-2.0
  where licences are listed.
- **Status:** alpha appears on launch material until the owner changes it.

## Principles

- **Three pillars:** in your tests, in your app, in CI.
- **Glossary:** console, panel, advisor (scans code or app), gate (fails a test or build), finding.
- **Personality:** precise, candid, quiet.
- **Voice:** give numbers their scope (“22 of 31 verified”, not “full parity”); distinguish verified from built; state limits
  as plainly as strengths; make no unsupported claims; use no hype or AI attribution.

## Docs site

The MkDocs site keeps Material's layout and syntax highlighting while using the shared `tokens.css` copy in
`website/docs/stylesheets/`. `sharpit.css` maps Material's header and tab surfaces to `--rail`, page surfaces to `--bg`,
text to `--ink` or `--muted`, and links, focus and active navigation to `--accent`. The header has a 1px `--line` bottom
edge, table headers use `--rail`, and admonitions use status-token 1px outlines. Palette headings use weights 400 and 600.
All mappings live under `[data-md-color-scheme]`, so the user's palette toggle controls the tokens even when it differs
from the operating system theme.
