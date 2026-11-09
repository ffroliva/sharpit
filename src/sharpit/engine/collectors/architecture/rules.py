"""Architecture advisor rule catalog and evaluators (spec §5.5; BootUI 2.2.0 ARCH-* rules)."""

from __future__ import annotations

import ast
from collections.abc import Sequence

from sharpit.engine.advisors.findings import Finding
from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.appsource import ModuleInfo, SourceIndex
from sharpit.engine.collectors.architecture.contracts import Contract
from sharpit.engine.collectors.architecture.graph import ImportEdge, ImportGraph

ADVISOR = "architecture"
_PACKAGE_STRUCTURE = "Package structure"
_CODING_PRACTICES = "Coding practices"
_SHARPIT_URL = "https://github.com/ffroliva/sharpit"

RULES: tuple[RuleDefinition, ...] = (
    RuleDefinition(
        id="ARCH-PKG-001",
        name="Packages should be free of cycles",
        category=_PACKAGE_STRUCTURE,
        severity="HIGH",
        description="Circular dependencies between packages make code difficult to understand, test, and maintain.",
        recommendation=(
            "Break circular package dependencies by introducing interfaces or refactoring shared code into a common"
            " package."
        ),
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-MOD-001",
        name="Internal packages should not be accessed from other modules",
        category=_PACKAGE_STRUCTURE,
        severity="HIGH",
        description="Modules must not import private or internal modules from outside their parent package.",
        recommendation="Use only public module interfaces; avoid importing from _private modules or internal packages.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-CODE-001",
        name="Classes should not access standard streams",
        category=_CODING_PRACTICES,
        severity="LOW",
        description="Writing directly to standard streams bypasses logging configurations and formatting.",
        recommendation="Use a configured logger instead of print() or sys.stdout/sys.stderr.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-CODE-002",
        name="Classes should not throw generic exceptions",
        category=_CODING_PRACTICES,
        severity="LOW",
        description=(
            "Raising generic Exception or BaseException obscures error causes and hinders specific error handling."
        ),
        recommendation="Define or use specific exception subclasses describing the error condition.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-CODE-004",
        name="Classes should not use Joda-Time",
        category=_CODING_PRACTICES,
        severity="INFO",
        description=(
            "Legacy third-party timezone libraries such as pytz are superseded by the standard zoneinfo module."
        ),
        recommendation="Migrate from pytz to standard library zoneinfo.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-CODE-006",
        name="Classes should not forcibly terminate the JVM",
        category=_CODING_PRACTICES,
        severity="HIGH",
        description="Application classes outside entry points should not call sys.exit, os._exit, exit, or quit.",
        recommendation="Raise an appropriate exception or return a status code rather than terminating the process.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-CODE-007",
        name="Classes should not access JDK-internal APIs",
        category=_CODING_PRACTICES,
        severity="MEDIUM",
        description=(
            "Importing private symbols from third-party libraries creates brittle dependencies on internal"
            " implementation details."
        ),
        recommendation="Depend only on public APIs of third-party libraries.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-CODE-008",
        name="Classes should not use legacy date and time classes",
        category=_CODING_PRACTICES,
        severity="INFO",
        description="datetime.utcnow() and utcfromtimestamp() are deprecated in Python 3.12.",
        recommendation="Use datetime.now(timezone.utc) or datetime.fromtimestamp(..., tz=timezone.utc).",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-CODE-010",
        name="Exceptions should be named ending with Exception",
        category=_CODING_PRACTICES,
        severity="INFO",
        description="PEP 8 recommends naming exception classes with an Error or Exception suffix.",
        recommendation="Rename exception classes to end with Error or Exception.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-CODE-012",
        name="Loggers should be private final or container-managed",
        category=_CODING_PRACTICES,
        severity="LOW",
        description="Loggers should be acquired using logging.getLogger(__name__) to maintain proper hierarchy.",
        recommendation="Use logging.getLogger(__name__) instead of root logger or hardcoded string literals.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-CODE-013",
        name="Application classes should not depend on test frameworks",
        category=_CODING_PRACTICES,
        severity="MEDIUM",
        description=(
            "Production application code must not import test libraries such as pytest, unittest.mock, or hypothesis."
        ),
        recommendation="Remove test framework imports from application code; move test utilities to test packages.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-CODE-014",
        name="Classes should not have public mutable static fields",
        category=_CODING_PRACTICES,
        severity="MEDIUM",
        description="Functions rebinding module-level globals introduce mutable shared state and concurrency hazards.",
        recommendation="Encapsulate mutable state in explicit classes or pass state via function arguments.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-CODE-017",
        name="Classes should not directly instantiate Thread",
        category=_CODING_PRACTICES,
        severity="MEDIUM",
        description="Directly creating threading.Thread instances bypasses concurrency limits and thread pools.",
        recommendation="Use concurrent.futures.ThreadPoolExecutor or async tasks instead of raw threads.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-CODE-018",
        name="Assertions should have a detail message",
        category=_CODING_PRACTICES,
        severity="INFO",
        description=(
            "Assertions in production code without messages provide unhelpful traceback diagnostics and may be stripped"
            " under -O."
        ),
        recommendation="Provide an informative message in assert statements or use explicit conditional checks.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-SPRING-002",
        name="Controllers should not depend on repositories",
        category="Layering",
        severity="LOW",
        description=(
            "Route handlers and controllers should access data through service layers rather than repositories"
            " directly."
        ),
        recommendation="Introduce a service layer between controllers and repositories.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-SPRING-003",
        name="Repositories should not depend on controllers",
        category="Layering",
        severity="MEDIUM",
        description="Data repositories must not import or depend on controller or router modules.",
        recommendation="Remove controller dependencies from repository modules.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-SPRING-006",
        name="Services should not depend on controllers",
        category="Layering",
        severity="MEDIUM",
        description="Business services must not depend on controller or web presentation modules.",
        recommendation="Remove controller imports from service modules.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-SPRING-007",
        name="Repositories should not depend on services",
        category="Layering",
        severity="MEDIUM",
        description="Data access repositories should not depend on higher-level service layer modules.",
        recommendation="Invert dependencies so services call repositories, not vice versa.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-SPRING-008",
        name="Services and repositories should not depend on web request types",
        category="Layering",
        severity="MEDIUM",
        description=(
            "Domain services and repositories should be transport-agnostic and not import Request or Response objects."
        ),
        recommendation="Pass domain parameters or DTOs to services instead of framework Request types.",
        learn_more_url=_SHARPIT_URL,
    ),
    RuleDefinition(
        id="ARCH-PY-001",
        name="Packages should respect declared import-linter contracts",
        category=_PACKAGE_STRUCTURE,
        severity="HIGH",
        description=(
            "Module dependencies violate architectural layering or forbidden import contracts declared in"
            " pyproject.toml."
        ),
        recommendation="Restructure imports to adhere to the project's declared import-linter contracts.",
        learn_more_url=_SHARPIT_URL,
    ),
)

