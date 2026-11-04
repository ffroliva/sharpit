# Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Run
> `/sharpit:status --feature design-system` for the next unchecked step, and `/sharpit:check` before every commit.

**Goal:** One tokens file and one design doc drive sharpit's console, docs site and promo slides, with checks that fail on drift.

**Architecture:** `design/tokens.css` takes the token blocks out of `ui/src/app.css` unchanged; the console imports it, the docs
site keeps a test-guarded copy, and slides link it. `design/DESIGN.md` is `ui/DESIGN.md` moved and extended. No engine code,
no runtime dependency.

**Tech Stack:** CSS, Svelte 5 and Vite (console), MkDocs Material (docs), Playwright (proof), pytest (checks).

**Spec:** `docs/superpowers/specs/2026-11-04-design-system-design.md`

**Predict verdict:** not run. No safety model item is touched.

## Global Constraints

- Branch `feat/0.5.0-design-system` from `release/0.5.0`, in worktree `C:\development\github\sharpit-wt\design-system`. The PR targets `release/0.5.0`, never `main`.
- Do not touch `src/sharpit/engine/`, `tests/masking/` or `scripts/dev/masking_gate.py`: another session owns the masking work.
- Runtime dependencies stay exactly `starlette` and `packaging`. No web fonts. `src/sharpit/ui/static/` is rebuilt and committed whenever `ui/` or `design/tokens.css` changes.
- Token names and values do not change. The console must not change visually.
- Commits use a conventional prefix and explicit `git add` paths. No AI attribution of any kind. Do not push without the owner's go.
- Slow commands (`npm run build`, Playwright, `mkdocs build`) run in the background. Per the owner's rule, run only the tests a change touches, then let CI run the full suite.
- Ports: `python ~/.agents/skills/multi-agent-dev/scripts/agentctl.py join` and `lease app-port` before Playwright. Never `docker`.

## Review Focus

- A reader with a dark OS picks light on the docs site, or the reverse: the toggle wins. Pinned in Task 2.
- The installed wheel has no `design/` folder: the console is still fully styled from the built CSS. Pinned in Task 1.
- `prefers-reduced-motion` still sets `--dur` to 0ms after the move. Pinned in Task 1.
- A console user pins light under a dark OS: `:root[data-theme="light"]` and the `:not()` media query survive the move. Pinned in Task 1.
- A campaign copies the slide kit into its own folder: the deck renders with the kit's relative paths. Pinned in Task 3.

## File map

| File | Task | Job |
|---|---|---|
| `design/tokens.css` | 1 | Token source |
| `design/DESIGN.md` | 1, 3, 4 | Moved from `ui/DESIGN.md` |
| `ui/src/app.css`, `ui/src/views/Traces.svelte` | 1 | Consume tokens, drop fallbacks |
| `src/sharpit/ui/static/` | 1 | Rebuilt |
| `scripts/dev/compare_shots.py` | 1 | One-off visual proof |
| `tests/design/test_tokens.py` | 1, 2, 3 | The checks |
| `website/docs/stylesheets/tokens.css`, `sharpit.css`, `website/mkdocs.yml` | 2 | Docs theme |
| `design/social/slide.css`, `template.html` | 3 | Slide kit |
| `AGENTS.md`, `docs/README.md`, `CHANGELOG.md` | 4 | Pointers and release note |

---

### Task 1: Tokens, console, checks

**Files:**
- Create: `design/tokens.css`, `scripts/dev/compare_shots.py`, `tests/design/test_tokens.py`
- Move: `ui/DESIGN.md` to `design/DESIGN.md`
- Modify: `ui/src/app.css:1-35`, `ui/src/views/Traces.svelte:144,146`, `src/sharpit/ui/static/`

**Interfaces:**
- Produces: `design/tokens.css` with the selectors below. In `test_tokens.py`: `tokens(theme: str) -> dict[str, str]` (theme `light` or `dark`, values as raw `oklch(...)` text), `contrast(a: str, b: str) -> float`, `ROOT: Path`.

- [ ] **Step 1: Capture the baseline before any change**

Lease a port. From `ui/`, run in the background, twice, copying `tests/e2e/screenshots/` to a temp folder after each run (`before-1`, `before-2`) and restoring it with `git checkout -- tests/e2e/screenshots`:

```bash
SHOTS=1 SHARPIT_E2E_PORT=<port> npm run e2e
SHOTS=1 SHARPIT_E2E_PORT=<port> npx playwright test -c playwright.sqla.config.ts
```

Also copy the current built CSS from `src/sharpit/ui/static/assets/*.css` to the temp folder.

- [ ] **Step 2: Write the failing tests in `tests/design/test_tokens.py`**

