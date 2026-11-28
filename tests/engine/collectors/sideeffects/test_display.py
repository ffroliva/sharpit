from collections import defaultdict
from typing import cast

import pytest
from tests.test_masking_corpus import (
    AWS_KEY,
    GITHUB_TOKEN,
    PROBES,
    SENTINEL,
    STRIPE_KEY,
)

from sharpit.engine.collectors.sideeffects.display import (
    display_parameter,
    intake,
    mask_segments,
    row_dto,
)
from sharpit.engine.collectors.sideeffects.store import (
    SideEffectsStore,
    StoreRow,
)
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sensors.files import FilesSensor

ROW_DTO_KEYS: tuple[str, ...] = (
    "scope",
    "attribution",
    "sensor",
    "kind",
    "target",
    "callSite",
    "insideMethod",
    "origin",
    "location",
    "count",
    "failed",
    "completed",
    "nonZeroExits",
    "lastExitStatus",
    "totalMillis",
    "maxMillis",
    "firstSeen",
    "lastSeen",
    "exemplarRequestIds",
    "client",
    "capture",
    "capturedBy",
    "leftRunning",
    "requests",
    "parameter",
    "detail",
)

CORPUS_SECRET_NAMES = (
    SENTINEL,
    STRIPE_KEY,
    AWS_KEY,
    GITHUB_TOKEN,
)


