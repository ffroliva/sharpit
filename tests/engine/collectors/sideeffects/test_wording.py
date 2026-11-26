from sharpit.engine.collectors.sideeffects.wording import OTHER, SEEN_ONCE, detail


def test_an_argument_of_a_named_command() -> None:
    assert detail("command", "name", "convert, argument 1", True) == (
        "Request input reached this command unchanged: the value of `name` appeared in argument 1 of `convert`. "
        "Check that it is validated."
    )


def test_an_argument_of_the_executable() -> None:
    assert detail("command", "name", "(the executable), argument 2", True) == (
        "Request input reached this command unchanged: the value of `name` appeared in argument 2 of the executable. "
        "Check that it is validated."
    )


def test_the_executable_alone() -> None:
    assert detail("command", "name", "(the executable)", True) == (
        "Request input reached this command unchanged: the value of `name` appeared in it. Check that it is validated."
    )


def test_a_file_path() -> None:
    assert detail("file path", "name", "./reports/{id}.csv", True) == (
        "Request input reached this file path unchanged: the value of `name` appeared in it. "
        "Check that it is validated and cannot leave its directory."
    )


def test_a_missing_name_reads_a_parameter() -> None:
    assert detail("command", None, "convert, argument 1", True).startswith(
        "Request input reached this command unchanged: the value of `a parameter`"
    )


def test_an_unconfirmed_row_ends_seen_once() -> None:
    confirmed = detail("command", "name", None, True)
    unconfirmed = detail("command", "name", None, False)
    assert unconfirmed == confirmed + SEEN_ONCE


def test_an_unknown_kind_takes_the_generic_sentence() -> None:
    assert detail("unknown", "name", "target", True) == (
        "Request input reached this sink unchanged: the value of `name` appeared in it. Check that it is validated."
    )


def test_wording_constants_match_bootui() -> None:
    assert SEEN_ONCE == " Seen in one request so far."
    assert OTHER == (
        "Request input reached more sinks than this table keeps apart; their parameters and"
        " sinks are counted here. Clear the recording to see them again."
    )