_CONTROLLER_PKGS = frozenset({"routers", "api", "endpoints", "controllers"})
_REPO_PKGS = frozenset({"repositories", "crud"})
_SERVICE_PKGS = frozenset({"services"})
_TEST_FRAMEWORKS = frozenset({"pytest", "unittest.mock", "hypothesis"})
_WEB_MODULES = frozenset({"fastapi", "starlette.requests", "starlette.responses"})


def _eval_cycles(graph: ImportGraph, out: list[Finding]) -> None:
    cycles = graph.find_package_cycles() or graph.find_cycles()
    for cycle in cycles:
        chain = " -> ".join(cycle.members) + f" -> {cycle.members[0]}"
        target = f"{cycle.members[0]} cycle"
        msg = f"Circular package dependency: {chain}"
        out.append(Finding("ARCH-PKG-001", ADVISOR, "HIGH", target, msg))


def _eval_internal_imports(graph: ImportGraph, out: list[Finding]) -> None:
    for src_mod, edges in graph.edges.items():
        src_pkg = src_mod.rpartition(".")[0]
        for edge in edges:
            parts = edge.target.split(".")
            if any(p == "internal" or (p.startswith("_") and not p.startswith("__")) for p in parts):
                tgt_pkg = edge.target.rpartition(".")[0]
                if not (edge.target.startswith(f"{src_pkg}.") or src_pkg == tgt_pkg):
                    msg = f"{src_mod} ({edge.path.name}:{edge.line}) imports internal module {edge.target}"
                    out.append(Finding("ARCH-MOD-001", ADVISOR, "HIGH", f"{src_mod}:{edge.line}", msg))


