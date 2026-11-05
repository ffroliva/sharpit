"""``activity`` 2.2.0 routes (lane D2): journal-only feed filters, ``/activity/journal``, ``/activity/resources``."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.capture import activity
from sharpit.engine.paging import parse_int_param
from sharpit.fastapi.http import json_response

_JOURNAL_FILTERS = ("route", "run", "requestId")


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def activity_feed(request: Request) -> Response:
        params = request.query_params
        journal_filters = any(params.get(name) for name in _JOURNAL_FILTERS) or params.get("noRequest") == "true"
        report = activity.activity_report(
            ctx,
            params.get("type"),
            params.get("severity"),
            parse_int_param(params.get("since"), "since"),
            parse_int_param(params.get("limit"), "limit"),
            params.get("q"),
            journal_filters=journal_filters,
        )
        return json_response(report)

    def journal(_request: Request) -> Response:
        return json_response(activity.journal_status_dto())

    def resources(_request: Request) -> Response:
        return json_response(activity.resources_dto())

    return [
        Route(f"{api}/activity", activity_feed, methods=["GET"]),
        Route(f"{api}/activity/journal", journal, methods=["GET"]),
        Route(f"{api}/activity/resources", resources, methods=["GET"]),
    ]
