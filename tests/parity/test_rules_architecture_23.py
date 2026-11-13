"""Architecture advisor rule parity tests against BootUI 2.3.0 ARCH-* rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from sharpit.engine import appsource
from sharpit.engine.advisors.findings import Finding
from sharpit.engine.collectors.architecture.graph import build_graph
from sharpit.engine.collectors.architecture.rules import evaluate_rules


def _scan(tmp_path: Path, files: dict[str, str]) -> dict[str, list[Finding]]:
    app_dir = tmp_path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    for rel_path, content in files.items():
        p = app_dir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    index = appsource.build_index(app_dir)
    graph = build_graph(index)
    return evaluate_rules(index, graph)


@pytest.mark.bootui("rule:ARCH-PKG-001")
def test_arch_pkg_001_package_cycles(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.packageCyclesCountEachDetectedCycleOnceRatherThanEachDependencyEdge
    # Fires on circular package dependency
    fired = _scan(
        tmp_path / "fire",
        {
            "pkg_a/__init__.py": "import app.pkg_b\n",
            "pkg_b/__init__.py": "import app.pkg_a\n",
        },
    )
    assert "ARCH-PKG-001" in fired
    finding = fired["ARCH-PKG-001"][0]
    assert finding.rule_id == "ARCH-PKG-001"
    assert finding.severity == "HIGH"
    assert finding.target == "app.pkg_a cycle"
    assert "Circular package dependency:" in finding.message
    assert len(fired["ARCH-PKG-001"]) == 1

    # Does not fire when acyclic
    passed = _scan(
        tmp_path / "pass",
        {
            "pkg_a/__init__.py": "import app.pkg_b\n",
            "pkg_b/__init__.py": "VALUE = 42\n",
        },
    )
    assert "ARCH-PKG-001" not in passed


@pytest.mark.bootui("rule:ARCH-MOD-001")
def test_arch_mod_001_internal_package_access(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.internalPackagesShouldNotBeAccessedExternallyFlagsCrossModuleInternalAccess
    # ported: ArchitectureRuleAuditTests.internalPackageAccessIsReportedOncePerDependencyWithItsOwnLine
    # Fires when module from another package imports private/internal module
    fired = _scan(
        tmp_path / "fire",
        {
            "billing/__init__.py": "",
            "billing/_internal.py": "SECRET = 1\n",
            "orders/__init__.py": "",
            "orders/service.py": "import app.billing._internal\n",
        },
    )
    assert "ARCH-MOD-001" in fired
    finding = fired["ARCH-MOD-001"][0]
    assert finding.rule_id == "ARCH-MOD-001"
    assert finding.severity == "HIGH"
    assert finding.target == "app.orders.service:1"
    assert "imports internal module app.billing._internal" in finding.message

    # Does not fire when private module is imported within the same package
    passed = _scan(
        tmp_path / "pass",
        {
            "billing/__init__.py": "",
            "billing/_internal.py": "SECRET = 1\n",
            "billing/service.py": "import app.billing._internal\n",
        },
    )
    assert "ARCH-MOD-001" not in passed


@pytest.mark.bootui("rule:ARCH-CODE-001")
def test_arch_code_001_standard_streams(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.noStandardStreamsFlagsNoArgPrintStackTrace
    # ported: ArchitectureRulesTests.capturingAStackTraceThroughAnExplicitWriterIsNotReported
    # Fires on print() or sys.stdout/stderr
    fired = _scan(
        tmp_path / "fire",
        {
            "main.py": "print('writing to standard stream')\n",
        },
    )
    assert "ARCH-CODE-001" in fired
    finding = fired["ARCH-CODE-001"][0]
    assert finding.rule_id == "ARCH-CODE-001"
    assert finding.severity == "LOW"
    assert finding.target == "app.main:1"
    assert finding.message == "app.main:1 print()"

    # Does not fire when using logging
    passed = _scan(
        tmp_path / "pass",
        {
            "main.py": "import logging\nlog = logging.getLogger(__name__)\nlog.info('message')\n",
        },
    )
    assert "ARCH-CODE-001" not in passed


@pytest.mark.bootui("rule:ARCH-CODE-002")
def test_arch_code_002_generic_exceptions(tmp_path: Path) -> None:
    # ported: ArchitectureViolationRetrievalTests.twentyNineSelfCallsAndSixteenGenericExceptionsRemainCompletelyRetrievable  # noqa: E501
    # Fires on raising generic Exception or BaseException
    fired = _scan(
        tmp_path / "fire",
        {
            "service.py": "raise Exception('something broke')\n",
        },
    )
    assert "ARCH-CODE-002" in fired
    finding = fired["ARCH-CODE-002"][0]
    assert finding.rule_id == "ARCH-CODE-002"
    assert finding.severity == "LOW"
    assert finding.target == "app.service:1"
    assert finding.message == "app.service:1 raises Exception"

    # Does not fire on specific exception subclasses
    passed = _scan(
        tmp_path / "pass",
        {
            "service.py": "raise ValueError('invalid argument')\n",
        },
    )
    assert "ARCH-CODE-002" not in passed


@pytest.mark.bootui("rule:ARCH-CODE-004")
def test_arch_code_004_joda_time(tmp_path: Path) -> None:
    # ported from the rule class ArchitectureRules.NoJodaTimeRule
    # Fires on pytz imports (Python analogue of legacy Joda-Time)
    fired = _scan(
        tmp_path / "fire",
        {
            "dates.py": "import pytz\n",
        },
    )
    assert "ARCH-CODE-004" in fired
    finding = fired["ARCH-CODE-004"][0]
    assert finding.rule_id == "ARCH-CODE-004"
    assert finding.severity == "INFO"
    assert finding.target == "app.dates:1"
    assert finding.message == "app.dates:1 pytz import"

    # Does not fire on standard library zoneinfo
    passed = _scan(
        tmp_path / "pass",
        {
            "dates.py": "import zoneinfo\n",
        },
    )
    assert "ARCH-CODE-004" not in passed


@pytest.mark.bootui("rule:ARCH-CODE-006")
def test_arch_code_006_terminate_jvm(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.noSystemExitFlagsRuntimeExitAndHalt
    # ported: ArchitectureRulesTests.noSystemExitExemptsSystemExitCalledDirectlyFromStaticMain
    # Fires on sys.exit / os._exit / exit / quit in application code
    fired = _scan(
        tmp_path / "fire",
        {
            "worker.py": "import sys\nsys.exit(1)\n",
        },
    )
    assert "ARCH-CODE-006" in fired
    finding = fired["ARCH-CODE-006"][0]
    assert finding.rule_id == "ARCH-CODE-006"
    assert finding.severity == "HIGH"
    assert finding.target == "app.worker:2"
    assert finding.message == "app.worker:2 calls sys.exit()"

    # Does not fire when called directly inside __main__ entry point
    passed = _scan(
        tmp_path / "pass",
        {
            "__main__.py": "import sys\nsys.exit(0)\n",
        },
    )
    assert "ARCH-CODE-006" not in passed


@pytest.mark.bootui("rule:ARCH-CODE-007")
def test_arch_code_007_jdk_internal_apis(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.noJdkInternalApiDoesNotFlagExportedComSunApi
    # Fires when importing private symbols from external libraries
    fired = _scan(
        tmp_path / "fire",
        {
            "client.py": "from external_pkg import _private_symbol\n",
        },
    )
    assert "ARCH-CODE-007" in fired
    finding = fired["ARCH-CODE-007"][0]
    assert finding.rule_id == "ARCH-CODE-007"
    assert finding.severity == "MEDIUM"
    assert finding.target == "app.client:1"
    assert finding.message == "app.client:1 imports private _private_symbol from external_pkg"

    # Does not fire on public API imports
    # ported: ArchitectureRulesTests.noJdkInternalApiDoesNotFlagExportedComSunApi
    passed = _scan(
        tmp_path / "pass",
        {
            "client.py": "from external_pkg import public_symbol\n",
        },
    )
    assert "ARCH-CODE-007" not in passed


@pytest.mark.bootui("rule:ARCH-CODE-008")
def test_arch_code_008_legacy_datetime(tmp_path: Path) -> None:
    # ported: NoLegacyDateTimeRuleTests.legacyConstructionAndCalendarFactoryRemainFindings
    # ported: NoLegacyDateTimeRuleTests.standardBridgeCallsDoNotCountAsLegacyUse
    # Fires on deprecated datetime.utcnow() or utcfromtimestamp()
    fired = _scan(
        tmp_path / "fire",
        {
            "clock.py": "from datetime import datetime\nts = datetime.utcnow()\n",
        },
    )
    assert "ARCH-CODE-008" in fired
    finding = fired["ARCH-CODE-008"][0]
    assert finding.rule_id == "ARCH-CODE-008"
    assert finding.severity == "INFO"
    assert finding.target == "app.clock:2"
    assert finding.message == "app.clock:2 calls utcnow()"

    # Does not fire on standard modern timezone-aware calls
    passed = _scan(
        tmp_path / "pass",
        {
            "clock.py": "from datetime import datetime, timezone\nts = datetime.now(timezone.utc)\n",
        },
    )
    assert "ARCH-CODE-008" not in passed


@pytest.mark.bootui("rule:ARCH-CODE-010")
def test_arch_code_010_exception_naming(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.exceptionsShouldBeNamedExceptionFlagsExceptionTypesWithoutSuffix
    # ported: ArchitectureRulesTests.exceptionsShouldBeNamedExceptionPassesWhenSuffixIsPresent
    # Fires on custom exceptions not ending in Error or Exception
    fired = _scan(
        tmp_path / "fire",
        {
            "errors.py": "class BadFailure(Exception):\n    pass\n",
        },
    )
    assert "ARCH-CODE-010" in fired
    finding = fired["ARCH-CODE-010"][0]
    assert finding.rule_id == "ARCH-CODE-010"
    assert finding.severity == "INFO"
    assert finding.target == "app.errors:1"
    assert finding.message == "app.errors:1 exception BadFailure not named Error/Exception"

    # Does not fire on exceptions with proper suffix
    passed = _scan(
        tmp_path / "pass",
        {
            "errors.py": (
                "class GoodFailureException(Exception):\n    pass\nclass ValidationError(Exception):\n    pass\n"
            ),
        },
    )
    assert "ARCH-CODE-010" not in passed


@pytest.mark.bootui("rule:ARCH-CODE-012")
def test_arch_code_012_loggers_private(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.loggersShouldBePrivateStaticFinalFlagsMutableOrVisibleLoggers
    # ported: ArchitectureRulesTests.loggersShouldBePrivateStaticFinalPassesForPrivateStaticFinalLoggers
    # Fires on getLogger() with hardcoded literal string or empty args
    fired = _scan(
        tmp_path / "fire",
        {
            "component.py": "import logging\nlog = logging.getLogger('hardcoded')\n",
        },
    )
    assert "ARCH-CODE-012" in fired
    finding = fired["ARCH-CODE-012"][0]
    assert finding.rule_id == "ARCH-CODE-012"
    assert finding.severity == "LOW"
    assert finding.target == "app.component:2"
    assert finding.message == "app.component:2 getLogger() with literal string"

    # Does not fire on idiomatic getLogger(__name__)
    passed = _scan(
        tmp_path / "pass",
        {
            "component.py": "import logging\nlog = logging.getLogger(__name__)\n",
        },
    )
    assert "ARCH-CODE-012" not in passed


@pytest.mark.bootui("rule:ARCH-CODE-013")
def test_arch_code_013_test_framework_dependencies(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.noTestFrameworkDependenciesFlagsMainCodeUsingTestApis
    # ported: ArchitectureRuleAuditTests.testFrameworkUseIsReportedFromMainOutputButNotFromTestOutput
    # Fires when production application code imports test frameworks
    fired = _scan(
        tmp_path / "fire",
        {
            "service.py": "import pytest\n",
        },
    )
    assert "ARCH-CODE-013" in fired
    finding = fired["ARCH-CODE-013"][0]
    assert finding.rule_id == "ARCH-CODE-013"
    assert finding.severity == "MEDIUM"
    assert finding.target == "app.service:1"
    assert finding.message == "app.service:1 imports test library pytest"

    # Does not fire when imported inside test packages
    passed = _scan(
        tmp_path / "pass",
        {
            "tests/__init__.py": "",
            "tests/test_service.py": "import pytest\n",
        },
    )
    assert "ARCH-CODE-013" not in passed


@pytest.mark.bootui("rule:ARCH-CODE-014")
def test_arch_code_014_public_mutable_globals(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.noPublicMutableStaticFieldsFlagsPublicNonFinalStaticFields
    # ported: ArchitectureRulesTests.noPublicMutableStaticFieldsPassesForFinalOrNonPublicStaticFields
    # Fires when functions rebind public module-level globals
    fired = _scan(
        tmp_path / "fire",
        {
            "state.py": "counter = 0\ndef increment():\n    global counter\n    counter += 1\n",
        },
    )
    assert "ARCH-CODE-014" in fired
    finding = fired["ARCH-CODE-014"][0]
    assert finding.rule_id == "ARCH-CODE-014"
    assert finding.severity == "MEDIUM"
    assert finding.target == "app.state:3"
    assert finding.message == "app.state:3 rebinds public global counter"

    # Does not fire on private globals or local variables
    passed = _scan(
        tmp_path / "pass",
        {
            "state.py": "_counter = 0\ndef increment():\n    global _counter\n    _counter += 1\n",
        },
    )
    assert "ARCH-CODE-014" not in passed


@pytest.mark.bootui("rule:ARCH-CODE-017")
def test_arch_code_017_direct_thread_instantiation(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.noDirectThreadInstantiationFlagsNewThread
    # ported: ArchitectureRulesTests.noDirectThreadInstantiationPassesForManagedExecutorUsage
    # Fires on direct instantiation of threading.Thread
    fired = _scan(
        tmp_path / "fire",
        {
            "worker.py": "import threading\nt = threading.Thread(target=lambda: None)\n",
        },
    )
    assert "ARCH-CODE-017" in fired
    finding = fired["ARCH-CODE-017"][0]
    assert finding.rule_id == "ARCH-CODE-017"
    assert finding.severity == "MEDIUM"
    assert finding.target == "app.worker:2"
    assert finding.message == "app.worker:2 directly instantiates Thread"

    # Does not fire when using executor pools
    passed = _scan(
        tmp_path / "pass",
        {
            "worker.py": (
                "from concurrent.futures import ThreadPoolExecutor\npool = ThreadPoolExecutor(max_workers=2)\n"
            ),
        },
    )
    assert "ARCH-CODE-017" not in passed


@pytest.mark.bootui("rule:ARCH-CODE-018")
def test_arch_code_018_assert_detail_message(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.assertionsShouldHaveDetailMessageFlagsMessagelessAssertion
    # ported: ArchitectureRulesTests.assertionsShouldHaveDetailMessagePassesForMessageBearingAssertion
    # Fires on assert statements without detail message
    fired = _scan(
        tmp_path / "fire",
        {
            "check.py": "def check(x):\n    assert x > 0\n",
        },
    )
    assert "ARCH-CODE-018" in fired
    finding = fired["ARCH-CODE-018"][0]
    assert finding.rule_id == "ARCH-CODE-018"
    assert finding.severity == "INFO"
    assert finding.target == "app.check:2"
    assert finding.message == "app.check:2 assert without message"

    # Does not fire when detail message is provided
    passed = _scan(
        tmp_path / "pass",
        {
            "check.py": "def check(x):\n    assert x > 0, 'x must be positive'\n",
        },
    )
    assert "ARCH-CODE-018" not in passed


@pytest.mark.bootui("rule:ARCH-SPRING-002")
def test_arch_spring_002_controllers_not_depend_on_repositories(tmp_path: Path) -> None:
    # ported from the rule class ArchitectureRules.ControllersShouldNotDependOnRepositoriesRule
    # Fires when controller/router module imports repository directly
    fired = _scan(
        tmp_path / "fire",
        {
            "routers/__init__.py": "",
            "routers/user.py": "import app.repositories.user\n",
            "repositories/__init__.py": "",
            "repositories/user.py": "class UserRepo: pass\n",
        },
    )
    assert "ARCH-SPRING-002" in fired
    finding = fired["ARCH-SPRING-002"][0]
    assert finding.rule_id == "ARCH-SPRING-002"
    assert finding.severity == "LOW"
    assert finding.target == "app.routers.user:1"
    assert finding.message == "Controller app.routers.user imports repository app.repositories.user"

    # Does not fire when controller imports service and service imports repository
    passed = _scan(
        tmp_path / "pass",
        {
            "routers/__init__.py": "",
            "routers/user.py": "import app.services.user\n",
            "services/__init__.py": "",
            "services/user.py": "import app.repositories.user\n",
            "repositories/__init__.py": "",
            "repositories/user.py": "class UserRepo: pass\n",
        },
    )
    assert "ARCH-SPRING-002" not in passed


@pytest.mark.bootui("rule:ARCH-SPRING-003")
def test_arch_spring_003_repositories_not_depend_on_controllers(tmp_path: Path) -> None:
    # ported from the rule class ArchitectureRules.RepositoriesShouldNotDependOnControllersRule
    # Fires when repository module imports controller/router
    fired = _scan(
        tmp_path / "fire",
        {
            "routers/__init__.py": "",
            "routers/user.py": "class UserRouter: pass\n",
            "repositories/__init__.py": "",
            "repositories/user.py": "import app.routers.user\n",
        },
    )
    assert "ARCH-SPRING-003" in fired
    finding = fired["ARCH-SPRING-003"][0]
    assert finding.rule_id == "ARCH-SPRING-003"
    assert finding.severity == "MEDIUM"
    assert finding.target == "app.repositories.user:1"
    assert finding.message == "Repository app.repositories.user imports controller app.routers.user"

    # Does not fire when repository has no controller dependency
    passed = _scan(
        tmp_path / "pass",
        {
            "repositories/__init__.py": "",
            "repositories/user.py": "class UserRepo: pass\n",
        },
    )
    assert "ARCH-SPRING-003" not in passed


@pytest.mark.bootui("rule:ARCH-SPRING-006")
def test_arch_spring_006_services_not_depend_on_controllers(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.servicesShouldNotDependOnControllersFlagsWebLayerDependencies
    # ported: ArchitectureRulesTests.servicesShouldNotDependOnControllersPassesWhenServiceHasNoControllerDependency
    # Fires when service module imports controller/router
    fired = _scan(
        tmp_path / "fire",
        {
            "routers/__init__.py": "",
            "routers/user.py": "class UserRouter: pass\n",
            "services/__init__.py": "",
            "services/user.py": "import app.routers.user\n",
        },
    )
    assert "ARCH-SPRING-006" in fired
    finding = fired["ARCH-SPRING-006"][0]
    assert finding.rule_id == "ARCH-SPRING-006"
    assert finding.severity == "MEDIUM"
    assert finding.target == "app.services.user:1"
    assert finding.message == "Service app.services.user imports controller app.routers.user"

    # Does not fire when service has no controller dependency
    passed = _scan(
        tmp_path / "pass",
        {
            "services/__init__.py": "",
            "services/user.py": "class UserService: pass\n",
        },
    )
    assert "ARCH-SPRING-006" not in passed


@pytest.mark.bootui("rule:ARCH-SPRING-007")
def test_arch_spring_007_repositories_not_depend_on_services(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.repositoriesShouldNotDependOnServicesFlagsPersistenceDependingOnBusinessLayer
    # Fires when repository module imports service module
    fired = _scan(
        tmp_path / "fire",
        {
            "services/__init__.py": "",
            "services/user.py": "class UserService: pass\n",
            "repositories/__init__.py": "",
            "repositories/user.py": "import app.services.user\n",
        },
    )
    assert "ARCH-SPRING-007" in fired
    finding = fired["ARCH-SPRING-007"][0]
    assert finding.rule_id == "ARCH-SPRING-007"
    assert finding.severity == "MEDIUM"
    assert finding.target == "app.repositories.user:1"
    assert finding.message == "Repository app.repositories.user imports service app.services.user"

    # Does not fire when service imports repository, not repository importing service
    passed = _scan(
        tmp_path / "pass",
        {
            "services/__init__.py": "",
            "services/user.py": "import app.repositories.user\n",
            "repositories/__init__.py": "",
            "repositories/user.py": "class UserRepo: pass\n",
        },
    )
    assert "ARCH-SPRING-007" not in passed


@pytest.mark.bootui("rule:ARCH-SPRING-015")
def test_arch_spring_015_mutable_settings(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.configurationPropertiesShouldBeImmutableFlagsMutableFields
    fired = _scan(
        tmp_path / "mutable",
        {"settings.py": "from pydantic_settings import BaseSettings\nclass Settings(BaseSettings):\n    name: str\n"},
    )
    assert "ARCH-SPRING-015" in fired
    finding = fired["ARCH-SPRING-015"][0]
    assert finding.rule_id == "ARCH-SPRING-015"
    assert finding.severity == "INFO"
    assert finding.target == "app.settings:3"
    assert finding.message == "app.settings:3 mutable settings field name"
    assert len(fired["ARCH-SPRING-015"]) == 1

    multiple = _scan(
        tmp_path / "multiple",
        {
            "settings.py": "from pydantic_settings import BaseSettings\n"
            "class Settings(BaseSettings):\n    name: str\n    count: int\n"
        },
    )
    assert len(multiple["ARCH-SPRING-015"]) == 2

    empty = _scan(
        tmp_path / "empty",
        {"settings.py": "from pydantic_settings import BaseSettings\nclass Settings(BaseSettings):\n    pass\n"},
    )
    assert "ARCH-SPRING-015" not in empty

    # ported: ArchitectureRulesTests.configurationPropertiesShouldBeImmutablePassesForImmutableRecord
    passed = _scan(
        tmp_path / "immutable",
        {
            "settings.py": "from pydantic_settings import BaseSettings\n"
            "class Settings(BaseSettings):\n"
            "    model_config = {'frozen': True}\n"
            "    name: str\n"
        },
    )
    assert "ARCH-SPRING-015" not in passed

    class_attrs = _scan(
        tmp_path / "classvars",
        {
            "settings.py": "from typing import ClassVar\nfrom pydantic_settings import BaseSettings\n"
            "class Settings(BaseSettings):\n    cache: ClassVar[int] = 2\n"
        },
    )
    assert "ARCH-SPRING-015" not in class_attrs

    inherited = _scan(
        tmp_path / "inherited",
        {
            "settings.py": "from pydantic_settings import BaseSettings\nclass S(BaseSettings): pass\n"
            "class T(S):\n    name: str\n"
        },
    )
    assert inherited["ARCH-SPRING-015"][0].target == "app.settings:4"

    imported_inherited = _scan(
        tmp_path / "imported-inherited",
        {
            "base.py": "from pydantic_settings import BaseSettings\nclass S(BaseSettings): pass\n",
            "child.py": "from .base import S\nclass T(S):\n    name: str\n",
        },
    )
    assert imported_inherited["ARCH-SPRING-015"][0].target == "app.child:3"


@pytest.mark.bootui("rule:ARCH-CODE-009")
def test_arch_code_009_deprecated_app_symbols(tmp_path: Path) -> None:
    # partial: BootUI 2.3.0 has no deprecated-application-symbol test; this is a PEP 702 analogue.
    fired = _scan(
        tmp_path / "deprecated-use",
        {
            "api.py": "from warnings import deprecated\n@deprecated('use replacement')\ndef old_api(): pass\n",
            "caller.py": "from app.api import old_api\nold_api()\n",
        },
    )
    assert "ARCH-CODE-009" in fired
    finding = fired["ARCH-CODE-009"][0]
    assert finding.rule_id == "ARCH-CODE-009"
    assert finding.severity == "INFO"
    assert finding.target == "app.caller:2"
    assert finding.message == "app.caller:2 uses deprecated app symbol"

    # A deprecated declaration alone is not a use.
    passed = _scan(
        tmp_path / "deprecated-unused",
        {"api.py": "from typing_extensions import deprecated as old\n@old('use replacement')\ndef old_api(): pass\n"},
    )
    assert "ARCH-CODE-009" not in passed

    method_name = _scan(
        tmp_path / "method-name",
        {
            "api.py": "from warnings import deprecated\nclass A:\n"
            "    @deprecated('use replacement')\n    def save(self): pass\n"
            "def save(): pass\n",
            "caller.py": "from app.api import save\nsave()\n",
        },
    )
    assert "ARCH-CODE-009" not in method_name

    module_attribute = _scan(
        tmp_path / "module-attribute",
        {
            "api.py": "from warnings import deprecated\n@deprecated('use replacement')\ndef old(): pass\n",
            "caller.py": "from app import api\napi.old()\n",
        },
    )
    assert "ARCH-CODE-009" in module_attribute

    same_module = _scan(
        tmp_path / "same-module",
        {
            "api.py": "from warnings import deprecated\n@deprecated('use replacement')\n"
            "def old(): pass\ndef use(): old()\n"
        },
    )
    assert same_module["ARCH-CODE-009"][0].target == "app.api:4"

    relative_import = _scan(
        tmp_path / "relative-import",
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from warnings import deprecated\n@deprecated('replace')\ndef old(): pass\n",
            "pkg/b.py": "from .a import old\nold()\n",
        },
    )
    assert relative_import["ARCH-CODE-009"][0].target == "app.pkg.b:2"

    parent_relative_import = _scan(
        tmp_path / "parent-relative-import",
        {
            "pkg/__init__.py": "",
            "pkg/sub/__init__.py": "",
            "pkg/a.py": "from warnings import deprecated\n@deprecated('replace')\ndef old(): pass\n",
            "pkg/sub/b.py": "from ..a import old\nold()\n",
        },
    )
    assert parent_relative_import["ARCH-CODE-009"][0].target == "app.pkg.sub.b:2"


@pytest.mark.bootui("rule:ARCH-SPRING-008")
def test_arch_spring_008_services_repositories_not_depend_on_web_types(tmp_path: Path) -> None:
    # ported: ArchitectureRulesTests.servicesAndRepositoriesShouldNotDependOnServletTypesFlagsHttpRequestDependencies
    # ported: ArchitectureRuleAuditTests.servicesMayThrowWebExceptionsWithoutDependingOnRequestTypes
    # Fires when service or repository module imports web transport types
    fired = _scan(
        tmp_path / "fire",
        {
            "services/__init__.py": "",
            "services/user.py": "from starlette.requests import Request\n",
        },
    )
    assert "ARCH-SPRING-008" in fired
    finding = fired["ARCH-SPRING-008"][0]
    assert finding.rule_id == "ARCH-SPRING-008"
    assert finding.severity == "MEDIUM"
    assert finding.target == "app.services.user:1"
    assert finding.message == "app.services.user:1 imports web transport from starlette.requests"

    # Does not fire on transport-agnostic DTOs
    passed = _scan(
        tmp_path / "pass",
        {
            "services/__init__.py": "",
            "services/user.py": "class UserProfile: pass\n",
        },
    )
    assert "ARCH-SPRING-008" not in passed


def test_planted_secret_never_appears_in_findings(tmp_path: Path) -> None:
    # Planted secret in scanned code must never appear in finding target, message, or fingerprint
    planted_secret = "SECRET_TOKEN_482910_XYZ"
    findings = _scan(
        tmp_path / "secret_scan",
        {
            "leak.py": f"""import sys
API_KEY = '{planted_secret}'
print('{planted_secret}')
raise Exception('{planted_secret}')
assert False, '{planted_secret}'
""",
        },
    )
    all_findings = [f for sublist in findings.values() for f in sublist]
    assert len(all_findings) > 0
    for finding in all_findings:
        assert planted_secret not in finding.target
        assert planted_secret not in finding.message
        assert planted_secret not in finding.fingerprint