def _eval_module_ast(
    mod_name: str,
    mod_info: ModuleInfo,
    base_pkgs: set[str],
    out: dict[str, list[Finding]],
) -> None:
    tree = mod_info.tree
    is_main = mod_name == "__main__" or mod_name.endswith(".__main__")
    parts = set(mod_name.split("."))

    for node in ast.walk(tree):
        _check_standard_streams(mod_name, node, out.setdefault("ARCH-CODE-001", []))
        _check_generic_exceptions(mod_name, node, out.setdefault("ARCH-CODE-002", []))
        _check_joda_time(mod_name, node, out.setdefault("ARCH-CODE-004", []))
        if not is_main:
            _check_terminate_jvm(mod_name, node, out.setdefault("ARCH-CODE-006", []))
        _check_jdk_internal_apis(mod_name, node, base_pkgs, out.setdefault("ARCH-CODE-007", []))
        _check_legacy_datetime(mod_name, node, out.setdefault("ARCH-CODE-008", []))
        _check_exception_naming(mod_name, node, out.setdefault("ARCH-CODE-010", []))
        _check_loggers_private(mod_name, node, out.setdefault("ARCH-CODE-012", []))
        if not (parts & {"tests", "test"}):
            _check_test_frameworks(mod_name, node, out.setdefault("ARCH-CODE-013", []))
        _check_mutable_globals(mod_name, node, out.setdefault("ARCH-CODE-014", []))
        _check_instantiate_thread(mod_name, node, out.setdefault("ARCH-CODE-017", []))
        _check_assert_detail(mod_name, node, out.setdefault("ARCH-CODE-018", []))
        if parts & (_SERVICE_PKGS | _REPO_PKGS):
            _check_web_transport_imports(mod_name, node, out.setdefault("ARCH-SPRING-008", []))


def _check_standard_streams(mod_name: str, node: ast.AST, out: list[Finding]) -> None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
        out.append(
            Finding("ARCH-CODE-001", ADVISOR, "LOW", f"{mod_name}:{node.lineno}", f"{mod_name}:{node.lineno} print()")
        )
    elif (
        isinstance(node, ast.Attribute)
        and node.attr in ("stdout", "stderr")
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    ):
        out.append(
            Finding(
                "ARCH-CODE-001",
                ADVISOR,
                "LOW",
                f"{mod_name}:{node.lineno}",
                f"{mod_name}:{node.lineno} sys.{node.attr}",
            )
        )


def _check_generic_exceptions(mod_name: str, node: ast.AST, out: list[Finding]) -> None:
    if isinstance(node, ast.Raise) and node.exc:
        exc_id: str | None = None
        if isinstance(node.exc, ast.Name):
            exc_id = node.exc.id
        elif isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name):
            exc_id = node.exc.func.id
        if exc_id in ("Exception", "BaseException"):
            out.append(
                Finding(
                    "ARCH-CODE-002",
                    ADVISOR,
                    "LOW",
                    f"{mod_name}:{node.lineno}",
                    f"{mod_name}:{node.lineno} raises {exc_id}",
                )
            )


