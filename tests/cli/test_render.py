"""Ported human-readable output rules from BootUI's TextRendererTests."""

import json

import pytest

from sharpit.cli.render import render, write_utf8


# ported: TextRendererTests.scalarMembersRenderAsKeyValueLines
def test_scalar_members_render_as_key_value_lines():
    assert render({"uptime": "3h", "pid": 42, "healthy": True}, color=False) == ("uptime: 3h\npid: 42\nhealthy: true")


# ported: TextRendererTests.anArrayOfLikeShapedObjectsBecomesATable
def test_array_of_objects_becomes_a_table():
    assert render(
        {"beans": [{"name": "a", "scope": "singleton"}, {"name": "bb", "scope": "prototype"}]}, color=False
    ) == ("beans (2)\n  name  scope\n  ----  ---------\n  a     singleton\n  bb    prototype")


# ported: TextRendererTests.anArrayWithANestedObjectFallsBackToATreeRatherThanLyingInATable
def test_nested_objects_fall_back_to_a_tree():
    assert render({"items": [{"name": "a", "detail": {"x": 1}}]}, color=False) == (
        "items (1)\n  -\n    name: a\n    detail\n      x: 1"
    )


# ported: TextRendererTests.anArrayOfScalarsRendersAsAList
def test_arrays_of_scalars_render_as_lists():
    assert render({"profiles": ["dev", "test"]}, color=False) == "profiles (2)\n  - dev\n  - test"


# ported: TextRendererTests.nullAndAbsentValuesReadAsADashRatherThanTheWordNull
def test_null_is_shown_as_a_dash():
    assert render({"cause": None}, color=False) == "cause: -"


# ported: TextRendererTests.controlCharactersInValuesCannotReachTheTerminal
def test_control_characters_are_neutralized():
    text = render({"note": "first\nsecond\u001b"}, color=False)
    assert "\u001b" not in text
    assert "first\nsecond\\x1b" in text


# ported: TextRendererTests.pausedEvidenceGetsANoticeBeforeTheUnchangedPayload
def test_paused_low_footprint_mode_gets_a_notice():
    assert render({"lowFootprint": {"active": True, "paused": True}, "groups": []}, color=False).startswith(
        "PAUSED by low-footprint mode"
    )


# ported: TextRendererTests.emptyCollectionsStayVisibleInsteadOfDisappearing
def test_empty_collections_stay_visible():
    assert render({"findings": [], "details": {}}, color=False) == "findings: []\ndetails: {}"


# ported: TextRendererTests.numbersKeepTheFormTheServerSentThem
def test_numbers_keep_their_json_spelling():
    assert (
        render(json.loads('{"ratio":1.50,"bytes":12345678901}', parse_float=str), color=False)
        == "ratio: 1.50\nbytes: 12345678901"
    )


# ported: TextRendererTests.longCellsAreTruncatedSoATableStaysReadable
def test_long_table_cells_are_truncated():
    text = render({"rows": [{"trace": "a" * 200}]}, color=False)
    assert "…" in text
    assert all(len(line) < 80 for line in text.splitlines())


# ported: TextRendererTests.valuesOutsideATableArePrintedWhole
def test_values_outside_a_table_are_not_truncated():
    reason = "repeated-selects did not run: " + "external validation is incomplete " * 3
    text = render({"summary": reason, "checksNotRun": [reason]}, color=False)
    assert "…" not in text
    assert text == f"summary: {reason}\nchecksNotRun (1)\n  - {reason}"


# ported: TextRendererTests.newlinesInsideACellDoNotBreakTheTable
def test_newlines_inside_table_cells_are_flattened():
    assert render({"rows": [{"message": "first\nsecond"}]}, color=False) == (
        "rows (1)\n  message\n  ------------\n  first second"
    )


# ported: TextRendererTests.nestedObjectsAreIndentedUnderTheirName
def test_nested_objects_are_indented():
    assert (
        render({"jvm": {"vendor": "Eclipse", "version": "21"}}, color=False) == "jvm\n  vendor: Eclipse\n  version: 21"
    )


# ported: TextRendererTests.aTopLevelArrayIsRenderedWithoutAWrapper
def test_top_level_arrays_have_no_wrapper():
    assert render([{"a": 1}, {"a": 2}], color=False) == "a\n-\n1\n2"


# ported: TextRendererTests.colourIsOnlyAddedWhenAskedFor
def test_color_is_only_added_when_requested():
    assert "\x1b[" not in render({"a": 1}, color=False)
    assert "\x1b[" in render({"a": 1}, color=True)


# ported: TextRendererTests.controlCharactersInKeysCannotReachTheTerminalEither
def test_control_characters_in_table_headers_are_neutralized():
    text = render({"rows": [{"a\x1b[2Jb": "1"}]}, color=False)
    assert "\x1b" not in text
    assert r"a\x1b[2Jb" in text


# ported: TextRendererTests.advisorViolationLocationsStayReadableBesideTheirViolations
def test_violation_locations_remain_readable():
    text = render({"violations": ["Cycle a -> b"], "locations": [{"className": "a.B", "line": 42}]}, color=False)
    assert "violations (1)" in text
    assert "className  line" in text
    assert "a.B        42" in text


def test_utf8_output_without_a_byte_buffer_is_never_silently_replaced():
    written: list[str] = []

    class TextOnly:
        encoding = "cp1252"

        def write(self, text: str) -> int:
            text.encode(self.encoding)
            written.append(text)
            return len(text)

    stream = TextOnly()
    with pytest.raises(UnicodeEncodeError):
        write_utf8(stream, '{"name": "→ ok"}\n')  # type: ignore[arg-type]
    assert written == []
