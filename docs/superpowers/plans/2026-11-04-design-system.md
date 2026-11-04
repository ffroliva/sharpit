# Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Run
> `/sharpit:status --feature design-system` for the next unchecked step, and `/sharpit:check` before every commit.

**Goal:** One tokens file and one rule set drive sharpit's console, docs site and promo slides, the measured UI defects are fixed, and checks fail on drift.

**Architecture:** `design/tokens.css` takes the token blocks out of `ui/src/app.css` unchanged; the console imports it, the docs
site keeps a test-guarded copy, and slides link it. `design/DESIGN.md` is `ui/DESIGN.md` moved and extended. Hardening lands after
the no-visual-change proof, in its own task. No engine code, no runtime dependency.

**Tech Stack:** CSS, Svelte 5 and Vite (console), MkDocs Material (docs), Playwright (proof and layout tests), pytest (checks).

**Spec:** `docs/superpowers/specs/2026-11-04-design-system-design.md`

**Predict verdict:** not run. No safety model item is touched.

## Global Constraints

- Base: `release/0.5.0`, which is what folds into `main`. Branch `feat/0.5.0-design-system`, worktree `C:\development\github\sharpit-wt\design-system`. One PR into `release/0.5.0`, never `main`.
- Do not touch `src/sharpit/engine/`, `tests/masking/` or `scripts/dev/masking_gate.py`: another session owns the masking work.
- Runtime dependencies stay exactly `starlette` and `packaging`. No web fonts. `src/sharpit/ui/static/` is rebuilt and committed whenever `ui/` or `design/tokens.css` changes.
- Task 1 changes no token name, value or pixel. Later tasks may change pixels only to meet the written rules or fix a measured defect.
- Commits use a conventional prefix and explicit `git add` paths. No AI attribution of any kind. Do not push without the owner's go.
- A `test:` commit comes before its fix: `scripts/dev/red_check.py` must see a red assertion. A missing file is a crash, so tests assert existence first.
- Slow commands (`npm run build`, Playwright, `mkdocs build`) run in the background. Run only the tests a change touches; CI runs the full suite. This plan's Python blocks must pass `ruff format --check`.
- Ports: `agentctl.py join`, then `lease app-port`, before Playwright. Never `docker`.

## Review Focus

- A reader with a dark OS picks light on the docs site, or the reverse: the toggle wins. Pinned in Task 3.
- The installed wheel has no `design/` folder: the console is fully styled from the built CSS. Pinned in Task 1.
- `prefers-reduced-motion` still sets `--dur` to 0ms after the move. Pinned in Task 1.
- A console user pins light under a dark OS: the `:not()` media query survives the move. Pinned in Task 1.
- A phone user sees every rail link and the current panel without overlap. Pinned in Task 2.

## File map

| File | Task | Job |
|---|---|---|
| `design/tokens.css` | 1 | Token source |
| `design/DESIGN.md` | 1 to 5 | Moved from `ui/DESIGN.md` |
| `ui/src/app.css`, `ui/src/views/Traces.svelte`, `ui/src/views/Data.svelte` | 1 | Consume tokens, drop fallbacks |
| `src/sharpit/ui/static/` | 1, 2 | Rebuilt |
| `pyproject.toml` | 1 | Exclude `design/` and `tests/design` from the sdist |
| `scripts/dev/compare_shots.py`, `tests/scripts/test_compare_shots.py` | 1 | One-off visual proof |
| `tests/design/test_tokens.py` | 1, 3, 4 | Token and surface checks |
| `tests/design/test_ui_rules.py`, `ui/tests/e2e/layout.spec.ts` | 2 | Rule checks and layout tests |
| `ui/src/App.svelte`, `ui/src/components/*.svelte`, `ui/src/views/*.svelte` | 2 | Hardening |
| `website/docs/stylesheets/tokens.css`, `sharpit.css`, `website/mkdocs.yml` | 3 | Docs theme |
| `design/social/slide.css`, `template.html` | 4 | Slide kit |
| `README.md`, `website/docs/index.md`, `action.yml`, `ui/src/views/Exceptions.svelte` | 5 | Copy fixes |
| `AGENTS.md`, `docs/README.md`, `CHANGELOG.md` | 5 | Pointers and release note |

---

### Task 1: Tokens, console, checks, proof

**Files:**
- Create: `design/tokens.css`, `scripts/dev/compare_shots.py`, `tests/design/test_tokens.py`, `tests/scripts/test_compare_shots.py`
- Move: `ui/DESIGN.md` to `design/DESIGN.md`
- Modify: `ui/src/app.css:1-35`, `ui/src/views/Traces.svelte:144,146`, `ui/src/views/Data.svelte:132`, `pyproject.toml`, `src/sharpit/ui/static/`