def _check_joda_time(mod_name: str, node: ast.AST, out: list[Finding]) -> None:
    if isinstance(node, ast.Import):
        out.extend(
            Finding(
                "ARCH-CODE-004", ADVISOR, "INFO", f"{mod_name}:{node.lineno}", f"{mod_name}:{node.lineno} pytz import"
            )
            for alias in node.names
            if alias.name == "pytz" or alias.name.startswith("pytz.")
        )
    elif (
        isinstance(node, ast.ImportFrom) and node.module and (node.module == "pytz" or node.module.startswith("pytz."))
    ):
        out.append(
            Finding(
                "ARCH-CODE-004", ADVISOR, "INFO", f"{mod_name}:{node.lineno}", f"{mod_name}:{node.lineno} pytz import"
            )
        )


def _check_terminate_jvm(mod_name: str, node: ast.AST, out: list[Finding]) -> None:
    if isinstance(node, ast.Call):
        is_exit = False
        name = ""
        if isinstance(node.func, ast.Name) and node.func.id in ("exit", "quit"):
            is_exit = True
            name = node.func.id
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in ("exit", "_exit")
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in ("sys", "os")
        ):
            is_exit = True
            name = f"{node.func.value.id}.{node.func.attr}"
        if is_exit:
            out.append(
                Finding(
                    "ARCH-CODE-006",
                    ADVISOR,
                    "HIGH",
                    f"{mod_name}:{node.lineno}",
                    f"{mod_name}:{node.lineno} calls {name}()",
                )
            )


def _check_jdk_internal_apis(mod_name: str, node: ast.AST, base_pkgs: set[str], out: list[Finding]) -> None:
    if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        top = node.module.partition(".")[0]
        if top not in base_pkgs and top != "__future__":
            parts = node.module.split(".")
            if any(p.startswith("_") and not p.startswith("__") for p in parts):
                out.append(
                    Finding(
                        "ARCH-CODE-007",
                        ADVISOR,
                        "MEDIUM",
                        f"{mod_name}:{node.lineno}",
                        f"{mod_name}:{node.lineno} imports private {node.module}",
                    )
                )
            else:
                out.extend(
                    Finding(
                        "ARCH-CODE-007",
                        ADVISOR,
                        "MEDIUM",
                        f"{mod_name}:{node.lineno}",
                        f"{mod_name}:{node.lineno} imports private {alias.name} from {node.module}",
                    )
                    for alias in node.names
                    if alias.name.startswith("_") and not alias.name.startswith("__")
                )


def _check_legacy_datetime(mod_name: str, node: ast.AST, out: list[Finding]) -> None:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("utcnow", "utcfromtimestamp")
    ):
        out.append(
            Finding(
                "ARCH-CODE-008",
                ADVISOR,
                "INFO",
                f"{mod_name}:{node.lineno}",
                f"{mod_name}:{node.lineno} calls {node.func.attr}()",
            )
        )


def _check_exception_naming(mod_name: str, node: ast.AST, out: list[Finding]) -> None:
    if isinstance(node, ast.ClassDef):
        is_exc = any(
            isinstance(b, ast.Name)
            and (b.id in ("Exception", "BaseException") or b.id.endswith(("Error", "Exception")))
            for b in node.bases
        )
        if is_exc and not node.name.endswith(("Error", "Exception")):
            out.append(
                Finding(
                    "ARCH-CODE-010",
                    ADVISOR,
                    "INFO",
                    f"{mod_name}:{node.lineno}",
                    f"{mod_name}:{node.lineno} exception {node.name} not named Error/Exception",
                )
            )


def _check_loggers_private(mod_name: str, node: ast.AST, out: list[Finding]) -> None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "getLogger":
        if not node.args:
            out.append(
                Finding(
                    "ARCH-CODE-012",
                    ADVISOR,
                    "LOW",
                    f"{mod_name}:{node.lineno}",
                    f"{mod_name}:{node.lineno} getLogger() without name",
                )
            )
        elif len(node.args) > 0 and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            out.append(
                Finding(
                    "ARCH-CODE-012",
                    ADVISOR,
                    "LOW",
                    f"{mod_name}:{node.lineno}",
                    f"{mod_name}:{node.lineno} getLogger() with literal string",
                )
            )


