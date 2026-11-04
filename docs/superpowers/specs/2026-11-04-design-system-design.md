# sharpit design system

Status: draft for the owner's review, 2026-11-04. Nothing is built.

The owner chose the home (the sharpit repo) and the scope (console, docs site, launch and social, brand basics). The owner
skipped the questions, so every other decision here is the author's call. They are listed in "Calls to check" at the end.

## Why

sharpit's look exists in three places that nothing keeps in step:

| Surface | Today | Problem |
|---|---|---|
| Console | `ui/DESIGN.md` and a hand-kept copy of its tokens in `ui/src/app.css` | The file's first line says "keep the two in step". Nothing checks that |
| Docs site | Material for MkDocs with `primary: teal`, `accent: teal` | A second accent. `ui/DESIGN.md` allows one, ochre |
| Launch deck | A third copy of the tokens in `social-publisher/media/sharpit-v0.5.0/` | Gitignored, in another repo, invisible to CI |

A reader who meets sharpit on LinkedIn, then the docs, then the console should see one product.

## Goals

- One file holds the tokens. One document holds the rules.
- The console, the docs site and promo slides read those tokens.
- A check fails when a surface drifts or a colour pair drops below WCAG AA.
- Brand basics are written down: name, wordmark, voice, credit to BootUI.
- The console looks identical after the move.

## Non-goals

- A logo or favicon. There is none today and none is designed here.
- A component library. Svelte components stay in `ui/src/components/`.
- A published package. This is two files in the repo.
- A console redesign or new tokens the surfaces do not need.
- Syntax highlighting colours on the docs site. Material's stay.

## Anti-goals

This fails, even if every check passes, when:

- the console changes visually, or its CSP or build gets weaker;
- sharpit gains a runtime dependency or a web font;
- the system adds decoration: a second accent, cards, filled status badges, uppercase labels;
- it starts to look like BootUI, whose look the owner rejected (table in `ui/DESIGN.md`);
- it delays the 0.5.0 release.

## Constraints

- Runtime dependencies stay exactly `starlette` and `packaging`. `design/` is not in the wheel; the built CSS is.
- The console's CSP allows `font-src 'self' data:` and no inline script, so there are no web fonts. The docs already set
  `font: false`, and slides use the same system stacks.
- The built UI in `src/sharpit/ui/static/` is committed, and CI checks it matches `ui/`, so any token move needs a rebuild.
- Work happens in a worktree from current `origin/main`, after the v0.5.0 tag. On 2026-11-04 `ui/DESIGN.md`, `ui/src/app.css`
  and `website/mkdocs.yml` were identical on `release/0.5.0` and `origin/main`, so no conflict is expected.

## Structure

```
design/
  DESIGN.md        the rules, moved from ui/DESIGN.md and extended
  tokens.css       the tokens, the single source
  social/
    slide.css      the console's patterns scaled for a 1080 px slide
    template.html  a two-slide starter
website/docs/stylesheets/
  tokens.css       a byte-identical copy (MkDocs serves only docs_dir)
  sharpit.css      maps tokens onto Material's variables
tests/design/
  test_tokens.py   the checks below
```

