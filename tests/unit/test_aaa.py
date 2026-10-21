"""Arrange / Act / Assert labels in the Allure report (tests/utils/aaa.py).

Pure unit tests: no app, no database, no browser.
"""

from collections.abc import Iterator
from contextlib import nullcontext

import allure
import pytest

from tests.utils import aaa
from tests.utils.allure_links import area

pytestmark = [pytest.mark.regression, area("Reporting")]


@pytest.fixture(autouse=True)
def _fresh_state() -> Iterator[None]:
    # The runtest hook marks the body as running after this setup; tests set the flag themselves.
    aaa.start_test(labels_on=True)
    yield
    aaa.start_test(labels_on=True)


@allure.title("A request is labelled Act only while the test body runs")
def test_request_is_labelled_act_only_in_the_test_body() -> None:
    aaa.set_test_body_running(False)  # as in fixture setup and teardown
    assert aaa.request_title("GET", "/x") == "GET /x"

    aaa.set_test_body_running(True)

    assert aaa.request_title("GET", "/x") == "Act: GET /x"


@allure.title("Inside an explicit phase nothing is labelled a second time")
def test_explicit_phase_switches_automatic_labels_off() -> None:
    aaa.set_test_body_running(True)

    with aaa.arrange("data"):
        assert not aaa.labelling()
        assert aaa.request_title("POST", "/y") == "POST /y"
        with aaa.check("nested"):  # a phase never nests inside another
            assert not aaa.labelling()

    assert aaa.labelling()


@allure.title("A phase is closed again when its code raises")
def test_phase_is_closed_when_the_code_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # No real step: a failed step would show red inside this passing test in the report.
    monkeypatch.setattr(aaa.allure, "step", lambda title: nullcontext())
    aaa.set_test_body_running(True)

    with pytest.raises(ValueError, match="boom"), aaa.act("fails"):
        raise ValueError("boom")

    assert aaa.labelling()


@allure.title("A Gherkin scenario gets no labels: browser checks read Expect")
def test_labels_are_off_for_gherkin_scenarios() -> None:
    aaa.start_test(labels_on=False)
    aaa.set_test_body_running(True)

    assert not aaa.labelling()
    assert aaa.request_title("GET", "/x") == "GET /x"
    assert aaa.assert_title("x to be visible") == "Expect x to be visible"


@allure.title("A browser check is labelled Assert outside Gherkin scenarios")
def test_browser_checks_are_labelled_assert() -> None:
    assert aaa.assert_title("x to be visible") == "Assert: x to be visible"


@allure.title("A test starts with no phase left open by the one before")
def test_start_test_clears_a_phase_left_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(aaa.allure, "step", lambda title: nullcontext())
    aaa.set_test_body_running(True)
    phase = aaa.act("never closed")
    phase.__enter__()  # as if a test died without leaving its phase

    aaa.start_test(labels_on=True)
    aaa.set_test_body_running(True)
    assert aaa.labelling()

    phase.__exit__(None, None, None)  # closing it late must not push the count below zero
    assert aaa.labelling()
