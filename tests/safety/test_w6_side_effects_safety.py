"""Side Effects reads have no side effects, and the panel gates every route."""

PANEL = "side-effects"
GET_ROWS = ["/sharpit/api/side-effects", "/sharpit/api/side-effects/sensor"]
WRITE_ROWS: list[tuple[str, str]] = []
