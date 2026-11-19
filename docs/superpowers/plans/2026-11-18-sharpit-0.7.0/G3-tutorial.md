# G3 — Interactive tutorial page for documentation site

Production path: `website/docs/tutorial.md`, `website/docs/tutorial/`, `website/mkdocs.yml`, `tests/docs/test_tutorial.py`.

| Scenario | Expected behaviour |
|---|---|
| Visitor opens Interactive tutorial in documentation nav | Tutorial loads within five minutes of reading and clicking, explaining what sharpit is, the problem it solves, developer and AI agent workflows, and calls to action |
| Visitor navigates walkthrough interactively | 7 steps advance smoothly with progress bar, step indicators, Next/Previous buttons, and keyboard controls (ArrowLeft, ArrowRight) |
| JavaScript disabled or unavailable | Every step renders as a sequence of plain readable sections with all explanations, code samples, and real outputs visible |
| Visitor prefers reduced motion | Transitions between steps occur instantly with zero animation or translation transforms |
| Light and dark theme switching | Visual styles use sharpit design tokens (`--bg`, `--rail`, `--ink`, `--muted`, `--accent`, `--line`, etc.) and adapt to `data-md-color-scheme` |
| Mobile (390px) and desktop (1280px) viewports | Fluid responsive layout without text clipping, horizontal overflow, or broken mock consoles |
| Code and output truthfulness | Every SQL line, insight text, CLI command output, and exit code matches real transcripts in `website/docs/tutorial/captures/` |
| Automated validation | `tests/docs/test_tutorial.py` validates nav inclusion, link resolution, `sharpit.cli.commands` parsing of every command, and absence of external URLs except GitHub repo |

- [ ] **Step 1:** Record plan in `docs/superpowers/plans/2026-11-18-sharpit-0.7.0/G3-tutorial.md` and capture real transcripts into `website/docs/tutorial/captures/`.
- [ ] **Step 2:** Build `website/docs/tutorial/tutorial.css` and `website/docs/tutorial/tutorial.js` using sharpit tokens, accessible controls, keyboard navigation, and no-JS progressive enhancement.
- [ ] **Step 3:** Author `website/docs/tutorial.md` covering the 7 steps: problem, one-line install, console mock with N+1 repeated-selects insight, checks, CI gating with exit codes, AI agent comparison linking `ai-agents.md`, and try-it/star links.
- [ ] **Step 4:** Add Interactive tutorial to `website/mkdocs.yml` navigation under `Getting started` near Quickstart.
- [ ] **Step 5:** Implement `tests/docs/test_tutorial.py` asserting nav presence, link validity, CLI command parsing, and external resource restrictions.
- [ ] **Step 6:** Build docs with MkDocs, capture light and dark screenshots at 1280px and 390px using playwright-cli into `.local/`, and audit visual fidelity.
- [ ] **Step 7:** Run all required gates (`mkdocs build --strict`, `pytest`, `ruff`, `pyright`), commit, and report.
