"""The opt-in HTTP security observer: options, expectation parsing and the ``sharpit_http_observed`` fixture."""

from __future__ import annotations

from typing import Any

import pytest

HEADER = "--sharpit-required-response-header"
STATUS = "--sharpit-expected-status"


def _options(pytester: pytest.Pytester, *args: str) -> Any:
    """The resolved options, or None when pytest refuses the arguments (so a missing option is an assertion red)."""
    from sharpit.pytest_plugin.options import resolve

    try:
        return resolve(pytester.parseconfig(*args))
    except pytest.UsageError:
        return None


def _field(options: Any, name: str) -> Any:
    return getattr(options, name, None)


def _refused(pytester: pytest.Pytester, *args: str) -> str:
    result = pytester.runpytest(*args)
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    return result.stderr.str()


def test_http_security_observer_disabled_by_default(pytester: pytest.Pytester) -> None:
    options = _options(pytester, "--sharpit")

    assert _field(options, "http_security_enabled") is False


def test_http_security_option_and_ini_expectations_resolve(pytester: pytest.Pytester) -> None:
    pytester.makeini("""
        [pytest]
        sharpit_http_security = true
        sharpit_required_response_headers =
            GET /items=X-Content-Type-Options
        sharpit_expected_statuses =
            GET /items=200,304
    """)

    options = _options(pytester, "--sharpit")

    assert _field(options, "http_security_enabled") is True
    assert _field(options, "http_required_headers") == (("GET", "/items", "x-content-type-options"),)
    assert _field(options, "http_expected_statuses") == (("GET", "/items", (200, 304)),)


@pytest.mark.parametrize(
    ("option", "value", "shape"),
    [
        (HEADER, "GET /items", "METHOD ROUTE=HEADER"),
        (HEADER, "GET /items=", "METHOD ROUTE=HEADER"),
        (HEADER, "GET =X-A", "METHOD ROUTE=HEADER"),
        (HEADER, " /items=X-A", "METHOD ROUTE=HEADER"),
        (STATUS, "GET /items=ok", "METHOD ROUTE=STATUS"),
        (STATUS, "GET /items=99", "METHOD ROUTE=STATUS"),
        (STATUS, "GET /items=600", "METHOD ROUTE=STATUS"),
        (STATUS, "GET /items=200,", "METHOD ROUTE=STATUS"),
        (STATUS, "GET /items=", "METHOD ROUTE=STATUS"),
    ],
)
def test_http_security_invalid_expectation_is_rejected(
    pytester: pytest.Pytester, option: str, value: str, shape: str
) -> None:
    stderr = _refused(pytester, "--sharpit", "--sharpit-http-security", option, value)

    assert f"expected {shape}" in stderr


def test_http_security_expected_status_set_accepts_any_listed_status(pytester: pytest.Pytester) -> None:
    options = _options(
        pytester, "--sharpit", "--sharpit-http-security", STATUS, "GET /a=404,200", STATUS, "GET /a=200,500"
    )

    assert _field(options, "http_expected_statuses") == (("GET", "/a", (200, 404, 500)),)


def test_http_security_method_is_case_normalized(pytester: pytest.Pytester) -> None:
    options = _options(pytester, "--sharpit", "--sharpit-http-security", HEADER, "get /a=X-A", STATUS, "pOsT /b=201")

    assert _field(options, "http_required_headers") == (("GET", "/a", "x-a"),)
    assert _field(options, "http_expected_statuses") == (("POST", "/b", (201,)),)


def test_http_security_expectations_require_enabled_observer(pytester: pytest.Pytester) -> None:
    stderr = _refused(pytester, "--sharpit", HEADER, "GET /a=X-A")

    assert "--sharpit-http-security" in stderr
    assert "unrecognized arguments" not in stderr


def test_http_security_observer_requires_sharpit(pytester: pytest.Pytester) -> None:
    stderr = _refused(pytester, "--sharpit-http-security")

    assert "requires --sharpit" in stderr


def test_http_security_cli_expectations_replace_ini(pytester: pytest.Pytester) -> None:
    pytester.makeini("""
        [pytest]
        sharpit_required_response_headers =
            GET /ini=X-Ini
        sharpit_expected_statuses =
            GET /ini=200
    """)

    options = _options(pytester, "--sharpit", "--sharpit-http-security", HEADER, "GET /cli=X-Cli")

    assert _field(options, "http_required_headers") == (("GET", "/cli", "x-cli"),)
    assert _field(options, "http_expected_statuses") == (("GET", "/ini", (200,)),)


def test_http_security_expectation_parsing_edge_cases(pytester: pytest.Pytester) -> None:
    options = _options(
        pytester,
        "--sharpit",
        "--sharpit-http-security",
        HEADER,
        "  get   /a=b,c = X-A  ",
        HEADER,
        "GET /a=b,c=x-a",
        HEADER,
        "GET /a=b,c=X-B",
        STATUS,
        "GET /a=b,c=200",
    )

    assert _field(options, "http_required_headers") == (("GET", "/a=b,c", "x-a"), ("GET", "/a=b,c", "x-b"))
    assert _field(options, "http_expected_statuses") == (("GET", "/a=b,c", (200,)),)


def test_http_security_fixture_is_listed_by_pytest_fixtures(pytester: pytest.Pytester) -> None:
    result = pytester.runpytest("--fixtures")

    assert "sharpit_http_observed" in result.stdout.str()


def test_http_security_fixture_off_state_is_identity(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
        def test_identity(sharpit_http_observed):
            app = object()
            assert sharpit_http_observed(app) is app
    """)

    result = pytester.runpytest("--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown")

    result.assert_outcomes(passed=1)
