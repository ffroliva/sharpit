"""Ported human-readable output rules from BootUI's TextRendererTests."""

from sharpit.cli.render import render


# ported: TextRendererTests.scalarMembersRenderAsKeyValueLines
def test_scalar_members_render_as_key_value_lines():
    assert render({"uptime": "3h", "pid": 42, "healthy": True}, color=False) == ("uptime: 3h\npid: 42\nhealthy: true")


# ported: TextRendererTests.anArrayOfLikeShapedObjectsBecomesATable
def test_array_of_objects_becomes_a_table():
    assert render({"beans": [{"name": "a", "scope": "single"}, {"name": "bb", "scope": "proto"}]}, color=False) == (
        "beans (2)\n  name  scope \n  ----  ------\n  a     single\n  bb    proto"
    )


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
    assert "first second " in text


# ported: TextRendererTests.pausedEvidenceGetsANoticeBeforeTheUnchangedPayload
def test_paused_low_footprint_mode_gets_a_notice():
    assert render({"lowFootprint": {"active": True, "paused": True}, "groups": []}, color=False).startswith(
        "PAUSED by low-footprint mode"
    )
