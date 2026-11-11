from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.agentsessions import Layout, session_store
from sharpit.engine.paging import parse_int_param
from sharpit.fastapi.http import json_response
from sharpit.fastapi.routes.agent_sessions_stream import make_agent_sessions_stream_handler


def _make_sessions_endpoint(store: Any) -> Any:
    def sessions(request: Request) -> Response:
        since = parse_int_param(request.query_params.get("since"), "since")
        until = parse_int_param(request.query_params.get("until"), "until")
        return json_response(store.sessions(since, until))

    return sessions


def _make_dashboard_endpoint(store: Any) -> Any:
    def dashboard(_request: Request) -> Response:
        return json_response(store.dashboard())

    return dashboard


def _make_detail_endpoint(store: Any) -> Any:
    def session_detail(request: Request) -> Response:
        session_id: str = str(request.path_params["id"])
        detail: Any = store.detail(session_id)
        if detail is None:
            return Response(status_code=404)
        return json_response(detail)

    return session_detail


def _make_events_endpoint(store: Any) -> Any:
    def session_events(request: Request) -> Response:
        session_id: str = str(request.path_params["id"])
        if store.detail(session_id) is None:
            return Response(status_code=404)
        category: str | None = request.query_params.get("category")
        since: int | None = parse_int_param(request.query_params.get("since"), "since")
        limit_param: int | None = parse_int_param(request.query_params.get("limit"), "limit")
        limit: int = 200 if limit_param is None else limit_param
        events_dto: Any = store.events(session_id, category, since, limit)
        if events_dto is None:
            return Response(status_code=404)
        return json_response(events_dto)

    return session_events


def _make_raw_endpoint(ctx: Any, store: Any) -> Any:
    def raw_event(request: Request) -> Response:
        if not store.settings.allow_raw_reveal:
            return Response(status_code=404)
        if ctx.settings.expose_values == "METADATA_ONLY":
            return Response(status_code=404)
        session_id: str = str(request.path_params["id"])
        event_id: str = str(request.path_params["eventId"])
        res: Any = store.raw(session_id, event_id)
        if res is None:
            return Response(status_code=404)
        return json_response({"sessionId": session_id, "eventId": event_id, "json": res})

    return raw_event


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    api: str = str(ctx.settings.api_path[len(ctx.settings.path) :])
    prefix: str = f"{api}/claude-code"
    store: Any = session_store(ctx, Layout.CLAUDE_CODE)

    return [
        Route(f"{prefix}/sessions", _make_sessions_endpoint(store), methods=["GET"]),
        Route(f"{prefix}/dashboard", _make_dashboard_endpoint(store), methods=["GET"]),
        Route(f"{prefix}/sessions/{{id}}", _make_detail_endpoint(store), methods=["GET"]),
        Route(f"{prefix}/sessions/{{id}}/events", _make_events_endpoint(store), methods=["GET"]),
        Route(f"{prefix}/sessions/{{id}}/events/{{eventId}}/raw", _make_raw_endpoint(ctx, store), methods=["GET"]),
        Route(f"{prefix}/stream", make_agent_sessions_stream_handler(ctx, Layout.CLAUDE_CODE), methods=["GET"]),
    ]
