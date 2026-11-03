"""Architecture advisor rule catalog (spec §5.5; BootUI 2.2.0 ARCH-* rules)."""

from __future__ import annotations

from collections.abc import Sequence

from sharpit.engine.advisors.rules import RuleDefinition

RULES: tuple[RuleDefinition, ...] = (
    RuleDefinition(
        id="ARCH-PKG-001",
        name="Packages should be free of cycles",
        category="Package structure",
        severity="HIGH",
        description="Circular dependencies between packages make code difficult to understand, test, and maintain.",
        recommendation=(
            "Break circular package dependencies by introducing interfaces or refactoring shared code into a common"
            " package."
        ),
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-MOD-001",
        name="Internal packages should not be accessed from other modules",
        category="Package structure",
        severity="HIGH",
        description="Modules must not import private or internal modules from outside their parent package.",
        recommendation="Use only public module interfaces; avoid importing from _private modules or internal packages.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-CODE-001",
        name="Classes should not access standard streams",
        category="Coding practices",
        severity="LOW",
        description="Writing directly to standard streams bypasses logging configurations and formatting.",
        recommendation="Use a configured logger instead of print() or sys.stdout/sys.stderr.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-CODE-002",
        name="Classes should not throw generic exceptions",
        category="Coding practices",
        severity="LOW",
        description=(
            "Raising generic Exception or BaseException obscures error causes and hinders specific error handling."
        ),
        recommendation="Define or use specific exception subclasses describing the error condition.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-CODE-004",
        name="Classes should not use Joda-Time",
        category="Coding practices",
        severity="INFO",
        description=(
            "Legacy third-party timezone libraries such as pytz are superseded by the standard zoneinfo module."
        ),
        recommendation="Migrate from pytz to standard library zoneinfo.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-CODE-006",
        name="Classes should not forcibly terminate the JVM",
        category="Coding practices",
        severity="HIGH",
        description="Application classes outside entry points should not call sys.exit, os._exit, exit, or quit.",
        recommendation="Raise an appropriate exception or return a status code rather than terminating the process.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-CODE-007",
        name="Classes should not access JDK-internal APIs",
        category="Coding practices",
        severity="MEDIUM",
        description=(
            "Importing private symbols from third-party libraries creates brittle dependencies on internal"
            " implementation details."
        ),
        recommendation="Depend only on public APIs of third-party libraries.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-CODE-008",
        name="Classes should not use legacy date and time classes",
        category="Coding practices",
        severity="INFO",
        description="datetime.utcnow() and utcfromtimestamp() are deprecated in Python 3.12.",
        recommendation="Use datetime.now(timezone.utc) or datetime.fromtimestamp(..., tz=timezone.utc).",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-CODE-010",
        name="Exceptions should be named ending with Exception",
        category="Coding practices",
        severity="INFO",
        description="PEP 8 recommends naming exception classes with an Error or Exception suffix.",
        recommendation="Rename exception classes to end with Error or Exception.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-CODE-012",
        name="Loggers should be private final or container-managed",
        category="Coding practices",
        severity="LOW",
        description="Loggers should be acquired using logging.getLogger(__name__) to maintain proper hierarchy.",
        recommendation="Use logging.getLogger(__name__) instead of root logger or hardcoded string literals.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-CODE-013",
        name="Application classes should not depend on test frameworks",
        category="Coding practices",
        severity="MEDIUM",
        description=(
            "Production application code must not import test libraries such as pytest, unittest.mock, or hypothesis."
        ),
        recommendation="Remove test framework imports from application code; move test utilities to test packages.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-CODE-014",
        name="Classes should not have public mutable static fields",
        category="Coding practices",
        severity="MEDIUM",
        description="Functions rebinding module-level globals introduce mutable shared state and concurrency hazards.",
        recommendation="Encapsulate mutable state in explicit classes or pass state via function arguments.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-CODE-017",
        name="Classes should not directly instantiate Thread",
        category="Coding practices",
        severity="MEDIUM",
        description="Directly creating threading.Thread instances bypasses concurrency limits and thread pools.",
        recommendation="Use concurrent.futures.ThreadPoolExecutor or async tasks instead of raw threads.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-CODE-018",
        name="Assertions should have a detail message",
        category="Coding practices",
        severity="INFO",
        description=(
            "Assertions in production code without messages provide unhelpful traceback diagnostics and may be stripped"
            " under -O."
        ),
        recommendation="Provide an informative message in assert statements or use explicit conditional checks.",
        learn_more_url="https://github.com/ffroliva/sharpit",
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
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-SPRING-003",
        name="Repositories should not depend on controllers",
        category="Layering",
        severity="MEDIUM",
        description="Data repositories must not import or depend on controller or router modules.",
        recommendation="Remove controller dependencies from repository modules.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-SPRING-006",
        name="Services should not depend on controllers",
        category="Layering",
        severity="MEDIUM",
        description="Business services must not depend on controller or web presentation modules.",
        recommendation="Remove controller imports from service modules.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-SPRING-007",
        name="Repositories should not depend on services",
        category="Layering",
        severity="MEDIUM",
        description="Data access repositories should not depend on higher-level service layer modules.",
        recommendation="Invert dependencies so services call repositories, not vice versa.",
        learn_more_url="https://github.com/ffroliva/sharpit",
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
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
    RuleDefinition(
        id="ARCH-PY-001",
        name="Packages should respect declared import-linter contracts",
        category="Package structure",
        severity="HIGH",
        description=(
            "Module dependencies violate architectural layering or forbidden import contracts declared in"
            " pyproject.toml."
        ),
        recommendation="Restructure imports to adhere to the project's declared import-linter contracts.",
        learn_more_url="https://github.com/ffroliva/sharpit",
    ),
)


def evaluate_rules(
    index: object,
    graph: object,
    contracts: Sequence[object] = (),
) -> dict[str, list[object]]:
    """Skeleton: returns empty findings."""
    del index, graph, contracts
    return {}
