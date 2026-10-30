import pytest

from sharpit.engine.relaxed import canonicalize, contains


# ported: RelaxedNamesTests.canonicalizeLowercasesAndNormalizesSeparators
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("BOOTUI_MCP_ENABLED", "bootui.mcp.enabled"),
        ("bootui.conformance.api-token", "bootui.conformance.api.token"),
        ("bootui.mcp.enabled", "bootui.mcp.enabled"),
        ("", ""),  # ported: RelaxedNamesTests.canonicalizePreservesNullAndEmpty
    ],
)
def test_canonicalize(name: str, expected: str) -> None:
    assert canonicalize(name) == expected


# ported: RelaxedNamesTests.canonicalizeIsLengthPreservingSoLiteralMatchesAreNeverLost
def test_canonicalize_is_length_preserving() -> None:
    name = "Spring_Datasource-URL"
    assert len(canonicalize(name)) == len(name)
    assert contains(name, canonicalize("datasource"))


# ported: RelaxedNamesTests.containsMatchesAcrossSeparatorAndCaseSpellings
@pytest.mark.parametrize(
    ("name", "query"),
    [
        ("BOOTUI_MCP_ENABLED", "bootui.mcp.enabled"),
        ("bootui.mcp.enabled", canonicalize("BOOTUI_MCP_ENABLED")),
        ("spring.datasource.url", canonicalize("spring-datasource")),
        ("bootui.mcp.enabled", ""),  # ported: RelaxedNamesTests.anEmptyOrNullQueryMatchesEverything
        ("bootui.mcp.enabled", None),
    ],
)
def test_contains_matches(name: str, query: str | None) -> None:
    assert contains(name, query)


# ported: RelaxedNamesTests.containsRejectsUnrelatedNamesAndToleratesNulls
def test_contains_rejects_unrelated_and_tolerates_none() -> None:
    assert not contains("bootui.mcp.enabled", "bootui.cli.enabled")
    assert not contains(None, "bootui")
    assert contains(None, "")
