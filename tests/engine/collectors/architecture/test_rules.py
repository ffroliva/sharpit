"""Tests for architecture advisor rules and pyproject contracts (spec §5.5)."""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine import appsource
from sharpit.engine.collectors.architecture.contracts import Contract, find_pyproject_path, read_contracts
from sharpit.engine.collectors.architecture.graph import build_graph
from sharpit.engine.collectors.architecture.rules import evaluate_rules


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ported: ArchitectureRulesTests.packagesShouldBeFreeOfCycles
def test_rule_packages_free_of_cycles(tmp_path: Path) -> None:
    pkg = tmp_path / "app_cycle"
    _write(pkg / "__init__.py")
    _write(pkg / "p1" / "__init__.py", "import app_cycle.p2\n")
    _write(pkg / "p2" / "__init__.py", "import app_cycle.p1\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-PKG-001", [])) >= 1


# ported: ArchitectureRulesTests.internalPackagesShouldNotBeAccessedFromOtherModules
def test_rule_internal_packages(tmp_path: Path) -> None:
    pkg = tmp_path / "app_internal"
    _write(pkg / "__init__.py")
    _write(pkg / "auth" / "__init__.py")
    _write(pkg / "auth" / "internal.py", "SECRET = 1\n")
    _write(pkg / "users" / "__init__.py")
    _write(pkg / "users" / "views.py", "import app_internal.auth.internal\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-MOD-001", [])) >= 1


# ported: ArchitectureRulesTests.classesShouldNotAccessStandardStreams
def test_rule_standard_streams(tmp_path: Path) -> None:
    pkg = tmp_path / "app_streams"
    _write(pkg / "__init__.py")
    _write(pkg / "m.py", "def log_it():\n    print('hello')\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-CODE-001", [])) >= 1


# ported: ArchitectureRulesTests.classesShouldNotThrowGenericExceptions
def test_rule_generic_exceptions(tmp_path: Path) -> None:
    pkg = tmp_path / "app_genexc"
    _write(pkg / "__init__.py")
    _write(pkg / "m.py", "def fail():\n    raise Exception('boom')\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-CODE-002", [])) >= 1


# ported: ArchitectureRulesTests.classesShouldNotUseJodaTime
def test_rule_joda_time(tmp_path: Path) -> None:
    pkg = tmp_path / "app_pytz"
    _write(pkg / "__init__.py")
    _write(pkg / "m.py", "import pytz\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-CODE-004", [])) >= 1


# ported: ArchitectureRulesTests.classesShouldNotForciblyTerminateTheJvm
def test_rule_forcibly_terminate(tmp_path: Path) -> None:
    pkg = tmp_path / "app_exit"
    _write(pkg / "__init__.py")
    _write(pkg / "service.py", "import sys\ndef abort():\n    sys.exit(1)\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-CODE-006", [])) >= 1


# ported: ArchitectureRulesTests.classesShouldNotAccessJdkInternalApis
def test_rule_jdk_internal_apis(tmp_path: Path) -> None:
    pkg = tmp_path / "app_internal_api"
    _write(pkg / "__init__.py")
    _write(pkg / "m.py", "from starlette._utils import is_async_callable\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-CODE-007", [])) >= 1


# ported: ArchitectureRulesTests.classesShouldNotUseLegacyDateAndTimeClasses
def test_rule_legacy_date_time(tmp_path: Path) -> None:
    pkg = tmp_path / "app_utcnow"
    _write(pkg / "__init__.py")
    _write(pkg / "m.py", "import datetime\ndef now():\n    return datetime.datetime.utcnow()\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-CODE-008", [])) >= 1


# ported: ArchitectureRulesTests.exceptionsShouldBeNamedEndingWithException
def test_rule_exceptions_naming(tmp_path: Path) -> None:
    pkg = tmp_path / "app_exc_naming"
    _write(pkg / "__init__.py")
    _write(pkg / "m.py", "class InvalidUser(Exception):\n    pass\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-CODE-010", [])) >= 1


# ported: ArchitectureRulesTests.loggersShouldBePrivateFinalOrContainerManaged
def test_rule_loggers_private(tmp_path: Path) -> None:
    pkg = tmp_path / "app_logger"
    _write(pkg / "__init__.py")
    _write(pkg / "m.py", "import logging\nlog = logging.getLogger('custom_logger')\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-CODE-012", [])) >= 1


# ported: ArchitectureRulesTests.applicationClassesShouldNotDependOnTestFrameworks
def test_rule_test_frameworks(tmp_path: Path) -> None:
    pkg = tmp_path / "app_test_dep"
    _write(pkg / "__init__.py")
    _write(pkg / "service.py", "import pytest\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-CODE-013", [])) >= 1


# ported: ArchitectureRulesTests.classesShouldNotHavePublicMutableStaticFields
def test_rule_mutable_static_fields(tmp_path: Path) -> None:
    pkg = tmp_path / "app_globals"
    _write(pkg / "__init__.py")
    _write(pkg / "m.py", "PUBLIC_VAR = 1\ndef update():\n    global PUBLIC_VAR\n    PUBLIC_VAR = 2\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-CODE-014", [])) >= 1


# ported: ArchitectureRulesTests.classesShouldNotDirectlyInstantiateThread
def test_rule_instantiate_thread(tmp_path: Path) -> None:
    pkg = tmp_path / "app_thread"
    _write(pkg / "__init__.py")
    _write(pkg / "worker.py", "import threading\nt = threading.Thread(target=lambda: None)\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-CODE-017", [])) >= 1


