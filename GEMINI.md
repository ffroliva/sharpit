# GEMINI.md

All rules for this repository are in [AGENTS.md](AGENTS.md); read it first and follow it. This file holds nothing else.

Gemini CLI / Antigravity notes: the `/sharpit:*` workflows are plain Markdown in `skills/<name>/SKILL.md`; read the
file for the workflow you need. There is no background-task tool, so run long commands detached with a timeout and a
log file (`timeout 900 uv run pytest -q > run.log 2>&1 &`) and read the log's last lines until the summary appears.
