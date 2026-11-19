"""Static security analyzer detection rule SEC-STATIC-001 (port of BootUI 2.4.0 #1597).

Detects declarations for a small, known set of static security analyzers (Bandit, Semgrep, CodeQL,
a sonar-project.properties file, Ruff with S selected) without running them.

Only bounded local project and repository configuration is inspected. Incomplete, unsafe, malformed
or oversized evidence is indeterminate rather than evidence that an analyzer is absent.
"""

from __future__ import annotations

import configparser
import enum
import os
import re
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sharpit.engine.advisors.findings import Finding
from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.appsource import as_dict, as_str_list, requirements_name
from sharpit.engine.collectors.security.static_analysis_files import (
    contains_symbolic_link,
    read_bounded,
    read_text,
    strip_yaml_comments,
)

RULE_ID = "SEC-STATIC-001"
TITLE = "No local static security analysis declared"
CATEGORY = "Static analysis"
SEVERITY = "INFO"
DETAIL = "No recognized static security analyzer declaration was found in the inspected local project files."
DESCRIPTION = (
    DETAIL + " ruff.toml extend configurations are not followed, requirements -r includes are not followed, and"
    " remote or organization-managed configuration is not resolved. sharpit does not run analyzers or verify"
    " execution."
)
RECOMMENDATION = (
    "Declare Bandit (e.g. in requirements, pyproject.toml, or setup.cfg), Semgrep, CodeQL, a"
    " sonar-project.properties file, or Ruff with the S rules selected in pyproject.toml. sharpit does not"
    " install or run analyzers."
)
LEARN_MORE_URL = "https://bandit.readthedocs.io/"
LIMITATION_TEXT = "Static analyzer configuration could not be assessed from bounded local files."

MAX_WORKFLOW_FILES = 64
MAX_PARENT_DEPTH = 5

PYPROJECT_TOML = "pyproject.toml"
SETUP_CFG = "setup.cfg"
TOX_INI = "tox.ini"
PRE_COMMIT_CONFIG_YAML = ".pre-commit-config.yaml"
RUFF_TOML = "ruff.toml"
DOT_RUFF_TOML = ".ruff.toml"

KNOWN_WORKFLOW_ACTION = re.compile(
    r"(?i)^(?:github/codeql-action/(?:init|analyze)@\S+|"
    r"(?:semgrep|returntocorp)/semgrep-action\S*|"
    r"sonarsource/(?:sonarqube-scan-action|sonarcloud-github-action)\S*|"
    r"pycqa/bandit-action\S*)$"
)
ENVIRONMENT_ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=.*$", re.ASCII)
REQUIREMENT_NAME_PATTERN = re.compile(r"^(?:bandit|semgrep)(?:\s*\[[^\]]*\])?(?:\s*[<>=!~;@\(].*)?$", re.IGNORECASE)

SEMGREP_CONFIG_RELPATHS = (
    Path(".semgrep.yml"),
    Path(".semgrep.yaml"),
    Path("semgrep.yml"),
    Path("semgrep.yaml"),
    Path(".semgrep/semgrep.yml"),
    Path(".semgrep/config.yml"),
)


