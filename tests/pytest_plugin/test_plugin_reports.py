from __future__ import annotations

import json

import pytest


@pytest.mark.parametrize(
    ("variable", "value", "warning"),
    [
        ("SHARPIT_EXPOSE_VALUES", "FULL", "report ignores SHARPIT_EXPOSE_VALUES=FULL"),
        ("SHARPIT_MASK_SECRETS", "false", "report ignores SHARPIT_MASK_SECRETS=false"),
    ],
)
def test_reports_ignore_unsafe_exposure_settings(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, variable: str, value: str, warning: str
) -> None:
    secret = "sk_live_12345678901234567890"
    pytester.makepyfile(
        f"""
        import logging
        import sqlite3
        def test_secrets():
            sqlite3.connect(':memory:').execute('SELECT ?', ('{secret}',))
            try: raise ValueError('{secret}')
            except ValueError: logging.getLogger('app').exception('handled')
        """
    )
    monkeypatch.setenv(variable, value)

    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 1
    report_text = (pytester.path / "report.json").read_text()
    assert secret not in report_text
    data = json.loads(report_text)
    assert warning in data["warnings"]
