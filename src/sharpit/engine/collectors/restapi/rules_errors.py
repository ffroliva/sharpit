"""REST API error-handling rules evaluated against the error contract."""

from __future__ import annotations

from collections.abc import Sequence

from sharpit.engine.collectors.restapi.error_contract import ErrorContractEntry
from sharpit.engine.collectors.restapi.rules_common import Violation
from sharpit.engine.spi import ApiRouteInfo


def _err004(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    return []


def _err005(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    return []


def _err007(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    return []


def _err008(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    return []


def _err010(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    return []


def _err011(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    return []


CHECKS = {
    "RAPI-ERR-004": _err004,
    "RAPI-ERR-005": _err005,
    "RAPI-ERR-007": _err007,
    "RAPI-ERR-008": _err008,
    "RAPI-ERR-010": _err010,
    "RAPI-ERR-011": _err011,
}