def _check_test_frameworks(mod_name: str, node: ast.AST, out: list[Finding]) -> None:
    if isinstance(node, ast.Import):
        out.extend(
            Finding(
                "ARCH-CODE-013",
                ADVISOR,
                "MEDIUM",
                f"{mod_name}:{node.lineno}",
                f"{mod_name}:{node.lineno} imports test library {alias.name}",
            )
            for alias in node.names
            if any(alias.name == tf or alias.name.startswith(f"{tf}.") for tf in _TEST_FRAMEWORKS)
        )
    elif (
        isinstance(node, ast.ImportFrom)
        and node.module
        and any(node.module == tf or node.module.startswith(f"{tf}.") for tf in _TEST_FRAMEWORKS)
    ):
        out.append(
            Finding(
                "ARCH-CODE-013",
                ADVISOR,
                "MEDIUM",
                f"{mod_name}:{node.lineno}",
                f"{mod_name}:{node.lineno} imports from test library {node.module}",
            )
        )


def _check_mutable_globals(mod_name: str, node: ast.AST, out: list[Finding]) -> None:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        for child in ast.walk(node):
            if isinstance(child, ast.Global):
                out.extend(
                    Finding(
                        "ARCH-CODE-014",
                        ADVISOR,
                        "MEDIUM",
                        f"{mod_name}:{child.lineno}",
                        f"{mod_name}:{child.lineno} rebinds public global {name}",
                    )
                    for name in child.names
                    if not name.startswith("_")
                )


def _check_instantiate_thread(mod_name: str, node: ast.AST, out: list[Finding]) -> None:
    if isinstance(node, ast.Call):
        is_thread = False
        if isinstance(node.func, ast.Attribute) and node.func.attr == "Thread":
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "threading":
                is_thread = True
        elif isinstance(node.func, ast.Name) and node.func.id == "Thread":
            is_thread = True
        if is_thread:
            out.append(
                Finding(
                    "ARCH-CODE-017",
                    ADVISOR,
                    "MEDIUM",
                    f"{mod_name}:{node.lineno}",
                    f"{mod_name}:{node.lineno} directly instantiates Thread",
                )
            )


def _check_assert_detail(mod_name: str, node: ast.AST, out: list[Finding]) -> None:
    if isinstance(node, ast.Assert) and node.msg is None:
        out.append(
            Finding(
                "ARCH-CODE-018",
                ADVISOR,
                "INFO",
                f"{mod_name}:{node.lineno}",
                f"{mod_name}:{node.lineno} assert without message",
            )
        )


def _check_web_transport_imports(mod_name: str, node: ast.AST, out: list[Finding]) -> None:
    if isinstance(node, ast.Import):
        out.extend(
            Finding(
                "ARCH-SPRING-008",
                ADVISOR,
                "MEDIUM",
                f"{mod_name}:{node.lineno}",
                f"{mod_name}:{node.lineno} imports web transport {alias.name}",
            )
            for alias in node.names
            if alias.name in _WEB_MODULES or alias.name == "fastapi"
        )
    elif isinstance(node, ast.ImportFrom) and node.module and (node.module in _WEB_MODULES or node.module == "fastapi"):
        out.append(
            Finding(
                "ARCH-SPRING-008",
                ADVISOR,
                "MEDIUM",
                f"{mod_name}:{node.lineno}",
                f"{mod_name}:{node.lineno} imports web transport from {node.module}",
            )
        )


