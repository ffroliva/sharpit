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
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sharpit.engine.advisors.findings import Finding
from sharpit.engine.advisors.rules import RuleDefinition

RULE_ID = "SEC-STATIC-001"
TITLE = "No local static security analysis declared"
CATEGORY = "Static analysis"
SEVERITY = "INFO"
DETAIL = "No recognized static security analyzer declaration was found in the inspected local project files."
DESCRIPTION = (
    DETAIL + " External Maven parents, Gradle applied scripts or convention plugins, and organization-managed CI"
    " configuration are not resolved. sharpit does not run analyzers or verify execution."
)
RECOMMENDATION = (
    "Declare Bandit (e.g. in requirements, pyproject.toml, or setup.cfg), Semgrep, CodeQL, a"
    " sonar-project.properties file, or Ruff with the S rules selected in pyproject.toml. sharpit does not"
    " install or run analyzers."
)
LEARN_MORE_URL = "https://bandit.readthedocs.io/"
LIMITATION_TEXT = "Static analyzer configuration could not be assessed from bounded local files."

MAX_FILE_BYTES = 1_048_576  # 1 MiB
MAX_WORKFLOW_FILES = 64
MAX_PARENT_DEPTH = 5

KNOWN_WORKFLOW_ACTION = re.compile(
    r"(?i)^(?:github/codeql-action/(?:init|analyze)@\S+|"
    r"(?:semgrep|returntocorp)/semgrep-action\S*|"
    r"sonarsource/(?:sonarqube-scan-action|sonarcloud-github-action)\S*)$"
)
ENVIRONMENT_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
REQUIREMENT_NAME_PATTERN = re.compile(r"^(?:bandit|semgrep)(?:[\[<>=!~;].*)?$", re.IGNORECASE)

