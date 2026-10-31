# sharpit UI design

The single source of the console's look. Task 15b builds the views from these tokens and nothing else.

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

```css
:root {
  color-scheme: light dark;
  --bg: oklch(1 0 0); --rail: oklch(0.965 0 0); --line: oklch(0.89 0 0);
  --ink: oklch(0.22 0 0); --muted: oklch(0.48 0 0);
  --accent: oklch(0.53 0.124 60); --on-accent: oklch(1 0 0); --sel: oklch(0.95 0.03 60);
  --ok: oklch(0.50 0.12 150); --warn: oklch(0.52 0.12 75); --danger: oklch(0.52 0.18 27);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: oklch(0.17 0 0); --rail: oklch(0.205 0 0); --line: oklch(0.30 0 0);
    --ink: oklch(0.93 0 0); --muted: oklch(0.72 0 0);
    --accent: oklch(0.78 0.13 65); --on-accent: oklch(0.17 0 0); --sel: oklch(0.26 0.04 60);
    --ok: oklch(0.76 0.13 150); --warn: oklch(0.82 0.13 85); --danger: oklch(0.72 0.16 27);
  }
}
:root[data-theme="dark"] { /* same values as the dark block above */ }
```

The theme toggle sets `data-theme` on `<html>` from a module script, never from an inline one, because the CSP forbids inline
scripts.

## Type

- UI text: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`. There is one family and no web fonts: the CSP allows only
  `font-src 'self' data:`, and system fonts load instantly.
- Values: `ui-monospace, "Cascadia Mono", "SF Mono", Menlo, Consolas, monospace`. Values are config values, bean names and types,
  logger names, routes, package coordinates, CVE ids. The brief requires mono here. It is a choice about content (values are
  copied into code), not a small-label decoration, so labels stay in the UI family.
- The scale is a fixed rem scale with ratio 1.125 and a 13px base:

| Token | Size / line height | Use |
|---|---|---|
| `--t-sm` | 12px / 16px | Counts, hints, keyboard hints |
| `--t-base` | 13px / 20px | Body, table cells, rail |
| `--t-md` | 14.5px / 20px, weight 600 | Panel title |
| `--t-lg` | 16.5px / 24px, weight 600 | Palette input, empty-state lead |

- Weights are 400 and 600 only. Labels are sentence case and never uppercase. Numbers use `font-variant-numeric: tabular-nums`.

## Density and space

- Spacing uses a 4px base: `--s1` 4, `--s2` 8, `--s3` 12, `--s4` 16, `--s6` 24.
- Table rows are 28px with 8px horizontal cell padding. The header row is sticky on `--rail`.
- The rail is 208px. Rail items are 28px, and group gaps are 12px.
- The panel header is one 36px line holding the title, the filter input (which grows), and the "`37 of 412`" count in muted text.
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
quiet so the palette can carry the personality: a wide input in `--t-lg`, results grouped by kind, and the matched prefix in
`--accent`.
