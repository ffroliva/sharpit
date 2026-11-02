from sharpit.engine.testsession.partial import partial_run


def test_partial_when_deselected() -> None:
    assert partial_run([{"deselected": 1}], {}) is True


def test_partial_when_keyword_or_nodeid_selected() -> None:
    assert partial_run([{"selection": True}], {}) is True


def test_partial_when_last_failed_or_deselect_used() -> None:
    assert partial_run([{"selection": True}], {}) is True


def test_partial_when_maxfail_or_shouldstop() -> None:
    assert partial_run([], {"maxfail": True}) is True
    assert partial_run([], {"stopped": True}) is True


def test_partial_when_interrupted() -> None:
    assert partial_run([{"interrupted": True}], {}) is True


def test_xdist_partial_facts_merged() -> None:
    assert partial_run([{"deselected": 0}, {"collected": 4, "run": 3}], {}) is True


def test_full_run_is_not_partial() -> None:
    assert partial_run([{"deselected": 0, "selection": False, "collected": 4, "run": 4}], {}) is False