**Interfaces:**
- Produces: `design/tokens.css`. In `test_tokens.py`: `ROOT: Path`, `tokens(theme: str) -> dict[str, str]`, `contrast(a: str, b: str) -> float`, `contrast_pairs() -> list[tuple[str, str]]` parsed from the `design/DESIGN.md` table.

- [ ] **Step 1: Capture the baseline before any change**

Lease a port. From `ui/`, run in the background, twice, copying `tests/e2e/screenshots/` to a temp folder after each run (`before-1`, `before-2`) and restoring it with `git checkout -- tests/e2e/screenshots`:

```bash
SHOTS=1 SHARPIT_E2E_PORT=<port> npm run e2e
SHOTS=1 SHARPIT_E2E_PORT=<port> npx playwright test -c playwright.sqla.config.ts
```

Copy the built CSS from `src/sharpit/ui/static/assets/*.css` to the temp folder too.

- [ ] **Step 2: Write the failing tests**

`tokens()` asserts `design/tokens.css` exists, so a missing file fails on an assertion. Each test reads through it.

```python
def test_contrast_matches_the_measured_table():
    light, dark = tokens("light"), tokens("dark")
    assert round(contrast(light["ink"], light["bg"]), 1) == 17.3
    assert round(contrast(light["muted"], light["bg"]), 1) == 6.5
    assert round(contrast(dark["ink"], dark["bg"]), 1) == 15.6
    assert round(contrast(dark["accent"], dark["bg"]), 1) == 9.3


def test_text_pairs_pass_aa(theme):
    values = tokens(theme)
    for text, surface in contrast_pairs():
        assert contrast(values[text], values[surface]) >= 4.5, (text, surface)


def test_built_css_carries_the_tokens():
    built = "".join(p.read_text() for p in (ROOT / "src/sharpit/ui/static/assets").glob("*.css"))
    assert "--accent:" in built
    assert "data-md-color-scheme" in built  # absent until the rebuild, so this is a real red
```

Also, one assertion each: `test_console_defines_no_token` (no colour token declared in `ui/src/app.css`), `test_no_colour_fallbacks_in_ui` (no match for `r"var\(--[a-z-]+,"` under `ui/src`), `test_doc_lists_every_token` (names in tokens.css equal first-column `--name` in tables under `##` headings containing "tokens"), `test_theme_blocks_survive` (the four selectors of Step 5), `test_reduced_motion_survives`, `test_sdist_excludes_design` (`pyproject.toml` excludes both paths).

`contrast` converts OKLCH to linear sRGB by Ottosson's published matrices, clamps, then applies WCAG 2 relative luminance.

- [ ] **Step 3: Run `uv run python scripts/dev/red_check.py <node ids>`.** Expected: red on assertions.

- [ ] **Step 4: Commit** `test: design tokens, one source, AA contrast, built CSS`.

- [ ] **Step 5: Create `design/tokens.css` and wire the console**

Move lines 2-35 of `ui/src/app.css` into `design/tokens.css` with values untouched, including the reduced-motion block. The selectors:

```css
:root, [data-md-color-scheme="default"] { ... }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }
:root[data-theme="light"] { color-scheme: light; }
:root[data-theme="dark"], [data-md-color-scheme="slate"] { ... }
```

`ui/src/app.css` starts with `/* Tokens: design/tokens.css. Rules: design/DESIGN.md. */` then `@import '../../design/tokens.css';`.

Remove the fallbacks: `var(--danger, #c0392b)` and `var(--accent, #3b82f6)` in `Traces.svelte` become `var(--danger)` and `var(--accent)`. `var(--surface, transparent)` in `Data.svelte` becomes `transparent`, since `--surface` is defined nowhere. The two `oklch(0 0 0 / ...)` values in `Palette.svelte` stay: a shadow and a backdrop.

Add `/design` and `/tests/design` to the sdist excludes in `pyproject.toml`.

- [ ] **Step 6: Move and extend the doc**

`git mv ui/DESIGN.md design/DESIGN.md`. Replace its CSS block with a link to `tokens.css`. Add `## Other tokens`, one table row per `--ui --mono --s1 --s2 --s3 --s4 --s6 --row --head --rail-w --radius --ease --dur --z-sticky --z-palette`. Add `## Spacing and type rules` from the spec. Under `## Type`, remove the 1.125 claim and publish the size set.