# ported: ArchitectureRulesTests.assertionsShouldHaveADetailMessage
def test_rule_assertions_detail_message(tmp_path: Path) -> None:
    pkg = tmp_path / "app_assert"
    _write(pkg / "__init__.py")
    _write(pkg / "m.py", "def check(x):\n    assert x > 0\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-CODE-018", [])) >= 1


# ported: ArchitectureRulesTests.controllersShouldNotDependOnRepositories
def test_rule_controllers_repositories(tmp_path: Path) -> None:
    pkg = tmp_path / "app_ctrl_repo"
    _write(pkg / "__init__.py")
    _write(pkg / "repositories" / "__init__.py", "class Repo:\n    pass\n")
    _write(pkg / "routers" / "__init__.py", "from app_ctrl_repo.repositories import Repo\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-SPRING-002", [])) >= 1


# ported: ArchitectureRulesTests.repositoriesShouldNotDependOnControllers
def test_rule_repositories_controllers(tmp_path: Path) -> None:
    pkg = tmp_path / "app_repo_ctrl"
    _write(pkg / "__init__.py")
    _write(pkg / "routers" / "__init__.py", "class Router:\n    pass\n")
    _write(pkg / "repositories" / "__init__.py", "from app_repo_ctrl.routers import Router\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-SPRING-003", [])) >= 1


# ported: ArchitectureRulesTests.servicesShouldNotDependOnControllers
def test_rule_services_controllers(tmp_path: Path) -> None:
    pkg = tmp_path / "app_srv_ctrl"
    _write(pkg / "__init__.py")
    _write(pkg / "routers" / "__init__.py", "class Router:\n    pass\n")
    _write(pkg / "services" / "__init__.py", "from app_srv_ctrl.routers import Router\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-SPRING-006", [])) >= 1


# ported: ArchitectureRulesTests.repositoriesShouldNotDependOnServices
def test_rule_repositories_services(tmp_path: Path) -> None:
    pkg = tmp_path / "app_repo_srv"
    _write(pkg / "__init__.py")
    _write(pkg / "services" / "__init__.py", "class Service:\n    pass\n")
    _write(pkg / "repositories" / "__init__.py", "from app_repo_srv.services import Service\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-SPRING-007", [])) >= 1


# ported: ArchitectureRulesTests.servicesAndRepositoriesShouldNotDependOnWebRequestTypes
def test_rule_web_request_types(tmp_path: Path) -> None:
    pkg = tmp_path / "app_req_type"
    _write(pkg / "__init__.py")
    _write(pkg / "services" / "__init__.py", "from starlette.requests import Request\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-SPRING-008", [])) >= 1


def test_importlinter_layers_contract_violation(tmp_path: Path) -> None:
    pkg = tmp_path / "app_layers"
    _write(pkg / "__init__.py")
    _write(pkg / "ui" / "__init__.py", "U = 1\n")
    _write(pkg / "domain" / "__init__.py", "import app_layers.ui\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    contracts = [
        Contract(
            name="layers-contract",
            contract_type="layers",
            layers=("app_layers.ui", "app_layers.domain"),
        )
    ]
    findings = evaluate_rules(index, graph, contracts=contracts)

    assert len(findings.get("ARCH-PY-001", [])) >= 1


def test_importlinter_forbidden_contract_violation(tmp_path: Path) -> None:
    pkg = tmp_path / "app_forbidden"
    _write(pkg / "__init__.py")
    _write(pkg / "external" / "__init__.py", "E = 1\n")
    _write(pkg / "domain" / "__init__.py", "import app_forbidden.external\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    contracts = [
        Contract(
            name="forbidden-contract",
            contract_type="forbidden",
            source_modules=("app_forbidden.domain",),
            forbidden_modules=("app_forbidden.external",),
        )
    ]
    findings = evaluate_rules(index, graph, contracts=contracts)

    assert len(findings.get("ARCH-PY-001", [])) >= 1


def test_malformed_pyproject_is_a_limitation(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[tool.importlinter\nmalformed = ")
    pkg = tmp_path / "app_bad_toml"
    _write(pkg / "__init__.py")

    _contracts, limitations = read_contracts(pkg, [str(tmp_path)])

    assert any("pyproject.toml" in lim for lim in limitations)


def test_pyproject_read_only_from_package_sys_path_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    top = tmp_path / "top"
    _write(top / "pyproject.toml", '[tool.importlinter]\nname = "top"\n')
    project = top / "sub" / "my_project"
    _write(project / "pyproject.toml", '[[tool.importlinter.contracts]]\nname = "sub"\ntype = "layers"\n')
    pkg = project / "src" / "my_app"
    _write(pkg / "__init__.py")

    opened: list[str] = []
    real_open = builtins.open

    def spy_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)
    # sys.path has project / src (src/ layout):
    sys_path = [str(project / "src")]
    target = find_pyproject_path(pkg, sys_path)

    assert target == project / "pyproject.toml"
    assert not any(str(top / "pyproject.toml") == p for p in opened)


def test_violation_never_contains_literal_secret(tmp_path: Path) -> None:
    pkg = tmp_path / "app_secret"
    _write(pkg / "__init__.py")
    _write(pkg / "a.py", 'API_KEY = "sk-live-1234567890abcdef"\nimport app_secret.b\n')
    _write(pkg / "b.py", 'TOKEN = "sk-live-secrettoken9999"\nimport app_secret.a\n')

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    findings = evaluate_rules(index, graph)

    assert len(findings.get("ARCH-PKG-001", [])) >= 1
    for finding in findings["ARCH-PKG-001"]:
        assert "sk-live-" not in getattr(finding, "target", "")
        assert "sk-live-" not in getattr(finding, "message", "")
