"""Every ``# ported:`` citation on the scanner and recorder rows was read again when generic mode went (Task 29).

BootUI's ``SqlStatementNormalizer`` and ``JournalTextExposure`` read every statement one way, with no dialect. Task 29
re-pointed each row that read ``UNSUPPORTED`` to the known dialect whose output still equals BootUI's assertion, so
its citation stays; a row whose assertion no known dialect holds was deleted with its citation. A new citation on
these files fails here until it is read and added: the list is the audit, so a stale one cannot creep back.
"""

# derived: plan 2026-11-05 Task 29 Step 8, no BootUI source

from __future__ import annotations

import collections
import re
from pathlib import Path

HERE = Path(__file__).parent
CITATION = re.compile(r"#\s*ported:\s*(?P<source>.+?)\s*$")
AUDITED_FILES = ("test_sqlscan.py", "test_sqltrace.py")
# (file, citation) -> how many rows cite it, each read on 2026-11-07 against the dialect its row now reads
AUDITED: dict[tuple[str, str], int] = {
    ("test_sqlscan.py", "JournalTextExposureTests.sqlThatCannotBeToldApartFromAValueIsNeverShownMasked"): 3,
    (
        "test_sqlscan.py",
        "JournalTextExposureTests.sqlWhoseBackslashesReadDifferentlyByDialectShowsNothingAfterItsFirstQuote",
    ): 1,
    ("test_sqlscan.py", "SqlRowLimitsTests.anEmptyHashCommentEndsAtItsLineAndAtTheEndOfTheText"): 1,
    ("test_sqlscan.py", "SqlStatementNormalizerTests.tokensClassifyTheTextTheWayNormalizeLexesIt"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.boundsTheScanSoAPathologicalStatementCannotDominate"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.collapsesInListsButNotProjectionsOrArguments"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.collapsesWhitespaceAndStripsComments"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.countsLiteralsInPredicatePositionsSeparately,"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.doesNotTreatDigitsInsideIdentifiersAsLiterals"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.foldsInListsSoListLengthDoesNotSplitOneStatementIntoMany"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.handlesDoubledQuoteEscapesWithoutSplittingTheLiteral"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.isCaseInsensitiveForGroupingButKeepsTheStatementAsWritten"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.keepsQuotedIdentifiersSoDifferentColumnsNeverCollapse"): 1,
    (
        "test_sqltrace.py",
        "SqlStatementNormalizerTests.leavesAnUnterminatedDollarRunAloneRatherThanSwallowingTheStatement",
    ): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.masksADoubleQuotedRunThatCannotBeAnIdentifier"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.masksPostgresDollarQuotedStrings"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.neverLeavesALiteralValueInTheNormalizedText"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.normalizesBooleanLiteralsSoEquivalentPredicatesAggregate"): 1,
    (
        "test_sqltrace.py",
        "SqlStatementNormalizerTests.replacesStringAndNumericLiteralsSoEquivalentExecutionsAggregate",
    ): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.returnsAnEmptyResultForNullOrBlankSql"): 1,
    ("test_sqltrace.py", "SqlStatementNormalizerTests.survivesUnterminatedQuotesFromTruncatedCapture"): 1,
    ("test_sqltrace.py", "SqlTraceEntryDto, SqlTraceGroupDto record components"): 1,
    ("test_sqltrace.py", "SqlTraceRecorder.topStatements (executions desc, then sql, at most 20)"): 1,
    ("test_sqltrace.py", "SqlTraceRecorder.truncate (strip, cut, ellipsis)"): 1,
    ("test_sqltrace.py", "SqlTraceRecorderTests.clearEmptiesBufferButKeepsTotalCaptured"): 1,
    ("test_sqltrace.py", "SqlTraceRecorderTests.computesAggregateStats"): 1,
    ("test_sqltrace.py", "SqlTraceRecorderTests.dropsParametersWhenCaptureDisabled"): 1,
    ("test_sqltrace.py", "SqlTraceRecorderTests.evictsOldestBeyondCapacityAndCountsEvictions"): 1,
    ("test_sqltrace.py", "SqlTraceRecorderTests.flagsSlowQueriesByThreshold, slowFlaggingDisabledWhenThresholdZero"): 1,
    (
        "test_sqltrace.py",
        "SqlTraceRecorderTests.groupsRepeatedSelectsAndFlagsNPlusOne (grouped on the normalised statement)",
    ): 1,
    ("test_sqltrace.py", "SqlTraceRecorderTests.keepsParametersAndThreadWhenCaptureEnabled"): 1,
    ("test_sqltrace.py", "SqlTraceRecorderTests.notifiesSubscribersOnRecordClearAndRecordingChange"): 1,
    ("test_sqltrace.py", "SqlTraceRecorderTests.omitsCallSiteWhenCaptureDisabled"): 1,
    ("test_sqltrace.py", "SqlTraceRecorderTests.recordsNothingWhenPaused"): 1,
    ("test_sqltrace.py", "SqlTraceReport.unavailable, SqlTraceStatsDto.empty"): 1,
    (
        "test_sqltrace.py",
        "SqlTraceStoreTests.recordsDurationMicrosAndRetention (BootUI 2.2.0 SqlTraceEntryDto, CaptureRetentionDto)",
    ): 1,
    (
        "test_sqltrace.py",
        "SqlTracingProxies.categoryOf / firstKeyword (verbatim), SqlTracingProxiesTests category assertions",
    ): 1,
}


def _found() -> dict[tuple[str, str], int]:
    found: collections.Counter[tuple[str, str]] = collections.Counter()
    for name in AUDITED_FILES:
        for line in (HERE / name).read_text(encoding="utf-8").splitlines():
            if (cited := CITATION.search(line)) is not None:
                found[(name, cited["source"])] += 1
    return dict(found)


def test_no_stale_ported_citation() -> None:
    assert _found() == AUDITED