- [ ] **Step 7: Rebuild**

Run `npm run build` in `ui/`, in the background. Expected: a text diff against the Step 1 CSS shows only the two added Material selectors.

- [ ] **Step 8: Write `scripts/dev/compare_shots.py` and its test**

`main(before_1: Path, before_2: Path, after: Path) -> int`: compare by sha256 per file name. Names differing between the two before runs are "live" and printed for checking by eye. Exit 1 if a non-live file differs in `after` or a file is missing. Test with three temp folders: match, live, regression.

- [ ] **Step 9: Prove no visual change**

Repeat Step 1 once into `after`. Run `python scripts/dev/compare_shots.py <before-1> <before-2> <after>`. Expected: exit 0. Open each live panel in both sets. Restore `tests/e2e/screenshots/`. Keep the output for the PR body.

- [ ] **Step 10: Run** `uv run pytest -q tests/design tests/scripts/test_compare_shots.py`, `npm run test`. Expected: pass.

- [ ] **Step 11: Commit** `feat: design tokens in one file, read by the console`.

### Task 2: Harden the console

**Files:**
- Create: `tests/design/test_ui_rules.py`, `ui/tests/e2e/layout.spec.ts`
- Modify: `ui/src/App.svelte`, `ui/src/app.css`, `ui/src/components/PanelShell.svelte`, `ui/src/components/ServerTable.svelte`, the views named below, `src/sharpit/ui/static/`

**Interfaces:** Consumes the rules in `design/DESIGN.md` from Task 1.

- [ ] **Step 1: Write the failing rule checks in `test_ui_rules.py`**

```python
def test_console_uses_h1_and_h2_only():
    assert not svelte_matches(r"<h[3-6]\b")


def test_no_card_rule_in_the_console():
    assert not svelte_matches(r"\.card\b")


def test_font_sizes_are_published():
    assert css_font_sizes() <= {"11px", "12px", "12.5px", "13px", "14.5px", "16.5px", "20px"}


def test_spacing_literals_are_commented():
    assert uncommented_off_scale_spacing() == []
```

`svelte_matches` and `css_font_sizes` scan `ui/src`; each asserts it found files.

- [ ] **Step 2: Write the failing `layout.spec.ts`**

In both themes, against the sample apps, assert with Playwright:

| Test | Viewport | Assertion |
|---|---|---|
| `rail links do not overlap` | 390, 720 | each link's left is at or past the previous link's right |
| `current panel is in view` | 390, 720, 1280×500 | the current rail item intersects the rail's visible box |
| `fluid columns have width` | 390 | every `th` on Loggers, Providers and HTTP Exchanges has width over 48px |
| `panel header is one line` | 1280 | `.panel-head` height is 36px or less on Log Tail and Security Logs |
| `headings are styled` | 1280 | on SQLAlchemy Statistics and FastAPI Security, h2 is 13px weight 600 and its text starts at 16px |
| `header actions sit right` | 1280 | the last header control ends at the header's right padding on Health, Exceptions, SQL Trace, Transactions, Security Logs, Alembic |
| `details target size` | 390 | Details and link buttons are at least 24px tall |

Run them. Expected: red on assertions.

- [ ] **Step 3: Commit** `test: console rules and layout at phone and desktop widths`.

- [ ] **Step 4: Fix, one cause at a time**

| Defect | Fix |
|---|---|
| Rail overlap at 720px and under | `ul { flex: none; }` in the `App.svelte` media block |
| Current item off screen | `scrollIntoView({ block: 'nearest', inline: 'nearest' })` on route change, instant under reduced motion. The rail stays at `--rail-w`: `.why` text wraps |
| Fluid columns collapse | `ServerTable.svelte`: `table.fixed` below 720px uses auto layout, or a `min-width` on fluid columns |
| Unstyled h2 and h3 | Global `h2` rule from `section.block h2`; `DatabaseAdvisor.svelte:55,66` h3 becomes h2; style SQLAlchemy Statistics and FastAPI Security with `section.block` and `dl.facts` |
| Heading spacing | One rule: 12 above, 4 below. Remove the 4 and 8 overrides in Alembic, MySql, PostgreSql, Vulnerabilities, and the extra 16 from `dl.facts` under a heading |
| Log Tail header 105px | `LogTail.svelte:73`: move the input into `.grow` |
| Security Logs inputs | `SecurityLogs.svelte:52`: `type="text"` |
| Header actions mid-header | Remove the second `margin-left: auto`: `.push` and `PanelShell` must not both apply |
| Table cell inset | `app.css:97,102`: last cell's right padding matches the first's left, `--s4` |
| Off-scale values | `Palette:193`, `SqlTrace:231`, `Traces:149`, and sizes at `AdvisorPanel:322`, `ConnectionPools:97`, `LogTail:103` |
| `.card` | `ConnectionPools.svelte:93`: hairline-separated `section.block` |
| Notice margins | `.notice` is `<p>`: `margin: 0` |
| Exceptions h2 700 | Weight 600 |
| Data notice shown twice | Show it once |
| Hit targets 16 to 20px | `.link` buttons `min-height: 24px` at 720px and under |
| Focus ring clipped on 14 selectors | Negative `outline-offset` inside scroll regions |
| Error states without Retry | Overview, ServerTable panels, Vulnerabilities: pass `onretry`, as `PanelShell` already supports |
| Unavailable pages without h1 | Render the panel title as h1 |
| Numbers left aligned | `.num` on Statistics columns; "2700 ms" does not wrap |
| Health separator | A space after the check name |