`design/DESIGN.md` has one section per concern: principles, tokens, console (today's content, kept), docs site, social, brand.

## Tokens

`tokens.css` takes today's token blocks from `ui/src/app.css` unchanged: the same names, the same values, the same light and
dark themes. Names stay, so no component changes.

| Group | Tokens |
|---|---|
| Colour | `--bg --rail --line --ink --muted --accent --on-accent --sel --ok --warn --danger` |
| Type | `--ui --mono` |
| Space and shape | `--s1 --s2 --s3 --s4 --s6 --row --head --rail-w --radius` |
| Motion and layers | `--ease --dur --z-sticky --z-palette` |

`--t-sm`, `--t-base`, `--t-md` and `--t-lg` are not tokens: nothing in `ui/src` defines them, and `app.css` uses literal px. In
`design/DESIGN.md` the type table lists them as plain sizes. `slide.css` defines its own `--t-*` and `--hair` at slide scale.

One addition: the theme selectors also match Material's scheme, because Material sets `data-md-color-scheme` on `<body>`
rather than `data-theme` on `<html>`:

```css
:root, [data-md-color-scheme="default"] { /* light values */ }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { /* dark values */ } }
:root[data-theme="light"] { color-scheme: light; }
:root[data-theme="dark"], [data-md-color-scheme="slate"] { /* dark values */ }
```

All of today's theme blocks stay, including the OS-theme media query, so the console still follows the OS setting. Only the two
Material selectors are new.

The selector on `<body>` beats the inherited `:root` value, so the docs' toggle wins over the OS setting. The builder confirms
this in a browser with all four combinations of OS theme and toggle. The selectors match nothing in the console.

## Surfaces

### Console

`ui/src/app.css` starts with `@import '../../design/tokens.css';` and loses its token blocks. Everything else stays. Rebuild
`src/sharpit/ui/static/`.

Four colour literals exist in `ui/src` outside `app.css`. The builder moves each to a token or records why it stays.

Proof of no visual change, as a one-off in the PR rather than a lasting CI gate:

- At the same commit, run the Playwright suites with `SHOTS=1` before and after the move, in both themes, into a temporary
  folder, and compare the two sets. Nothing compares them today, so the PR adds a small compare script. It masks live values such
  as clock times, request rates and temp paths (for example on `activity` and `health`).
- Diff the built CSS as well: only the source order of the token blocks may change, and the resolved values may not.

The committed PNGs under `ui/tests/e2e/screenshots/` stay untouched. They are the 0.4.0 catalog, so they are not a valid baseline,
and refreshing them is a separate change.

### Docs site

In `website/mkdocs.yml`, both palette entries use `primary: custom` and `accent: custom`, and `extra_css` lists the two
stylesheets. `sharpit.css` maps tokens onto Material's variables:

| Material | Token |
|---|---|
| Header and tab background | `--rail`, text `--ink`, with a 1px `--line` bottom edge |
| Page background and text | `--bg`, `--ink` |
| Secondary text | `--muted` |
| Links, focus, active nav item | `--accent` |
| Table header | `--rail` |
| Admonition edges | status tokens, as a full 1px outline |

The header is neutral, as the console's rail is: the accent keeps its one job of marking links, focus and selection. Material
keeps its layout. The docs do not imitate the console's density, because they are for long reading.

### Launch and social

`design/social/slide.css` holds the console's patterns at slide size: the rail row, the 36px header line, tables, the `.tag`
outline, `.notice`, `dl.facts`, code blocks. The scale is the console's multiplied by about 2.9, so 13px body text becomes 38px
and stays readable at phone width.

Rules, proven by the 0.5.0 deck:

- **Format:** 1080×1350, exported as PNG. A slide is a console panel at its below-720px layout: rail row, one header line,
  hairlines.
- **Theme:** dark for exports, the console's dark tokens unchanged.
- **Filled element:** one per deck at most, on the cover command.
- **Show the product:** use real commands, real findings and real screenshots with fake secrets.
- **Banned:** big-number hero stats, cards, gradients, and any text under 32px except code at 28px.
- **Claims:** every claim traces to a Facts block in the campaign file.
- **Images:** alt text with each post.

A campaign copies `tokens.css` and `slide.css` into its own folder and records the commit it copied from. A deck is a dated
snapshot, so it should not change when the tokens later do. This is why no check reaches into `social-publisher`.

The 0.5.0 deck's CSS becomes the base of `slide.css`. `template.html` is two of its slides.

### Brand basics

- **Name:** `sharpit`, always lower case, also at the start of a sentence.
- **Wordmark:** the word in `--ui` at weight 600. No logo.
- **Personality:** precise, candid, quiet.
- **Voice:**
  - A number comes with what it does not cover: "22 of 31 verified", not "full parity".
  - Say verified or built, and never blur the two.
  - State limits as plainly as strengths: alpha, FastAPI only.
  - No hype, and no claim without evidence that can be pointed at.
  - No AI attribution.
- **Credit:** "a Python port of BootUI by Julien Dubois", on the README, the docs footer and any launch material, with the
  Apache-2.0 notice where licences are listed.
- **Status:** alpha appears on launch material until the owner changes it.

## Checks

`tests/design/test_tokens.py` runs in the normal pytest suite. Each is seen red first.

| Check | Fails when |
|---|---|
| Docs copy | `website/docs/stylesheets/tokens.css` differs from `design/tokens.css` |
| One source | `ui/src/app.css` or `sharpit.css` defines a colour token |
| Contrast | any text pair in the `design/DESIGN.md` contrast table is under 4.5:1, computed from `tokens.css` in both themes |
| Doc in step | a token in `tokens.css` is missing from the token tables in `design/DESIGN.md`, or the reverse (only those tables count, so the type sizes and `--md-*` names are not tokens) |

The contrast check needs a small OKLCH to sRGB conversion in the test, with a known-value assertion against the ratios already
in the table.

## Order of work

Each step lands and can be reviewed alone:

1. Move the tokens and `DESIGN.md`, wire the console, rebuild, add the checks.
2. Docs site.
3. `slide.css` and the template.
4. Brand section, then update `AGENTS.md` (Layout), `docs/README.md` and references to `ui/DESIGN.md`.

The chain from `AGENTS.md` applies: `/sharpit:plan`, `/sharpit:check` before commits, a draft PR. No safety model item is touched,
so `/sharpit:llm-council` is not required.

## Done

- The before and after screenshots match in both themes, with live values masked, and the resolved CSS values are unchanged.
- The docs site shows the ochre accent and neutrals in light and dark, with the toggle working under both OS themes.
- All four checks pass, and each was seen red.
- A new slide can be started from `template.html` with no copied colour values.
- CI is green, including the UI build check.

## Left to the builder

- The exact Material variable names, which depend on the installed version.
- Whether `template.html` needs an export script or the campaign's own Playwright step is enough.
- The order of sections in `design/DESIGN.md`.

## Calls to check

These are the author's, not the owner's:

1. `design/` at the repo root, with `ui/DESIGN.md` moved there and not left as a pointer.
2. `tokens.css` as the source, with no JSON and no token build tool.
3. A committed docs copy guarded by a test, rather than a build step.
4. A neutral docs header, not an ochre one.
5. Dark as the export theme for slides.
6. Decks keep a dated copy of the tokens and are not checked by CI.
7. No logo in this version.
8. Lower-case `sharpit` even at the start of a sentence.
9. Starts after the v0.5.0 tag.
10. The no-visual-change proof is a one-off before and after run with masking, plus a CSS diff, with the committed PNGs untouched.
11. Type sizes stay plain sizes in the doc, and `slide.css` owns its `--t-*`.