class FakeSensorRows:
    def __init__(self) -> None:
        self.queues: dict[str, list[dict[str, object]]] = defaultdict(list)
        self.clear_times: dict[str, int] = defaultdict(int)

    def append(self, row: dict[str, object]) -> None:
        sensor = str(row.get("sensor") or row.get("source") or "processes")
        self.queues[sensor].append(row)

    def drain(self, sensor: str) -> list[dict[str, object]]:
        items = list(self.queues[sensor])
        self.queues[sensor].clear()
        return items

    def cleared_at(self, sensor: str) -> int:
        return self.clear_times[sensor]


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY, Exposure.FULL])
def test_segments_and_names_that_look_like_secrets_are_masked(exposure: Exposure) -> None:
    # ported: SideEffectOriginsTests.segmentsAndNamesThatLookLikeSecretsAreMasked
    masker = Masker(exposure=exposure, mask_secrets=True)
    assert mask_segments("/keys/AKIAABCDEFGHIJKLMNOP/x.txt", masker) == "/keys/******/x.txt"
    assert mask_segments("./reports/report-{n}.csv", masker) == "./reports/report-{n}.csv"
    assert display_parameter("AKIAABCDEFGHIJKLMNOP", masker) == "******"
    assert display_parameter("DATABASE_PASSWORD", masker) == "DATABASE_PASSWORD"


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY, Exposure.FULL])
def test_a_secret_looking_parameter_name_is_masked_in_parameter_and_detail_at_every_exposure(
    exposure: Exposure,
) -> None:
    masker = Masker(exposure=exposure, mask_secrets=True)
    row = {
        "sensor": "security-sinks",
        "kind": "command",
        "target": "convert, argument 1",
        "parameter": "AKIAIOSFODNN7EXAMPLE",
        "at": 1_000_000,
    }
    intake_row = intake(masker)(row)
    assert intake_row["parameter"] == "******"

    store_row = StoreRow(
        scope="route",
        attribution="GET /convert",
        sensor="security-sinks",
        kind="command",
        target="convert, argument 1",
        parameter=cast("str | None", intake_row["parameter"]),
        confirmed=True,
    )
    dto = row_dto(store_row, masker)
    assert dto["parameter"] == "******"
    assert "`******`" in str(dto["detail"])
    assert "AKIAIOSFODNN7EXAMPLE" not in str(dto["parameter"])
    assert "AKIAIOSFODNN7EXAMPLE" not in str(dto["detail"])


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY, Exposure.FULL])
def test_rows_are_keyed_on_masked_values(exposure: Exposure) -> None:
    masker = Masker(exposure=exposure, mask_secrets=True)
    rows = FakeSensorRows()
    store = SideEffectsStore(rows, intake=intake(masker))
    rows.append(
        {
            "sensor": "security-sinks",
            "kind": "file-path",
            "target": "/keys/AKIAIOSFODNN7EXAMPLA/data.csv",
            "parameter": "AKIAIOSFODNN7EXAMPLA",
            "at": 1_000_000,
            "requestId": "0000000000000001",
            "route": "GET /reports",
        }
    )
    rows.append(
        {
            "sensor": "security-sinks",
            "kind": "file-path",
            "target": "/keys/AKIAIOSFODNN7EXAMPLA/data.csv",
            "parameter": "AKIAIOSFODNN7EXAMPLB",
            "at": 1_000_001,
            "requestId": "0000000000000002",
            "route": "GET /reports",
        }
    )
    store.drain()
    stored = store.rows_of("security-sinks")
    assert len(stored) == 1
    assert stored[0].count == 2
    assert stored[0].parameter == "******"
    assert stored[0].target == "/keys/******/data.csv"
    store_rows = store._store_rows
    for key in store_rows:
        assert "AKIAIOSFODNN7EXAMPL" not in key.target
        assert "AKIAIOSFODNN7EXAMPL" not in str(key.parameter)
        assert key.target == "/keys/******/data.csv"
        assert key.parameter == "******"


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY, Exposure.FULL])
def test_every_security_sinks_row_has_no_location(exposure: Exposure) -> None:
    masker = Masker(exposure=exposure, mask_secrets=True)
    cmd_row = StoreRow(
        scope="route",
        attribution="GET /run",
        sensor="security-sinks",
        kind="command",
        target="convert",
        location="working-directory",
        parameter="param",
    )
    cmd_dto = row_dto(cmd_row, masker)
    assert cmd_dto["location"] is None

    fp_row = StoreRow(
        scope="route",
        attribution="GET /run",
        sensor="security-sinks",
        kind="file-path",
        target="./file.txt",
        location="working-directory",
        parameter="param",
    )
    fp_dto = row_dto(fp_row, masker)
    assert fp_dto["location"] is None

    file_row = StoreRow(
        scope="route",
        attribution="GET /run",
        sensor="files",
        kind="read",
        target="./file.txt",
        location="working-directory",
    )
    file_dto = row_dto(file_row, masker)
    assert file_dto["location"] == "working-directory"


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY, Exposure.FULL])
@pytest.mark.parametrize("secret_name", CORPUS_SECRET_NAMES)
def test_a_secret_looking_parameter_name_never_reaches_a_target_at_any_exposure(
    exposure: Exposure,
    secret_name: str,
) -> None:
    masker = Masker(exposure=exposure, mask_secrets=True)
    fs = FilesSensor(mask_path=masker.mask_path)
    pattern = f"./reports/{{{secret_name}}}.csv"
    finish_fn = fs._finish
    collapsed = finish_fn(pattern)
    target = mask_segments(collapsed, masker)

    store_row = StoreRow(
        scope="route",
        attribution="GET /reports",
        sensor="security-sinks",
        kind="file-path",
        target=target,
        parameter=display_parameter(secret_name, masker),
        confirmed=True,
    )
    dto = row_dto(store_row, masker)
    dto_target = str(dto["target"])

    assert secret_name not in dto_target
    if secret_name == SENTINEL:
        for probe in PROBES:
            assert probe not in dto_target
    elif secret_name == STRIPE_KEY:
        assert STRIPE_KEY[8:] not in dto_target
    elif secret_name == GITHUB_TOKEN:
        assert GITHUB_TOKEN[4:] not in dto_target


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY, Exposure.FULL])
def test_every_exposure_masks_secret_segments_and_never_blanks_a_row(exposure: Exposure) -> None:
    masker = Masker(exposure=exposure, mask_secrets=True)
    raw_row = {
        "sensor": "security-sinks",
        "kind": "file-path",
        "target": "/keys/AKIAABCDEFGHIJKLMNOP/reports.csv",
        "parameter": "param",
        "at": 1_000_000,
    }
    intake_row = intake(masker)(raw_row)
    assert intake_row["target"] == "/keys/******/reports.csv"

    store_row = StoreRow(
        scope="route",
        attribution="GET /reports",
        sensor="security-sinks",
        kind="file-path",
        target=str(intake_row["target"]),
        call_site="demo:run",
        origin=None,
        location=None,
        count=1,
        failed=0,
        completed=1,
        non_zero_exits=0,
        last_exit_status=None,
        total_millis=10,
        max_millis=10,
        first_seen=1_000_000,
        last_seen=1_000_000,
        exemplar_request_ids=["0000000000000001"],
        left_running=0,
        requests=1,
        parameter=str(intake_row["parameter"]),
        confirmed=True,
    )
    dto = row_dto(store_row, masker)
    assert dto["target"] == "/keys/******/reports.csv"
    assert dto["scope"] is not None
    assert dto["attribution"] is not None
    assert dto["sensor"] is not None
    assert dto["kind"] == "file path"
    assert dto["target"] is not None
    assert dto["count"] is not None
    assert dto["firstSeen"] is not None
    assert dto["lastSeen"] is not None
    assert dto["parameter"] is not None
    assert dto["detail"] is not None


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY, Exposure.FULL])
def test_the_console_token_in_a_path_is_never_shown(exposure: Exposure) -> None:
    token = "console-token-secret-999"
    masker = Masker(exposure=exposure, mask_secrets=False, token=token)
    path = f"./uploads/{token}/document.txt"
    masked = mask_segments(path, masker)
    assert token not in masked
    assert masked == "./uploads/******/document.txt"

    store_row = StoreRow(
        scope="route",
        attribution=f"GET /uploads/{token}",
        sensor="files",
        kind="read",
        target=masked,
        location="working-directory",
    )
    dto = row_dto(store_row, masker)
    assert token not in str(dto["target"])
    assert token not in str(dto["attribution"])


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY, Exposure.FULL])
def test_row_keys_follow_the_dto_order(exposure: Exposure) -> None:
    masker = Masker(exposure=exposure, mask_secrets=True)
    store_row = StoreRow(
        scope="route",
        attribution="GET /test",
        sensor="security-sinks",
        kind="command",
        target="convert",
        parameter="param",
        confirmed=True,
    )
    dto = row_dto(store_row, masker)
    assert tuple(dto.keys()) == ROW_DTO_KEYS


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY, Exposure.FULL])
def test_no_row_key_holds_a_hash(exposure: Exposure) -> None:
    masker = Masker(exposure=exposure, mask_secrets=True)
    store_row = StoreRow(
        scope="route",
        attribution="GET /test",
        sensor="security-sinks",
        kind="command",
        target="convert",
        parameter="param",
        confirmed=True,
    )
    dto = row_dto(store_row, masker)
    assert "rawHash" not in dto
    assert "redactedHash" not in dto
    for key in dto:
        assert "hash" not in key.lower()


def test_display_asks_the_masker_through_its_public_method(monkeypatch: pytest.MonkeyPatch) -> None:
    # display must not read the masker's private state: a renamed attribute would silently show the token
    monkeypatch.setattr(Masker, "holds_never_shown", lambda self, text: True, raising=False)
    masker = Masker(exposure=Exposure.MASKED, mask_secrets=False, token="console-token-secret-999")
    assert display_parameter("harmless", masker) == "******"


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.FULL])
def test_a_parameter_name_holding_the_console_token_is_masked(exposure: Exposure) -> None:
    token = "console-token-secret-999"
    masker = Masker(exposure=exposure, mask_secrets=False, token=token)
    assert display_parameter(f"x{token}y", masker) == "******"