SEMGREP_CONFIG_RELPATHS = (
    Path(".semgrep.yml"),
    Path(".semgrep.yaml"),
    Path("semgrep.yml"),
    Path("semgrep.yaml"),
    Path(".semgrep") / "semgrep.yml",
    Path(".semgrep") / "config.yml",
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


def contains_symbolic_link(trusted_root: Path, candidate: Path) -> bool:
    """True if candidate climbs outside trusted_root or any segment along the path is a symlink/junction."""
    root = Path(os.path.abspath(trusted_root))
    target = Path(os.path.abspath(candidate))

    root_norm = os.path.normcase(str(root))
    target_norm = os.path.normcase(str(target))
    try:
        if os.path.commonpath([root_norm, target_norm]) != root_norm:
            return True
    except ValueError:
        return True

    current = root
    try:
        rel = target.relative_to(root)
    except ValueError:
        return True

    for segment in rel.parts:
        current = current / segment
        try:
            lst = os.lstat(current)
            if stat.S_ISLNK(lst.st_mode):
                return True
            if hasattr(os.path, "isjunction") and os.path.isjunction(current):
                return True
        except FileNotFoundError:
            return False
        except OSError:
            return True
    return False


def _validate_lstat(trusted_root: Path, path: Path) -> os.stat_result:
    if contains_symbolic_link(trusted_root, path):
        raise ValueError("Symlink or junction detected")
    try:
        lst = os.lstat(path)
    except OSError as exc:
        raise ValueError("Cannot stat file") from exc

    if stat.S_ISLNK(lst.st_mode) or (hasattr(os.path, "isjunction") and os.path.isjunction(path)):
        raise ValueError("File is symlink or junction")
    if not stat.S_ISREG(lst.st_mode):
        raise ValueError("File is not a regular file")
    if lst.st_size > MAX_FILE_BYTES:
        raise ValueError("File size exceeds inspection limit")
    return lst


def _read_fd_bounded(fd: int, lst: os.stat_result) -> bytes:
    fst = os.fstat(fd)
    if not stat.S_ISREG(fst.st_mode) or not os.path.samestat(lst, fst):
        raise ValueError("File changed or is not regular")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_FILE_BYTES:
            raise ValueError("File size exceeds inspection limit")
    return b"".join(chunks)


def read_bounded(trusted_root: Path, path: Path) -> bytes:
    """Read a regular file under trusted_root safely within MAX_FILE_BYTES without following symlinks/junctions."""
    lst = _validate_lstat(trusted_root, path)
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("Cannot open file") from exc
    try:
        return _read_fd_bounded(fd, lst)
    finally:
        os.close(fd)


def read_text(trusted_root: Path, path: Path) -> str:
    """Read bounded text as UTF-8; any decode error raises ValueError (becomes INDETERMINATE)."""
    data = read_bounded(trusted_root, path)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("File is not valid UTF-8") from exc


def strip_yaml_comments(text: str) -> str:
    """Strip YAML comments preserving line counts and quoted content (port of BootUI stripYamlComments)."""
    out: list[str] = []
    quote: str | None = None
    escaped = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if quote is not None:
            out.append(c)
            if quote == '"' and c == "\\" and not escaped:
                escaped = True
            elif c == quote and not escaped:
                if quote == "'" and i + 1 < n and text[i + 1] == "'":
                    i += 1
                    out.append(text[i])
                else:
                    quote = None
            else:
                escaped = False
        elif (c == '"' or c == "'") and (i == 0 or text[i - 1] != "\\"):
            quote = c
            out.append(c)
        elif c == "#" and (i == 0 or text[i - 1].isspace()):
            while i < n and text[i] != "\n":
                i += 1
            if i < n:
                out.append("\n")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _split_shell_commands(command: str) -> list[str]:
    statements: list[str] = []
    quote: str | None = None
    escaped = False
    start = 0
    n = len(command)
    for i in range(n):
        c = command[i]
        if quote is not None:
            if c == "\\" and quote == '"' and not escaped:
                escaped = True
            else:
                if c == quote and not escaped:
                    quote = None
                escaped = False
        elif c in ('"', "'"):
            quote = c
        elif c in (";", "|", "&"):
            statements.append(command[start:i])
            if i + 1 < n and ((c == "|" and command[i + 1] == "|") or (c == "&" and command[i + 1] == "&")):
                i += 1  # noqa: PLW2901
            start = i + 1
    statements.append(command[start:])
    return statements


def _shell_tokens(statement: str) -> list[str]:
    tokens: list[str] = []
    token: list[str] = []
    quote: str | None = None
    escaped = False
    for c in statement:
        if quote is not None:
            if c == "\\" and quote == '"' and not escaped:
                escaped = True
            elif c == quote and not escaped:
                quote = None
                escaped = False
            else:
                token.append(c)
                escaped = False
        elif c in ('"', "'"):
            quote = c
        elif c.isspace():
            if token:
                tokens.append("".join(token))
                token.clear()
        else:
            token.append(c)
    if token:
        tokens.append("".join(token))
    return tokens


def _is_semgrep_invocation(args: Sequence[str]) -> bool:
    if args and args[0] in ("scan", "ci"):
        return True
    for idx, arg in enumerate(args):
        if arg.startswith("--config=") and len(arg) > len("--config="):
            return True
        if arg in ("--config", "-f") and idx + 1 < len(args) and args[idx + 1].strip():
            return True
        if arg.startswith("-f") and len(arg) > 2:
            return True
    return False


def _has_known_workflow_command(command: str) -> bool:
    for stmt in _split_shell_commands(command):
        tokens = _shell_tokens(stmt)
        cmd_idx = 0
        while cmd_idx < len(tokens):
            tok = tokens[cmd_idx]
            if tok in ("env", "sudo", "time", "command", "exec") or ENVIRONMENT_ASSIGNMENT.match(tok):
                cmd_idx += 1
            else:
                break
        if cmd_idx >= len(tokens):
            continue
        executable = tokens[cmd_idx]
        name = executable.rpartition("/")[2].rpartition("\\")[2].lower()
        args = tokens[cmd_idx + 1 :]
        if name == "bandit" and (not args or not args[0].startswith("--version")):
            return True
        if name == "semgrep" and _is_semgrep_invocation(args):
            return True
        if name == "codeql" and args and args[0] in ("database", "analyze"):
            return True
        if name == "sonar-scanner":
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
        action = trimmed[len("uses:") :].strip()
        if len(action) >= 2 and action[0] in ('"', "'") and action[-1] == action[0]:
            action = action[1:-1]
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
        content = read_text(repository_root, Path(entry.path))
        cleaned = strip_yaml_comments(content)
        if _has_known_workflow_declaration(cleaned):
            return True, False
    except Exception:  # noqa: BLE001
        return False, True
    return False, False


def _inspect_workflows(repository_root: Path, directory: Path) -> tuple[bool, bool]:
    """(configured, indeterminate) for .github/workflows directory."""
    if contains_symbolic_link(repository_root, directory):
        return False, True
    try:
        if not directory.exists():
            return False, False
        if not directory.is_dir():
            return False, True
    except OSError:
        return False, True

    visited = 0
    indeterminate = False
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                name = entry.name.lower()
                if not (name.endswith(".yml") or name.endswith(".yaml")):
                    continue
                visited += 1
                if visited > MAX_WORKFLOW_FILES:
                    return False, True
                conf, ind = _inspect_workflow_entry(repository_root, entry)
                if conf:
                    return True, False
                indeterminate |= ind
    except OSError:
        return False, True
    return False, indeterminate


def _inspect_sonar_properties(repository_root: Path, path: Path) -> tuple[bool, bool]:
    """(configured, indeterminate) for sonar-project.properties."""
    if contains_symbolic_link(repository_root, path):
        return False, True
    try:
        if not path.exists():
            return False, False
        if not path.is_file():
            return False, True
        content = read_text(repository_root, path)
        return (True, False) if content.strip() else (False, False)
    except Exception:  # noqa: BLE001
        return False, True


def _inspect_semgrep_configs(repository_root: Path, candidate_roots: Sequence[Path]) -> tuple[bool, bool]:
    """(configured, indeterminate) for recognized Semgrep config files."""
    indeterminate = False
    for root in candidate_roots:
        for rel in SEMGREP_CONFIG_RELPATHS:
            cfg = root / rel
            if contains_symbolic_link(repository_root, cfg):
                indeterminate = True
                continue
            try:
                if not cfg.exists():
                    continue
                if not cfg.is_file():
                    indeterminate = True
                    continue
                content = read_text(repository_root, cfg)
                if content.strip():
                    return True, False
            except Exception:  # noqa: BLE001
                indeterminate = True
    return False, indeterminate


def _inspect_pre_commit(repository_root: Path, path: Path) -> tuple[bool, bool]:
    """(configured, indeterminate) for .pre-commit-config.yaml."""
    if contains_symbolic_link(repository_root, path):
        return False, True
    try:
        if not path.exists():
            return False, False
        if not path.is_file():
            return False, True
        text = strip_yaml_comments(read_text(repository_root, path))
        for line in text.splitlines():
            trimmed = line.strip().lower()
            if (
                "pycqa/bandit" in trimmed
                or "semgrep/semgrep" in trimmed
                or trimmed == "id: bandit"
                or trimmed == "id: semgrep"
            ):
                return True, False
        return False, False
    except Exception:  # noqa: BLE001
        return False, True


def _inspect_requirements(repository_root: Path, path: Path) -> tuple[bool, bool]:
    """(configured, indeterminate) for requirements*.txt files."""
    if contains_symbolic_link(repository_root, path):
        return False, True
    try:
        if not path.exists():
            return False, False
        if not path.is_file():
            return False, True
        text = read_text(repository_root, path)
        for line in text.splitlines():
            trimmed = line.partition("#")[0].strip()
            if not trimmed:
                continue
            if REQUIREMENT_NAME_PATTERN.match(trimmed):
                return True, False
        return False, False
    except Exception:  # noqa: BLE001
        return False, True


def _has_setup_cfg_bandit(parser: configparser.ConfigParser) -> bool:
    return any("bandit" in sec.lower() for sec in parser.sections())


def _has_setup_cfg_requirements(parser: configparser.ConfigParser) -> bool:
    if parser.has_section("options"):
        requires = parser.get("options", "install_requires", fallback="")
        for line in requires.splitlines():
            if REQUIREMENT_NAME_PATTERN.match(line.partition("#")[0].strip()):
                return True
    if parser.has_section("options.extras_require"):
        for _, val in parser.items("options.extras_require"):
            for line in val.splitlines():
                if REQUIREMENT_NAME_PATTERN.match(line.partition("#")[0].strip()):
                    return True
    return False


def _inspect_setup_cfg(repository_root: Path, path: Path) -> tuple[bool, bool]:
    """(configured, indeterminate) for setup.cfg."""
    if contains_symbolic_link(repository_root, path):
        return False, True
    try:
        if not path.exists():
            return False, False
        if not path.is_file():
            return False, True
        text = read_text(repository_root, path)
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(text)
        if _has_setup_cfg_bandit(parser) or _has_setup_cfg_requirements(parser):
            return True, False
        return False, False
    except Exception:  # noqa: BLE001 - malformed setup.cfg is indeterminate; never echoes content
        return False, True


def _inspect_tox_ini(repository_root: Path, path: Path) -> tuple[bool, bool]:
    """(configured, indeterminate) for tox.ini."""
    if contains_symbolic_link(repository_root, path):
        return False, True
    try:
        if not path.exists():
            return False, False
        if not path.is_file():
            return False, True
        text = read_text(repository_root, path)
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(text)
        for sec in parser.sections():
            deps = parser.get(sec, "deps", fallback="")
            for line in deps.splitlines():
                if REQUIREMENT_NAME_PATTERN.match(line.partition("#")[0].strip()):
                    return True, False
            commands = parser.get(sec, "commands", fallback="")
            for line in commands.splitlines():
                if _has_known_workflow_command(line.strip()):
                    return True, False
        return False, False
    except Exception:  # noqa: BLE001
        return False, True


def _as_dict(val: object) -> dict[str, object]:
    if isinstance(val, dict):
        d = cast("dict[object, object]", val)
        return {str(k): v for k, v in d.items()}
    return {}


def _as_str_list(val: object) -> list[str]:
    if isinstance(val, (list, tuple)):
        s = cast("Sequence[object]", val)
        return [str(x) for x in s]
    return []


def _check_ruff_section(data: dict[str, object], project_root: Path, repository_root: Path) -> tuple[bool, bool]:
    """Check Ruff configuration under tool.ruff and tool.ruff.lint.

    Returns (configured, indeterminate).
    """
    ruff_candidates = (
        project_root / "ruff.toml",
        project_root / ".ruff.toml",
        repository_root / "ruff.toml",
        repository_root / ".ruff.toml",
    )
    for candidate in ruff_candidates:
        try:
            if candidate.exists():
                return False, True
        except OSError:
            return False, True

    tool = _as_dict(data.get("tool"))
    ruff = _as_dict(tool.get("ruff"))
    if not ruff:
        return False, False

    if "extend" in ruff:
        return False, True

    lint = _as_dict(ruff.get("lint"))
    if "extend" in lint:
        return False, True

    select: list[str] = _as_str_list(ruff.get("select"))
    ignore: list[str] = _as_str_list(ruff.get("ignore"))
    extend_select: list[str] = _as_str_list(ruff.get("extend-select"))
    extend_ignore: list[str] = _as_str_list(ruff.get("extend-ignore"))

    if lint:
        select.extend(_as_str_list(lint.get("select")))
        ignore.extend(_as_str_list(lint.get("ignore")))
        extend_select.extend(_as_str_list(lint.get("extend-select")))
        extend_ignore.extend(_as_str_list(lint.get("extend-ignore")))

    all_select = set(select + extend_select)
    all_ignore = set(ignore + extend_ignore)

    has_s = "S" in all_select
    has_all = "ALL" in all_select
    s_ignored = "S" in all_ignore

    if has_s:
        return (False, False) if s_ignored else (True, False)
    if has_all:
        return (False, False) if s_ignored else (True, False)
    return False, False


def _check_deps_list(deps: object) -> bool:
    if isinstance(deps, (list, tuple)):
        s = cast("Sequence[object]", deps)
        for item in s:
            if isinstance(item, str) and REQUIREMENT_NAME_PATTERN.match(item.strip()):
                return True
    elif isinstance(deps, dict):
        d = cast("dict[object, object]", deps)
        for key in d:
            if isinstance(key, str) and REQUIREMENT_NAME_PATTERN.match(key.strip()):
                return True
    return False


def _has_pyproject_project_deps(project: dict[str, Any]) -> bool:
    if _check_deps_list(project.get("dependencies")):
        return True
    optional = _as_dict(project.get("optional-dependencies"))
    return any(_check_deps_list(group) for group in optional.values())


def _has_pyproject_poetry_deps(tool: dict[str, Any]) -> bool:
    poetry = _as_dict(tool.get("poetry"))
    if not poetry:
        return False
    if _check_deps_list(poetry.get("dependencies")) or _check_deps_list(poetry.get("dev-dependencies")):
        return True
    group = _as_dict(poetry.get("group"))
    return any(_check_deps_list(_as_dict(grp).get("dependencies")) for grp in group.values())


def _inspect_pyproject(
    trusted_root: Path,
    path: Path,
    repository_root: Path,
) -> tuple[bool, bool]:
    """(configured, indeterminate) for pyproject.toml."""
    if contains_symbolic_link(trusted_root, path):
        return False, True
    try:
        if not path.exists():
            return False, False
        if not path.is_file():
            return False, True
        raw_bytes = read_bounded(trusted_root, path)
        import tomllib

        raw_data = tomllib.loads(raw_bytes.decode("utf-8"))
        data = _as_dict(raw_data)
    except Exception:  # noqa: BLE001 - decode error or TOML error
        return False, True

    tool = _as_dict(data.get("tool"))
    if "bandit" in tool:
        return True, False
    ruff_configured, ruff_indeterminate = _check_ruff_section(data, trusted_root, repository_root)
    if ruff_configured:
        return True, False
    if ruff_indeterminate:
        return False, True

    project = _as_dict(data.get("project"))
    if project and _has_pyproject_project_deps(project):
        return True, False
    if _has_pyproject_poetry_deps(tool):
        return True, False

    return False, False


def _inspect_single_build_file(root: Path, bf: Path, repo_root: Path) -> tuple[bool, bool]:
    name = bf.name.lower()
    if name == "pyproject.toml":
        return _inspect_pyproject(root, bf, repo_root)
    if name == "setup.cfg":
        return _inspect_setup_cfg(root, bf)
    if name == "tox.ini":
        return _inspect_tox_ini(root, bf)
    if name.startswith("requirements") and name.endswith(".txt"):
        return _inspect_requirements(root, bf)
    if name == ".pre-commit-config.yaml":
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
    cand_build = cand / "pyproject.toml"
    try:
        if not cand_build.exists():
            return False, False
        if not cand_build.is_file() or cand_build.is_symlink():
            return False, True
        return _inspect_pyproject(cand, cand_build, repo_root)
    except OSError:
        return False, True


def _inspect_candidate_root(root: Path, cand: Path, repo_root: Path) -> tuple[bool, bool]:
    indeterminate = False
    if cand != root:
        conf, ind = _inspect_parent_pyproject(cand, repo_root)
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
            if not root.is_dir() or root.is_symlink() or (hasattr(root, "is_junction") and root.is_junction()):
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
        files: list[Path] = []
        for name in ("pyproject.toml", "setup.cfg", "tox.ini", ".pre-commit-config.yaml"):
            candidate = root / name
            try:
                if candidate.exists():
                    files.append(candidate)
            except OSError:
                continue
        try:
            with os.scandir(root) as entries:
                for entry in entries:
                    ename = entry.name.lower()
                    if ename.startswith("requirements") and ename.endswith(".txt"):
                        files.append(Path(entry.path))
        except OSError:
            pass
        return sorted(dict.fromkeys(files), key=lambda p: p.name)


class StaticSecurityAnalysisRule:
    """Rule SEC-STATIC-001 finding metadata and evidence limitation helper."""

    RULE_ID = RULE_ID
    NAME = TITLE
    CATEGORY = CATEGORY
    SEVERITY = SEVERITY
    DETAIL = DETAIL
    DESCRIPTION = DESCRIPTION
    RECOMMENDATION = RECOMMENDATION
    LEARN_MORE_URL = LEARN_MORE_URL

    @classmethod
    def rule_definition(cls) -> RuleDefinition:
        return RuleDefinition(
            id=cls.RULE_ID,
            name=cls.NAME,
            category=cls.CATEGORY,
            severity=cls.SEVERITY,
            description=cls.DESCRIPTION,
            recommendation=cls.RECOMMENDATION,
            learn_more_url=cls.LEARN_MORE_URL,
        )

    @classmethod
    def finding(cls) -> Finding:
        return Finding(
            rule_id=cls.RULE_ID,
            advisor="security",
            severity=cls.SEVERITY,
            target="project",
            message=cls.DETAIL,
            identity=cls.RULE_ID,
        )

    @classmethod
    def add_assessment_limitation(cls, ev: dict[str, Any]) -> dict[str, Any]:
        limitations = list(ev.get("limitations", []))
        limitations.append(LIMITATION_TEXT)
        return {
            "usable": ev.get("usable", False),
            "coverageComplete": False,
            "limitations": limitations,
        }