```python
TEXT = ("ink", "muted", "accent", "ok", "warn", "danger")
SURFACES = ("bg", "rail", "sel")

def test_contrast_matches_the_measured_table():
    light = tokens("light")
    assert round(contrast(light["ink"], light["bg"]), 1) == 17.3
    assert round(contrast(light["muted"], light["bg"]), 1) == 6.5
    dark = tokens("dark")
    assert round(contrast(dark["ink"], dark["bg"]), 1) == 15.6
    assert round(contrast(dark["accent"], dark["bg"]), 1) == 9.3

# parametrised over both themes, TEXT and SURFACES
def test_text_pair_passes_aa(theme, text, surface): ...      # contrast >= 4.5
def test_on_accent_passes_aa(theme): ...                     # on-accent on accent >= 4.5
def test_console_defines_no_token(): ...                     # ui/src/app.css has no line declaring a colour token
def test_no_colour_fallbacks_in_ui(): ...                    # no match for r"var\(--[a-z-]+," under ui/src
def test_doc_lists_every_token(): ...                        # token names == names in design/DESIGN.md
def test_theme_blocks_survive(): ...                         # tokens.css text contains each of the four selectors in Step 4
def test_reduced_motion_survives(): ...                      # tokens.css sets --dur: 0ms under prefers-reduced-motion
def test_built_css_carries_the_tokens(): ...                 # a file in src/sharpit/ui/static/assets/*.css holds "--accent:" and "--ink:"
```

`contrast` converts OKLCH to linear sRGB by Ottosson's published matrices, clamps, then applies WCAG 2 relative luminance. `test_doc_lists_every_token` reads the first-column backticked `--name` from tables under `##` headings containing "tokens", so the type sizes are not counted.

- [ ] **Step 3: Run `uv run python scripts/dev/red_check.py <node ids>`**

Expected: red on assertions (`design/tokens.css` absent is a crash, so `tokens()` must report an empty dict and the assertions fail on content).

- [ ] **Step 4: Create `design/tokens.css` and wire the console**

Move lines 2-35 of `ui/src/app.css` into `design/tokens.css` with the values untouched, including the reduced-motion block. The four theme selectors are:

```css
:root, [data-md-color-scheme="default"] { ... }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }
:root[data-theme="light"] { color-scheme: light; }
:root[data-theme="dark"], [data-md-color-scheme="slate"] { ... }
```

`ui/src/app.css` starts with `/* Tokens: design/tokens.css. Rules: design/DESIGN.md. */` then `@import '../../design/tokens.css';`.

In `Traces.svelte` replace `var(--danger, #c0392b)` with `var(--danger)` and `var(--accent, #3b82f6)` with `var(--accent)`. The blue fallback breaks the no-blue rule and never renders. The two `oklch(0 0 0 / ...)` values in `Palette.svelte` stay: they are a shadow and a backdrop, not palette colours.

- [ ] **Step 5: Move and extend the doc**

`git mv ui/DESIGN.md design/DESIGN.md`. Replace its CSS block with a link to `tokens.css`. Add `## Other tokens`, a table with one row per `--ui --mono --s1 --s2 --s3 --s4 --s6 --row --head --rail-w --radius --ease --dur --z-sticky --z-palette`. Note under `## Type` that `--t-*` are plain sizes, not tokens. Change the first line to say it covers every surface.

- [ ] **Step 6: Rebuild**

Run `npm run build` in `ui/` in the background. Expected: the built CSS differs from the Step 1 copy only in the two added Material selectors, and in the file hash. Check with a text diff.

- [ ] **Step 7: Write `scripts/dev/compare_shots.py`**

`main(before_1: Path, before_2: Path, after: Path) -> int`: compare by sha256 per file name. Names that differ between the two before runs are "live", and are printed for checking by eye. Exit 1 if a non-live file differs in `after`, or if a file is missing. A few lines of standard library. Add one small test in `tests/scripts/` with three temp folders covering match, live and regression.

- [ ] **Step 8: Prove no visual change**

Repeat Step 1 once into `after`. Run `python scripts/dev/compare_shots.py <before-1> <before-2> <after>`. Expected: exit 0. Open each live panel in both sets and confirm only live values differ. Restore `tests/e2e/screenshots/`.

- [ ] **Step 9: Run the tests**

Run: `uv run pytest -q tests/design tests/scripts/test_compare_shots.py` and `npm run test` in `ui/`. Expected: pass.

- [ ] **Step 10: Commit**

Commit tests first as `test:`, then `git add design ui/src src/sharpit/ui/static scripts/dev/compare_shots.py` and the deleted `ui/DESIGN.md` as `feat: design tokens in one file, read by the console`.

### Task 2: Docs site

**Files:**
- Create: `website/docs/stylesheets/tokens.css`, `website/docs/stylesheets/sharpit.css`
- Modify: `website/mkdocs.yml:21-33`, `tests/design/test_tokens.py`, `design/DESIGN.md`

**Interfaces:** Consumes `ROOT` from Task 1.

- [ ] **Step 1: Write the failing tests**

```python
def test_docs_copy_matches_tokens():
    assert (ROOT / "website/docs/stylesheets/tokens.css").read_bytes() == (ROOT / "design/tokens.css").read_bytes()

def test_docs_theme_defines_no_colour_token(): ...   # sharpit.css declares no colour token and no oklch( or hex literal
def test_docs_palette_is_custom(): ...               # mkdocs.yml has no "teal", and lists both stylesheets in extra_css
def test_material_schemes_are_mapped(): ...          # tokens.css holds both [data-md-color-scheme=...] selectors
```