- [ ] **Step 5: Rebuild and run**

`npm run build`, `npm run test`, `npm run e2e`, then `npx playwright test -c playwright.sqla.config.ts`, `uv run pytest -q tests/design`. Expected: pass. Axe in `a11y.spec.ts` stays clean.

- [ ] **Step 6: Re-measure**

Repeat the audit's phone checks on Loggers, HTTP Exchanges, Providers and the rail at 390 in both themes. Look at each changed panel at 1280 in both themes.

- [ ] **Step 7: Commit** `fix: console spacing, headings and phone layout follow the written rules`.

### Task 3: Docs site

**Files:**
- Create: `website/docs/stylesheets/tokens.css`, `website/docs/stylesheets/sharpit.css`
- Modify: `website/mkdocs.yml:21-33`, `tests/design/test_tokens.py`, `design/DESIGN.md`

**Interfaces:** Consumes `ROOT` from Task 1.

- [ ] **Step 1: Write the failing tests**

```python
def test_docs_copy_matches_tokens():
    copy = ROOT / "website/docs/stylesheets/tokens.css"
    assert copy.is_file()
    assert copy.read_bytes() == (ROOT / "design/tokens.css").read_bytes()


def test_docs_theme_maps_on_the_scheme():
    theme = ROOT / "website/docs/stylesheets/sharpit.css"
    assert theme.is_file()
    assert "[data-md-color-scheme]" in theme.read_text()
```

Also: `test_docs_theme_defines_no_colour_token` (asserts the file exists; no colour token, no `oklch(` or hex), `test_docs_palette_is_custom` (no `teal`; both stylesheets in `extra_css`). Add `*.css text eol=lf` for these two paths to `.gitattributes` if the byte test differs on Windows.

- [ ] **Step 2: Run `red_check.py`, then commit** `test: docs site reads the shared tokens`.

- [ ] **Step 3: Implement**

Copy `design/tokens.css`. In `mkdocs.yml` set `primary: custom` and `accent: custom` in both palette entries, and add `extra_css` with `stylesheets/tokens.css` then `stylesheets/sharpit.css`. In `sharpit.css`, under `[data-md-color-scheme]`, map the spec's Docs site table: neutral `--rail` header with a 1px `--line` bottom edge, `--accent` for links and focus, h1 to `--ink`, full 1px outline admonitions, headings at 400 and 600 only.

- [ ] **Step 4: Build strictly**

In `website/`, in the background: `uvx --python 3.12 --with-requirements requirements.txt mkdocs build --strict`. Expected: exit 0, as `pages.yml` runs it.

- [ ] **Step 5: Check the four theme combinations in a browser**

Serve `website/site/` under `/sharpit/` on a leased port, so assets resolve. For OS dark and light with both toggle positions, assert computed `background-color` on `.md-header` and `body`, and that the choice survives a `navigation.instant` page change. Measure link contrast and heading weights. Expected: the toggle wins all four, links are 4.5:1 or more. One-off.

- [ ] **Step 6: Add `## Docs site` to `design/DESIGN.md`, run `uv run pytest -q tests/design`, commit** `feat: docs site reads the design tokens`.

### Task 4: Slide kit and deck

**Files:**
- Create: `design/social/slide.css`, `design/social/template.html`
- Modify: `tests/design/test_tokens.py`, `design/DESIGN.md`

**Interfaces:** Source: approved `social-publisher/media/sharpit-v0.4.0/deck.html`, its `<style>`.