class State(enum.StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFIGURED = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class Inspection:
    state: State

    @property
    def evaluated(self) -> bool:
        return self.state in (State.CONFIGURED, State.NOT_CONFIGURED)


def _process_quoted_char(c: str, quote: str, escaped: bool, token: list[str] | None = None) -> tuple[str | None, bool]:
    if c == "\\" and quote == '"' and not escaped:
        return quote, True
    if c == quote and not escaped:
        return None, False
    if token is not None:
        token.append(c)
    return quote, False


def _skip_compound_operator(command: str, i: int, c: str) -> int:
    if i + 1 < len(command) and (c == "|" or c == "&") and command[i + 1] == c:
        return i + 1
    return i


def _split_shell_commands(command: str) -> list[str]:
    statements: list[str] = []
    quote: str | None = None
    escaped = False
    start = 0
    i = 0
    n = len(command)
    while i < n:
        c = command[i]
        if quote is not None:
            quote, escaped = _process_quoted_char(c, quote, escaped)
        elif c in ('"', "'"):
            quote = c
        elif c in (";", "|", "&"):
            statements.append(command[start:i])
            i = _skip_compound_operator(command, i, c)
            start = i + 1
        i += 1
    statements.append(command[start:])
    return [s.strip() for s in statements if s.strip()]


def _flush_token(token: list[str], tokens: list[str]) -> None:
    if token:
        tokens.append("".join(token))
        token.clear()


def _shell_tokens(statement: str) -> list[str]:
    tokens: list[str] = []
    token: list[str] = []
    quote: str | None = None
    escaped = False
    for c in statement:
        if quote is not None:
            quote, escaped = _process_quoted_char(c, quote, escaped, token)
        elif c in ('"', "'"):
            quote = c
        elif c.isspace():
            _flush_token(token, tokens)
        else:
            token.append(c)
    _flush_token(token, tokens)
    return tokens


def _is_semgrep_config_arg(args: Sequence[str], idx: int, arg: str) -> bool:
    if arg.startswith("--config=") and len(arg) > len("--config="):
        return True
    if arg in ("--config", "-f") and idx + 1 < len(args) and args[idx + 1].strip():
        return True
    return arg.startswith("-f") and len(arg) > 2


def _is_semgrep_invocation(args: Sequence[str]) -> bool:
    if args and args[0] in ("scan", "ci"):
        return True
    return any(_is_semgrep_config_arg(args, idx, arg) for idx, arg in enumerate(args))


_RUNNER_VALUE_OPTIONS = frozenset(
    {
        "--python",
        "--group",
        "--with",
        "--extra",
        "--package",
        "-p",
        "--project",
        "--directory",
        "-C",
        "--env-file",
        "--index",
        "--default-index",
    }
)

_WRAPPER_COMMANDS = frozenset({"env", "sudo", "time", "command", "exec"})


def _skip_runner_options(args: list[str]) -> list[str]:
    pos = 0
    while pos < len(args):
        tok = args[pos]
        if tok == "--":
            pos += 1
            break
        if tok in _RUNNER_VALUE_OPTIONS:
            pos += 2
            continue
        if tok.startswith("-"):
            pos += 1
            continue
        break
    return args[pos:]


def _strip_wrapper_tokens(tokens: list[str]) -> int:
    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if tok not in _WRAPPER_COMMANDS and not ENVIRONMENT_ASSIGNMENT.match(tok):
            break
        idx += 1
    return idx


def _basename_lower(token: str) -> str:
    return token.rpartition("/")[2].rpartition("\\")[2].lower()


def _is_python_executable(executable: str) -> bool:
    if executable in ("python", "python3", "py", "{envpython}"):
        return True
    return bool(re.match(r"^python3\.\d+$", executable))


def _unwrap_python_runner(executable: str, args: list[str]) -> tuple[str, list[str]] | None:
    if not _is_python_executable(executable) or "-m" not in args:
        return None
    m_idx = args.index("-m")
    if m_idx + 1 < len(args):
        return args[m_idx + 1].lower(), args[m_idx + 2 :]
    return None


def _unwrap_package_runner(executable: str, args: list[str]) -> tuple[str, list[str]] | None:
    if executable in ("uv", "poetry", "pipx") and args and args[0] == "run":
        rem = _skip_runner_options(args[1:])
        return (_basename_lower(rem[0]), rem[1:]) if rem else ("", [])
    if executable == "uvx":
        rem = _skip_runner_options(args)
        return (_basename_lower(rem[0]), rem[1:]) if rem else ("", [])
    return None


def _unwrap_runner_tokens(tokens: list[str]) -> tuple[str, list[str]]:
    """Unwrap execution runners like uv, uvx, python -m, poetry, pipx, tox to find target command and args."""
    idx = _strip_wrapper_tokens(tokens)
    if idx >= len(tokens):
        return "", []

    executable = _basename_lower(tokens[idx])
    args = tokens[idx + 1 :]

    if (py_res := _unwrap_python_runner(executable, args)) is not None:
        return py_res
    if (pkg_res := _unwrap_package_runner(executable, args)) is not None:
        return pkg_res
    return executable, args


def _is_known_analyzer_command(name: str, args: list[str]) -> bool:
    if name == "bandit":
        return not args or not args[0].startswith("--version")
    if name == "semgrep":
        return _is_semgrep_invocation(args)
    if name == "codeql":
        return bool(args) and args[0] in ("database", "analyze")
    return name == "sonar-scanner"


def _has_known_workflow_command(command: str) -> bool:
    for stmt in _split_shell_commands(command):
        tokens = _shell_tokens(stmt)
        name, args = _unwrap_runner_tokens(tokens)
        if name and _is_known_analyzer_command(name, args):
            return True
    return False


def _unquote_workflow_run_scalar(command: str) -> str:
    if len(command) < 2:
        return command
    quote = command[0]
    if quote not in ('"', "'") or command[-1] != quote:
        return command
    val = command[1:-1]
    return val.replace("''", "'") if quote == "'" else val.replace('\\"', '"').replace("\\\\", "\\")


def _check_step_action_or_command(trimmed: str) -> tuple[bool, bool, bool]:
    """Return (matched, enter_block, folded_block)."""
    if trimmed.startswith("- "):
        trimmed = trimmed[2:].lstrip()
    if trimmed.startswith("uses:"):
        action = trimmed[len("uses:") :].strip().strip("\"'")
        return bool(KNOWN_WORKFLOW_ACTION.match(action)), False, False
    if trimmed.startswith("run:"):
        command = trimmed[len("run:") :].strip()
        if not command or command.startswith(("|", ">")):
            return False, True, command.startswith(">")
        return _has_known_workflow_command(_unquote_workflow_run_scalar(command)), False, False
    return False, False, False


def _process_run_block_line(
    trimmed: str, indent: int, run_indent: int, folded: bool, block: list[str]
) -> tuple[bool, bool]:
    """Process a line in a run block. Returns (matched, continue_block)."""
    if not trimmed:
        return False, True
    if indent <= run_indent:
        return _has_known_workflow_command(" ".join(block)), False
    if folded:
        block.append(trimmed)
    elif trimmed.endswith("\\") and not trimmed.endswith("\\\\"):
        block.append(trimmed[:-1].rstrip())
    else:
        block.append(trimmed)
        if _has_known_workflow_command(" ".join(block)):
            return True, True
        block.clear()
    return False, True


def _has_known_workflow_declaration(text: str) -> bool:
    in_run_block = False
    folded_run_block = False
    run_indent = -1
    block_command: list[str] = []

    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        trimmed = line.strip()
        if in_run_block:
            matched, cont = _process_run_block_line(trimmed, indent, run_indent, folded_run_block, block_command)
            if matched:
                return True
            if cont:
                continue
            in_run_block = False
            block_command.clear()

        matched, enter_block, folded = _check_step_action_or_command(trimmed)
        if matched:
            return True
        if enter_block:
            in_run_block = True
            folded_run_block = folded
            run_indent = indent
            block_command.clear()

    return bool(block_command) and _has_known_workflow_command(" ".join(block_command))


def _repository_root(project_root: Path) -> Path:
    current: Path | None = project_root
    for _ in range(MAX_PARENT_DEPTH + 1):
        if current is None:
            break
        marker = current / ".git"
        try:
            if marker.exists() and not marker.is_symlink():
                return current
        except OSError:
            break
        current = current.parent if current.parent != current else None
    return project_root


def _repository_roots(project_root: Path, repository_root: Path) -> tuple[Path, ...]:
    return (project_root,) if repository_root == project_root else (project_root, repository_root)


def _inspect_workflow_entry(repository_root: Path, entry: os.DirEntry[str]) -> tuple[bool, bool]:
    if not entry.is_file(follow_symlinks=False) or entry.is_symlink():
        return False, True
    try:
        cleaned = strip_yaml_comments(read_text(repository_root, Path(entry.path)))
        return (True, False) if _has_known_workflow_declaration(cleaned) else (False, False)
    except Exception:  # noqa: BLE001
        return False, True


def _is_valid_workflow_dir(repository_root: Path, directory: Path) -> tuple[bool, bool]:
    """Return (is_dir, indeterminate). If not is_dir and not indeterminate, dir does not exist."""
    if contains_symbolic_link(repository_root, directory):
        return False, True
    try:
        if not directory.exists():
            return False, False
        if not directory.is_dir():
            return False, True
    except OSError:
        return False, True
    return True, False


def _scan_workflow_entries(repository_root: Path, directory: Path) -> tuple[bool, bool]:
    visited = 0
    indeterminate = False
    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.name.lower().endswith((".yml", ".yaml")):
                continue
            visited += 1
            if visited > MAX_WORKFLOW_FILES:
                return False, True
            conf, ind = _inspect_workflow_entry(repository_root, entry)
            if conf:
                return True, False
            indeterminate |= ind
    return False, indeterminate


def _inspect_workflows(repository_root: Path, directory: Path) -> tuple[bool, bool]:
    """(configured, indeterminate) for .github/workflows directory."""
    valid_dir, indeterminate = _is_valid_workflow_dir(repository_root, directory)
    if not valid_dir:
        return False, indeterminate
    try:
        return _scan_workflow_entries(repository_root, directory)
    except OSError:
        return False, True


def _inspect_bounded_file(
    trusted_root: Path, path: Path, check: Callable[[bytes], bool | tuple[bool, bool]]
) -> tuple[bool, bool] | None:
    """Read one safe, bounded config file and return (configured, indeterminate), or None if absent."""
    if contains_symbolic_link(trusted_root, path):
        return False, True
    try:
        if not path.exists():
            return None
        result = check(read_bounded(trusted_root, path))
        return result if isinstance(result, tuple) else (result, False)
    except Exception:  # noqa: BLE001 - malformed or unsafe local config is indeterminate
        return False, True


def _inspect_sonar_properties(repository_root: Path, path: Path) -> tuple[bool, bool]:
    """(configured, indeterminate) for sonar-project.properties."""
    result = _inspect_bounded_file(
        repository_root, path, lambda data: bool(data.decode("utf-8-sig", errors="replace").strip())
    )
    return result or (False, False)


def _inspect_single_semgrep_file(repository_root: Path, cfg: Path) -> tuple[bool, bool]:
    """Return (configured, indeterminate) for a single semgrep config file."""
    result = _inspect_bounded_file(repository_root, cfg, lambda data: bool(data.decode("utf-8-sig").strip()))
    return result or (False, False)


def _inspect_semgrep_configs(repository_root: Path, candidate_roots: Sequence[Path]) -> tuple[bool, bool]:
    """(configured, indeterminate) for recognized Semgrep config files."""
    indeterminate = False
    for root in candidate_roots:
        for rel in SEMGREP_CONFIG_RELPATHS:
            conf, ind = _inspect_single_semgrep_file(repository_root, root / rel)
            if conf:
                return True, False
            indeterminate |= ind
    return False, indeterminate


def _is_pre_commit_repo(lower: str) -> bool:
    repo_val = lower.partition("repo:")[2].strip().strip("\"'")
    return "pycqa/bandit" in repo_val or "semgrep/semgrep" in repo_val


def _is_pre_commit_id(lower: str) -> bool:
    val = lower.partition("id:")[2].strip().strip("\"'")
    return val in ("bandit", "semgrep")


def _is_pre_commit_entry(item: str) -> bool:
    cmd = item.partition("entry:")[2].strip().strip("\"'")
    return _has_known_workflow_command(cmd)


def _inspect_pre_commit_line(line: str) -> bool:
    item = line.strip().removeprefix("-").strip()
    lower = item.lower()
    if lower.startswith("repo:"):
        return _is_pre_commit_repo(lower)
    if lower.startswith("id:"):
        return _is_pre_commit_id(lower)
    if lower.startswith("entry:"):
        return _is_pre_commit_entry(item)
    return False


def _inspect_pre_commit(repository_root: Path, path: Path) -> tuple[bool, bool]:
    """(configured, indeterminate) for .pre-commit-config.yaml."""

    def check(data: bytes) -> bool:
        text = strip_yaml_comments(data.decode("utf-8-sig"))
        return any(_inspect_pre_commit_line(line) for line in text.splitlines())

    return _inspect_bounded_file(repository_root, path, check) or (False, False)


def _inspect_requirements(repository_root: Path, path: Path) -> tuple[bool, bool]:
    """(configured, indeterminate) for requirements*.txt files."""

    def check(data: bytes) -> bool:
        return any(
            REQUIREMENT_NAME_PATTERN.match(line.partition("#")[0].strip())
            for line in data.decode("utf-8-sig").splitlines()
        )

    return _inspect_bounded_file(repository_root, path, check) or (False, False)


def _has_setup_cfg_requirements(parser: configparser.ConfigParser) -> bool:
    lines: list[str] = []
    if parser.has_section("options"):
        lines.extend(parser.get("options", "install_requires", fallback="").splitlines())
    if parser.has_section("options.extras_require"):
        for _, val in parser.items("options.extras_require"):
            lines.extend(val.splitlines())
    return any(REQUIREMENT_NAME_PATTERN.match(line.partition("#")[0].strip()) for line in lines)


def _inspect_setup_cfg(repository_root: Path, path: Path) -> tuple[bool, bool]:
    """(configured, indeterminate) for setup.cfg."""

    def check(data: bytes) -> bool:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(data.decode("utf-8-sig"))
        return any("bandit" in section.lower() for section in parser.sections()) or _has_setup_cfg_requirements(parser)

    return _inspect_bounded_file(repository_root, path, check) or (False, False)


def _tox_section_has_analyzer(parser: configparser.ConfigParser, sec: str) -> bool:
    deps = parser.get(sec, "deps", fallback="").splitlines()
    if any(REQUIREMENT_NAME_PATTERN.match(line.partition("#")[0].strip()) for line in deps):
        return True
    cmds = parser.get(sec, "commands", fallback="").splitlines()
    return any(_has_known_workflow_command(line.strip()) for line in cmds)


def _inspect_tox_ini(repository_root: Path, path: Path) -> tuple[bool, bool]:
    """(configured, indeterminate) for tox.ini."""

    def check(data: bytes) -> bool:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(data.decode("utf-8-sig"))
        return any(_tox_section_has_analyzer(parser, section) for section in parser.sections())

    return _inspect_bounded_file(repository_root, path, check) or (False, False)


def _resolve_ruff_dict(data: dict[str, object]) -> tuple[bool, bool]:
    """Resolve Ruff configuration dict (from ruff.toml or pyproject tool.ruff).

    Returns (configured, indeterminate).
    """
    if "extend" in data:
        return False, True

    lint = as_dict(data.get("lint"))
    if "extend" in lint:
        return False, True

    def _field(name: str) -> list[str]:
        return as_str_list(lint[name] if name in lint else data.get(name))

    all_select = set(_field("select") + _field("extend-select"))
    all_ignore = set(_field("ignore") + _field("extend-ignore"))

    if "S" in all_select or "ALL" in all_select:
        return (False, False) if "S" in all_ignore else (True, False)
    return False, False


def _inspect_ruff_file(trusted_root: Path, path: Path) -> tuple[bool, bool] | None:
    return _inspect_bounded_file(
        trusted_root, path, lambda data: _resolve_ruff_dict(as_dict(tomllib.loads(data.decode("utf-8-sig"))))
    )


def _check_ruff_section(data: dict[str, object], project_root: Path, repository_root: Path) -> tuple[bool, bool]:
    """Check Ruff configuration under ruff.toml, .ruff.toml, or tool.ruff.

    Returns (configured, indeterminate).
    """
    for name in (DOT_RUFF_TOML, RUFF_TOML):
        result = _inspect_ruff_file(project_root, project_root / name)
        if result is not None:
            return result

    tool = as_dict(data.get("tool"))
    ruff = as_dict(tool.get("ruff"))
    if not ruff:
        for name in (DOT_RUFF_TOML, RUFF_TOML):
            result = _inspect_ruff_file(repository_root, repository_root / name)
            if result is not None:
                return result
        return False, False

    return _resolve_ruff_dict(ruff)


def _is_matching_requirement(item: object) -> bool:
    return isinstance(item, str) and bool(REQUIREMENT_NAME_PATTERN.match(item.strip()))


def _check_deps_list(deps: object) -> bool:
    if isinstance(deps, (list, tuple)):
        return any(_is_matching_requirement(x) for x in cast(Sequence[object], deps))
    if isinstance(deps, dict):
        return any(_is_matching_requirement(k) for k in cast(dict[object, object], deps))
    return False


def _has_pyproject_deps(data: dict[str, Any], tool: dict[str, Any]) -> bool:
    project = as_dict(data.get("project"))
    if _check_deps_list(project.get("dependencies")) or any(
        _check_deps_list(g) for g in as_dict(project.get("optional-dependencies")).values()
    ):
        return True
    poetry = as_dict(tool.get("poetry"))
    if (
        _check_deps_list(poetry.get("dependencies"))
        or _check_deps_list(poetry.get("dev-dependencies"))
        or any(_check_deps_list(as_dict(g).get("dependencies")) for g in as_dict(poetry.get("group")).values())
    ):
        return True
    if any(_check_deps_list(g) for g in as_dict(data.get("dependency-groups")).values()):
        return True
    if _check_deps_list(as_dict(tool.get("uv")).get("dev-dependencies")):
        return True
    pdm_dict = as_dict(as_dict(tool.get("pdm")).get("dev-dependencies"))
    if any(_check_deps_list(g) for g in pdm_dict.values()) or _check_deps_list(
        as_dict(tool.get("pdm")).get("dev-dependencies")
    ):
        return True
    return any(
        _check_deps_list(as_dict(e).get("dependencies")) or _check_deps_list(as_dict(e).get("extra-dependencies"))
        for e in as_dict(as_dict(tool.get("hatch")).get("envs")).values()
    )


def _inspect_pyproject(
    trusted_root: Path,
    path: Path,
    repository_root: Path,
) -> tuple[bool, bool]:
    """(configured, indeterminate) for pyproject.toml."""

    def check(raw_bytes: bytes) -> tuple[bool, bool]:
        data = as_dict(tomllib.loads(raw_bytes.decode("utf-8-sig")))
        tool = as_dict(data.get("tool"))
        if "bandit" in tool:
            return True, False
        ruff_configured, ruff_indeterminate = _check_ruff_section(data, trusted_root, repository_root)
        if ruff_configured or _has_pyproject_deps(data, tool):
            return True, False
        return False, ruff_indeterminate

    return _inspect_bounded_file(trusted_root, path, check) or (False, False)


def _inspect_single_build_file(root: Path, bf: Path, repo_root: Path) -> tuple[bool, bool]:
    name = bf.name.lower()
    if name == PYPROJECT_TOML:
        return _inspect_pyproject(root, bf, repo_root)
    if name in (RUFF_TOML, DOT_RUFF_TOML):
        res = _inspect_ruff_file(root, bf)
        return res if res is not None else (False, False)
    if name == SETUP_CFG:
        return _inspect_setup_cfg(root, bf)
    if name == TOX_INI:
        return _inspect_tox_ini(root, bf)
    if name.startswith("requirements") and name.endswith(".txt"):
        return _inspect_requirements(root, bf)
    if name == PRE_COMMIT_CONFIG_YAML:
        return _inspect_pre_commit(root, bf)
    return False, False


def _inspect_build_files(root: Path, build_files: list[Path], repo_root: Path) -> tuple[bool, bool]:
    indeterminate = False
    for bf in build_files:
        configured, ind = _inspect_single_build_file(root, bf, repo_root)
        if configured:
            return True, False
        indeterminate |= ind
    return False, indeterminate


def _inspect_parent_pyproject(cand: Path, repo_root: Path) -> tuple[bool, bool]:
    cand_build = cand / PYPROJECT_TOML
    try:
        if not cand_build.exists():
            return False, False
        if not cand_build.is_file() or cand_build.is_symlink():
            return False, True
        return _inspect_pyproject(cand, cand_build, repo_root)
    except OSError:
        return False, True


def _inspect_candidate_requirements(cand: Path, repo_root: Path) -> tuple[bool, bool]:
    indeterminate = False
    try:
        with os.scandir(cand) as entries:
            for entry in entries:
                ename = entry.name.lower()
                if requirements_name(ename):
                    conf, ind = _inspect_requirements(repo_root, Path(entry.path))
                    if conf:
                        return True, False
                    indeterminate |= ind
    except OSError:
        indeterminate = True
    return False, indeterminate


def _inspect_candidate_files(cand: Path, repo_root: Path) -> tuple[bool, bool]:
    indeterminate = False
    for checker, path in (
        (_inspect_pre_commit, cand / PRE_COMMIT_CONFIG_YAML),
        (_inspect_setup_cfg, cand / SETUP_CFG),
        (_inspect_tox_ini, cand / TOX_INI),
    ):
        conf, ind = checker(repo_root, path)
        if conf:
            return True, False
        indeterminate |= ind

    for ruff_name in (DOT_RUFF_TOML, RUFF_TOML):
        if (res := _inspect_ruff_file(repo_root, cand / ruff_name)) is not None:
            if res[0]:
                return True, False
            indeterminate |= res[1]

    conf, ind = _inspect_candidate_requirements(cand, repo_root)
    return (True, False) if conf else (False, indeterminate | ind)


def _inspect_candidate_root(root: Path, cand: Path, repo_root: Path) -> tuple[bool, bool]:
    indeterminate = False
    if cand != root:
        conf, ind = _inspect_parent_pyproject(cand, repo_root)
        if conf:
            return True, False
        indeterminate |= ind

        conf, ind = _inspect_candidate_files(cand, repo_root)
        if conf:
            return True, False
        indeterminate |= ind

    sonar_configured, sonar_ind = _inspect_sonar_properties(repo_root, cand / "sonar-project.properties")
    if sonar_configured:
        return True, False
    indeterminate |= sonar_ind

    workflows_configured, workflows_ind = _inspect_workflows(repo_root, cand / ".github" / "workflows")
    if workflows_configured:
        return True, False
    indeterminate |= workflows_ind
    return False, indeterminate


class StaticSecurityAnalysisDetector:
    """Detects declarations for static security analyzers without running them."""

    def inspect(self, project_root: Path | None) -> Inspection:
        if project_root is None:
            return Inspection(State.NOT_APPLICABLE)
        try:
            root = Path(os.path.abspath(project_root))
            if not root.is_dir() or root.is_symlink() or root.is_junction():
                return Inspection(State.NOT_APPLICABLE)

            build_files = self._build_files(root)
            if not build_files:
                return Inspection(State.NOT_APPLICABLE)

            repo_root = _repository_root(root)
            candidate_roots = _repository_roots(root, repo_root)

            conf, ind = _inspect_build_files(root, build_files, repo_root)
            if conf:
                return Inspection(State.CONFIGURED)
            indeterminate = ind

            semgrep_configured, semgrep_ind = _inspect_semgrep_configs(repo_root, candidate_roots)
            if semgrep_configured:
                return Inspection(State.CONFIGURED)
            indeterminate |= semgrep_ind

            for cand in candidate_roots:
                conf, ind = _inspect_candidate_root(root, cand, repo_root)
                if conf:
                    return Inspection(State.CONFIGURED)
                indeterminate |= ind

            return Inspection(State.INDETERMINATE if indeterminate else State.NOT_CONFIGURED)
        except Exception:  # noqa: BLE001 - defensive: any unhandled failure is indeterminate
            return Inspection(State.INDETERMINATE)

    def _build_files(self, root: Path) -> list[Path]:
        names = (
            PYPROJECT_TOML,
            SETUP_CFG,
            "setup.py",
            TOX_INI,
            PRE_COMMIT_CONFIG_YAML,
            RUFF_TOML,
            DOT_RUFF_TOML,
        )
        files: list[Path] = []
        for name in names:
            try:
                candidate = root / name
                if candidate.exists():
                    files.append(candidate)
            except OSError:
                continue
        try:
            with os.scandir(root) as entries:
                for entry in entries:
                    ename = entry.name.lower()
                    if requirements_name(ename):
                        files.append(Path(entry.path))
        except OSError:
            pass
        return sorted(dict.fromkeys(files), key=lambda p: p.name)


class StaticSecurityAnalysisRule:
    """Rule SEC-STATIC-001 finding metadata and evidence limitation helper."""

    @classmethod
    def rule_definition(cls) -> RuleDefinition:
        return RuleDefinition(
            id=RULE_ID,
            name=TITLE,
            category=CATEGORY,
            severity=SEVERITY,
            description=DESCRIPTION,
            recommendation=RECOMMENDATION,
            learn_more_url=LEARN_MORE_URL,
        )

    @classmethod
    def finding(cls) -> Finding:
        return Finding(
            rule_id=RULE_ID,
            advisor="security",
            severity=SEVERITY,
            target="project",
            message=DETAIL,
            identity=RULE_ID,
        )

    @classmethod
    def add_assessment_limitation(cls, ev: dict[str, Any]) -> dict[str, Any]:
        return evidence(bool(ev.get("usable")), False, [*ev.get("limitations", []), LIMITATION_TEXT])