- [ ] **Step 2: Run `red_check.py` on them.** Expected: red on assertions.

- [ ] **Step 3: Implement**

Copy `design/tokens.css`. In `mkdocs.yml` set `primary: custom` and `accent: custom` in both palette entries, and add `extra_css` with `stylesheets/tokens.css` then `stylesheets/sharpit.css`. In `sharpit.css` map the spec's Docs site table onto Material's variables: neutral `--rail` header with a 1px `--line` bottom edge, `--accent` for links and focus, full 1px outline admonitions in status colours.

- [ ] **Step 4: Build strictly**

Run in `website/`, in the background: `uvx --python 3.12 --with-requirements requirements.txt mkdocs build --strict`. Expected: exit 0, as `pages.yml` runs it.

- [ ] **Step 5: Check the four theme combinations in a browser**

Serve `website/site` on a leased port. With Playwright, for OS dark and light (`emulate_media`) and both toggle positions, assert the computed `background-color` of `.md-header` and `body`, and that navigation keeps the choice after a second page loads (`navigation.instant`). Measure link contrast on `--bg` in both themes. Expected: the toggle wins in all four. One-off, not committed.

- [ ] **Step 6: Add the `## Docs site` section to `design/DESIGN.md`** from the spec.

- [ ] **Step 7: Run `uv run pytest -q tests/design`.** Expected: pass.

- [ ] **Step 8: Commit** `feat: docs site reads the design tokens`.

### Task 3: Slide kit

**Files:**
- Create: `design/social/slide.css`, `design/social/template.html`
- Modify: `tests/design/test_tokens.py`, `design/DESIGN.md`

**Interfaces:** Source for the CSS: `social-publisher/media/sharpit-v0.5.0/deck.html`, its `<style>` minus the token blocks.

- [ ] **Step 1: Write the failing tests**

```python
def test_slide_kit_has_no_colour_values(): ...     # slide.css and template.html contain no oklch( or hex literal
def test_template_links_the_tokens(): ...          # template.html links ../tokens.css then slide.css, in that order
def test_slide_kit_copies_flat(): ...              # slide.css has no url( or @import, so a campaign can copy it anywhere
```

- [ ] **Step 2: Run `red_check.py` on them.** Expected: red on assertions.

- [ ] **Step 3: Implement**

`slide.css` overrides spacing and shape for slides (`--s1` 12px through `--s6` 72px, `--row` 88px, `--head` 112px, `--radius` 10px) and defines `--t-sm` 32px, `--t-base` 38px, `--t-md` 44px, `--t-lg` 66px and `--hair` 2px. `template.html` is the deck's cover and proof slides with placeholder text in brackets. Its script sets `--fit` as the deck does.

- [ ] **Step 4: Render the template**

With Playwright at 1080×1350, dark scheme, copy `tokens.css`, `slide.css` and the template into one temp folder, adjust the one link, and assert each slide's `.panel-body` has no overflow. Expected: 0. One-off.

- [ ] **Step 5: Add the `## Launch and social` section to `design/DESIGN.md`** from the spec, including how to start a campaign: copy both files, record the commit.

- [ ] **Step 6: Run `uv run pytest -q tests/design`.** Expected: pass.

- [ ] **Step 7: Commit** `feat: slide kit from the console's patterns`.

### Task 4: Brand section and pointers

**Files:**
- Modify: `design/DESIGN.md`, `AGENTS.md` (Layout), `docs/README.md`, `CHANGELOG.md`, `README.md` if a link needs it

- [ ] **Step 1: Add `## Brand` to `design/DESIGN.md`** with the spec's name, wordmark, personality, voice, credit and status rules, and `## Principles` at the top.

- [ ] **Step 2: Update the pointers**

Add `design/` to the `AGENTS.md` Layout block. Link `design/DESIGN.md` in `docs/README.md`. Under `## [0.5.0]`, `### Changed` in `CHANGELOG.md`, add: "The docs site uses the console's neutral palette and ochre accent; `design/` holds the tokens and rules every surface shares." Confirm with `git grep -n 'ui/DESIGN.md'` that only the spec, the plan and dated reports still say it.

- [ ] **Step 3: Run `uv run pytest -q tests/design tests/test_agent_workflow.py tests/docs` and `uv run ruff check`.** Expected: pass.

- [ ] **Step 4: Commit** `docs: brand basics and pointers to design/`.

- [ ] **Step 5: Finish**

Run `/sharpit:check` and `/sharpit:branch-review`. With the owner's go, push and open a draft PR into `release/0.5.0`. CI runs the full suite. Merge only with the owner's go, and tell the masking session that `release/0.5.0` moved.

## Definition of done

- [ ] All steps checked
- [ ] `/sharpit:check` green
- [ ] The spec's Done list is met, with `compare_shots.py` output and the four-theme check recorded in the PR body
- [ ] CI green on the PR, including `ui`, `wheel` and the Pages build
- [ ] No file under the masking work's paths changed: `git diff --name-only origin/release/0.5.0...HEAD`
