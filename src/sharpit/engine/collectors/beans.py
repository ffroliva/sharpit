"""``GET {api}/beans`` (port of BootUI ``BeansService``; contract section 6, spec 8 Beans)."""

from __future__ import annotations

from typing import Any

from sharpit.engine.context import SharpitContext
from sharpit.engine.paging import paged
from sharpit.engine.spi import ProviderInfo


def _bean(p: ProviderInfo) -> dict[str, Any]:
    resource = p.resource
    if p.overridden_by is not None:  # BeanSummary has no overriddenBy / description key: it rides on ``resource``
        resource = f"{resource or 'unknown source'} (overridden by {p.overridden_by})"
    return {
        "name": p.name,
        "type": p.type_name,
        "scope": p.scope,
        "resource": resource,
        "dependencies": list(p.dependencies),
        "aliases": [],
        "classification": p.classification,
    }


def beans_report(
    ctx: SharpitContext, q: str | None, classification: str | None, offset: int | None, limit: int | None
) -> dict[str, Any]:
    # Not memoised: dependency_overrides and routes can change after install, and the walk is read-only.
    beans = sorted((_bean(p) for p in ctx.introspector.providers()), key=lambda b: b["name"])
    wanted = (classification or "").strip().upper()
    selected = [b for b in beans if not wanted or b["classification"] == wanted]
    page, meta = paged(selected, q, offset, limit, lambda b: (b["name"], b["type"]))
    meta["total"] = len(beans)  # BootUI: page.total is the unfiltered count, before the classification filter too
    return {"total": len(beans), "beans": page, "page": meta}