def _eval_edge(src_mod: str, src_parts: set[str], edge: ImportEdge, out: dict[str, list[Finding]]) -> None:
    tgt_parts = set(edge.target.split("."))
    if (src_parts & _CONTROLLER_PKGS) and (tgt_parts & _REPO_PKGS):
        out.setdefault("ARCH-SPRING-002", []).append(
            Finding(
                "ARCH-SPRING-002",
                ADVISOR,
                "LOW",
                f"{src_mod}:{edge.line}",
                f"Controller {src_mod} imports repository {edge.target}",
            )
        )
    if (src_parts & _REPO_PKGS) and (tgt_parts & _CONTROLLER_PKGS):
        out.setdefault("ARCH-SPRING-003", []).append(
            Finding(
                "ARCH-SPRING-003",
                ADVISOR,
                "MEDIUM",
                f"{src_mod}:{edge.line}",
                f"Repository {src_mod} imports controller {edge.target}",
            )
        )
    if (src_parts & _SERVICE_PKGS) and (tgt_parts & _CONTROLLER_PKGS):
        out.setdefault("ARCH-SPRING-006", []).append(
            Finding(
                "ARCH-SPRING-006",
                ADVISOR,
                "MEDIUM",
                f"{src_mod}:{edge.line}",
                f"Service {src_mod} imports controller {edge.target}",
            )
        )
    if (src_parts & _REPO_PKGS) and (tgt_parts & _SERVICE_PKGS):
        out.setdefault("ARCH-SPRING-007", []).append(
            Finding(
                "ARCH-SPRING-007",
                ADVISOR,
                "MEDIUM",
                f"{src_mod}:{edge.line}",
                f"Repository {src_mod} imports service {edge.target}",
            )
        )


def _eval_layering(graph: ImportGraph, out: dict[str, list[Finding]]) -> None:
    for src_mod, edges in graph.edges.items():
        src_parts = set(src_mod.split("."))
        for edge in edges:
            _eval_edge(src_mod, src_parts, edge, out)


def _within(module: str, prefixes: Sequence[str]) -> bool:
    return any(module == p or module.startswith(f"{p}.") for p in prefixes)


def _layer(module: str, layers: Sequence[str]) -> int | None:
    return next((i for i, layer in enumerate(layers) if _within(module, (layer,))), None)


def _contract_breach(contract: Contract, src_mod: str, tgt_mod: str) -> str | None:
    """How importing ``tgt_mod`` from ``src_mod`` breaks ``contract``, or None."""
    if contract.contract_type == "layers":
        src_idx, tgt_idx = _layer(src_mod, contract.layers), _layer(tgt_mod, contract.layers)
        if src_idx is not None and tgt_idx is not None and src_idx > tgt_idx:
            return "imports higher layer"
    elif (
        contract.contract_type == "forbidden"
        and _within(src_mod, contract.source_modules)
        and _within(tgt_mod, contract.forbidden_modules)
    ):
        return "imports forbidden"
    return None


def _eval_contracts(graph: ImportGraph, contracts: Sequence[Contract], out: list[Finding]) -> None:
    for contract in contracts:
        for src_mod, edges in graph.edges.items():
            for edge in edges:
                breach = _contract_breach(contract, src_mod, edge.target)
                if breach is None:
                    continue
                msg = (
                    f"Contract {contract.name!r} violated: {src_mod} ({edge.path.name}:{edge.line}) "
                    f"{breach} {edge.target}"
                )
                out.append(Finding("ARCH-PY-001", ADVISOR, "HIGH", f"{src_mod}:{edge.line}", msg))


def evaluate_rules(
    index: SourceIndex,
    graph: ImportGraph,
    contracts: Sequence[Contract] = (),
) -> dict[str, list[Finding]]:
    """Evaluate architecture rules against the indexed application code and import graph."""
    findings: dict[str, list[Finding]] = {}

    _eval_cycles(graph, findings.setdefault("ARCH-PKG-001", []))
    _eval_internal_imports(graph, findings.setdefault("ARCH-MOD-001", []))

    base_pkgs = {m.partition(".")[0] for m in index.modules if m}
    for mod_name, mod_info in index.modules.items():
        _eval_module_ast(mod_name, mod_info, base_pkgs, findings)

    _eval_layering(graph, findings)
    _eval_contracts(graph, contracts, findings.setdefault("ARCH-PY-001", []))

    return {k: v for k, v in findings.items() if v}
