from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.capture.mailview import clear_emails, email_message, email_report, render_eml
from sharpit.engine.headers import security_headers
from sharpit.fastapi.http import error, json_response


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def listing(request: Request) -> Response:
        if request.method == "DELETE":  # an action: the guard chain has already applied the read-only gate
            clear_emails(ctx)
            return Response(status_code=204, headers=dict(security_headers("api")))
        return json_response(email_report(ctx))

    def detail(request: Request) -> Response:
        email_id: str = request.path_params["id"]
        message = email_message(ctx, email_id)
        return json_response(message) if message is not None else error(404, f"email {email_id} not found")

    def download(request: Request) -> Response:
        email_id: str = request.path_params["id"]
        message = email_message(ctx, email_id)
        if message is None:
            return error(404, f"email {email_id} not found")
        return Response(
            render_eml(message).encode("utf-8"),
            media_type="message/rfc822",
            headers={
                **dict(security_headers("api")),
                "content-disposition": f'attachment; filename="email-{email_id}.eml"',
            },
        )

    return [
        Route(f"{api}/email", listing, methods=["GET", "DELETE"]),
        Route(f"{api}/email/{{id}}", detail, methods=["GET"]),
        Route(f"{api}/email/{{id}}/eml", download, methods=["GET"]),
    ]