- [ ] **Step 1: Write the failing tests**

```python
def test_slide_kit_has_no_colour_or_size_literals():
    kit = ROOT / "design/social/slide.css"
    assert kit.is_file()
    text = kit.read_text()
    assert "oklch(" not in text
    assert not re.search(r"font-size:\s*\d", text)
```

Also `test_template_links_tokens_then_kit` (order of the two links) and `test_slide_type_floor` (`--t-sm` is 34px or more).

- [ ] **Step 2: Run `red_check.py`, then commit** `test: slide kit reads tokens and keeps its type floor`.

- [ ] **Step 3: Implement**

`slide.css` derives from the approved deck style, defines spacing `--s2` 24px, `--s3` 36px, `--s4` 48px, `--s6` 72px and type `--t-sm` 34px, `--t-base` 42px, `--t-lg` 84px, `--t-xl` 112px. It declares no colour tokens and has no literal font sizes. `template.html` is a two-slide starter with equal 72px margins, a real hook cover, one idea per slide, vertically centred content and one wordmark line. It links `../tokens.css` before `slide.css`, pins the dark theme, and its fit script reads `document.documentElement.clientWidth`.

- [ ] **Step 4: Rebuild the deck on the kit**

Skip this step; the coordinating Claude Code session will rebuild the deck in social-publisher.

- [ ] **Step 5: Add `## Launch and social` to `design/DESIGN.md`, run `uv run pytest -q tests/design`, commit** `feat: slide kit from the console's patterns`.

### Task 5: Brand, copy and pointers

**Files:**
- Modify: `design/DESIGN.md`, `README.md`, `website/docs/index.md`, `pyproject.toml:8`, `action.yml:2`, `ui/src/views/Exceptions.svelte:80`, `ui/src/views/DatabaseAdvisor.svelte:37`, `AGENTS.md` (Layout), `docs/README.md`, `CHANGELOG.md`, `src/sharpit/ui/static/`

- [ ] **Step 1: Add `## Brand` and `## Principles` to `design/DESIGN.md`** from the spec, including the one line, pillars, glossary and version rule.

- [ ] **Step 2: Fix the copy**

| Where | Change |
|---|---|
| `pyproject.toml:8`, README first line, `index.md:3`, `mkdocs.yml:3` | The spec's one line, or its shortened form |
| README:129, `index.md:8` | "a Python port of BootUI by Julien Dubois" |
| README:81,86 | "Outside proof" becomes "On the author's own project: gflow-cli"; "Proved" becomes "Showed" |
| README and `index.md:4` | Cut "understandable in minutes" |
| `index.md:17` | "from git" becomes "from PyPI" |
| `action.yml:2` | "SQL and exception gates" |
| `Exceptions.svelte:80` | Delete "That is good news." |
| `DatabaseAdvisor.svelte:37` | "Run database checks" |
| README:15 and :197 | "Licence" in prose |

- [ ] **Step 3: Update the pointers**

Add `design/` to the `AGENTS.md` Layout block. Link `design/DESIGN.md` in `docs/README.md`. Under `## [0.5.0]`, `### Changed` in `CHANGELOG.md`: "The docs site uses the console's neutral palette and ochre accent; `design/` holds the tokens and rules every surface shares." Under `### Fixed`: phone layout of the rail and fluid tables, heading styles, and Retry on load errors. Confirm with `git grep -n 'ui/DESIGN.md'` that only the spec, the plan and dated reports still say it.

- [ ] **Step 4: Rebuild `ui`, run** `uv run pytest -q tests/design tests/test_agent_workflow.py tests/docs`, `uv run ruff check`, `uv run ruff format --check`. Expected: pass.

- [ ] **Step 5: Commit** `docs: brand basics, one description, pointers to design/`.

- [ ] **Step 6: Finish**

Run `/sharpit:check` and `/sharpit:branch-review`. With the owner's go, push and open one draft PR into `release/0.5.0`. CI runs the full suite. A merge revert restores the static build, so the PR is the rollback unit. Merge only with the owner's go, and tell the masking session that `release/0.5.0` moved; `AGENTS.md` may need a small conflict fix there.

## Owner actions, outward


## Definition of done

- [ ] All steps checked
- [ ] `/sharpit:check` green
- [ ] The spec's Done list is met, with `compare_shots.py` output and the four-theme check in the PR body
- [ ] CI green on the PR, including `ui`, `wheel` and the Pages build
- [ ] No file under the masking work's paths changed: `git diff --name-only origin/release/0.5.0...HEAD`
