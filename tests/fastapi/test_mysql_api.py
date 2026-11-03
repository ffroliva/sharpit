"""The ``mysql`` panel routes and contract parity."""

from __future__ import annotations

from typing import Any

import golden
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.mysql.service import mysql_report
from sharpit.engine.context import SharpitContext
from sharpit.settings import load_settings

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())


class _Introspector:
    def app_info(self) -> Any:
        return None

    def routes(self) -> list[Any]:
        return []

    def providers(self) -> list[Any]:
        return []


def _ctx() -> SharpitContext:
    return SharpitContext(load_settings({"config_scan": False}, {}), ACTIVATION, _Introspector())


def test_report_golden_parity() -> None:
    payload = mysql_report(_ctx())
    golden.assert_parity("mysql", "report", payload)
