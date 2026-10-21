"""Polling attempts in the Allure report (tests/utils/waiting.py).

Pure unit tests: no app, no database, no browser. `eventually` runs against a scripted probe and a
short timeout; its Allure step and attachment are no-ops when nothing is reporting.
"""

import re
from collections.abc import Callable, Iterator

import allure
import pytest

from tests.utils import aaa, waiting
from tests.utils.allure_links import area
from tests.utils.waiting import Attempt, attempts_text, eventually, step_title, timeout_message

pytestmark = [pytest.mark.regression, area("Reporting")]


@pytest.fixture
def body_flag() -> Iterator[None]:
    yield
    aaa.set_test_body_running(False)


@pytest.fixture
def attached(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Collects the text of every "Polling attempts" attachment instead of writing it."""
    texts: list[str] = []

    def fake_attach(body: str, *, name: str, **_: object) -> None:
        if name == waiting.ATTEMPTS_ATTACHMENT:
            texts.append(body)

    monkeypatch.setattr(waiting.allure, "attach", fake_attach)
    return texts


def _scripted(*outcomes: str | None) -> Callable[[], str | None]:
    """A probe that answers in turn: "not yet" raises, None and a value return as they are."""
    calls = iter(outcomes)

    def probe() -> str | None:
        answer = next(calls)
        if answer == "not yet":
            raise AssertionError("no line yet")
        return answer

    return probe


@allure.title("Consecutive identical outcomes share one line, other outcomes keep theirs")
def test_consecutive_identical_outcomes_share_one_line() -> None:
    attempts = [
        Attempt(1, 0, "not yet: x"),
        Attempt(2, 50, "not yet: x"),
        Attempt(3, 100, "not yet: x"),
        Attempt(4, 150, "None"),
        Attempt(5, 200, "not yet: x"),
    ]

    assert attempts_text(attempts).splitlines() == [
        "#1-#3 (3x)  0-100 ms  not yet: x",
        "#4  150 ms  None",
        "#5  200 ms  not yet: x",
    ]


@allure.title("A successful wait ends with its ok attempt")
def test_success_ends_with_the_ok_attempt() -> None:
    attempts = [
        Attempt(1, 0, "not yet: no line"),
        Attempt(2, 50, "not yet: no line"),
        Attempt(3, 100, "ok"),
    ]

    assert attempts_text(attempts).splitlines()[-1] == "#3  100 ms  ok"


@allure.title("A reason that is empty or spans lines still makes one readable outcome")
def test_outcome_of_an_odd_reason_stays_on_one_line() -> None:
    assert waiting.not_yet(AssertionError()) == "not yet: no reason given"
    assert waiting.not_yet(AssertionError("first\nsecond")) == "not yet: first second"


@allure.title("A timeout message keeps the original text first, then attempts and time")
def test_timeout_message_keeps_the_original_text_first() -> None:
    attempts = [
        Attempt(1, 0, "None"),
        Attempt(2, 50, "not yet: no line"),
        Attempt(3, 150, "not yet: no line"),
    ]

    assert timeout_message("the log of request r1", 0.2, "no line", attempts) == (
        "gave up after 0.2 s waiting for the log of request r1: no line (3 attempts, 150 ms)"
    )


@allure.title("The step is labelled as a check only in the test body, not inside a phase")
@pytest.mark.usefixtures("body_flag")
def test_step_title_is_labelled_as_a_check_only_in_the_test_body() -> None:
    aaa.set_test_body_running(False)
    assert step_title("the log") == "Wait until the log"

    aaa.set_test_body_running(True)
    assert step_title("the log") == "Assert: Wait until the log"

    with aaa.arrange("data"):  # inside an explicit phase the phase is the label
        assert step_title("the log") == "Wait until the log"


@allure.title("eventually returns the first real result and records every attempt")
def test_returns_the_first_real_result_and_records_every_attempt(attached: list[str]) -> None:
    probe = _scripted("not yet", None, "found")

    assert eventually(probe, describe="the log", timeout_s=5) == "found"

    lines = attached[0].splitlines()
    assert len(lines) == 3
    assert lines[0] == "#1  0 ms  not yet: no line yet"
    assert lines[1].startswith("#2  ")
    assert lines[1].endswith(" ms  None")
    assert lines[2].startswith("#3  ")
    assert lines[2].endswith(" ms  ok")


@allure.title("eventually raises AssertionError on timeout and still attaches the attempts")
def test_timeout_raises_assertion_error_and_still_attaches_the_attempts(
    attached: list[str],
) -> None:
    def never() -> None:
        raise AssertionError("no line yet")

    with pytest.raises(AssertionError, match=r"^gave up after 0\.2 s waiting for the log: ") as err:
        eventually(never, describe="the log", timeout_s=0.2)

    assert re.search(r"no line yet \(\d+ attempts, \d+ ms\)$", str(err.value))
    run = re.match(r"#1-#\d+ \((\d+)x\)  0-\d+ ms  not yet: no line yet$", attached[0])
    assert run is not None
    assert int(run.group(1)) >= 2  # 0.2 s at 50 ms: several identical attempts, one line
