"""The security-sinks coverage sentence: every case is one sentence that starts with "Checks"."""

import pytest

from sharpit.engine.collectors.sideeffects.service import _sinks_reason


@pytest.mark.parametrize(
    ("processes", "files", "text"),
    [
        (True, True, "Checks commands through the processes sensor; file paths through the files sensor."),
        (False, True, "Checks file paths through the files sensor; not commands: the processes sensor is off."),
        (True, False, "Checks commands through the processes sensor; not file paths: the files sensor is off."),
        (False, False, "Checks no sink: the processes and files sensors are off."),
    ],
)
def test_sinks_reason_is_one_sentence_starting_with_checks(processes: bool, files: bool, text: str) -> None:
    assert _sinks_reason(processes, files) == text
