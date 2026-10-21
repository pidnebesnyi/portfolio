import allure
import pytest

from tests.utils import aaa


@pytest.fixture(autouse=True)
def _body_flag():
    yield
    aaa.set_test_body_running(False)


@pytest.mark.regression
@allure.title("A request is labelled Act only while the test body runs")
def test_request_is_labelled_act_only_in_the_test_body() -> None:
    aaa.set_test_body_running(False)  # as in fixture setup and teardown
    assert aaa.request_title("GET", "/x") == "GET /x"

    aaa.set_test_body_running(True)

    assert aaa.request_title("GET", "/x") == "Act: GET /x"


@pytest.mark.regression
@allure.title("Inside an explicit phase nothing is labelled a second time")
def test_explicit_phase_switches_automatic_labels_off() -> None:
    aaa.set_test_body_running(True)

    with aaa.arrange("data"):
        assert not aaa.labelling()
        assert aaa.request_title("POST", "/y") == "POST /y"
        with aaa.check("nested"):  # a phase never nests inside another
            assert not aaa.labelling()

    assert aaa.labelling()


@pytest.mark.regression
@allure.title("A phase is closed again when its code raises")
def test_phase_is_closed_when_the_code_raises() -> None:
    aaa.set_test_body_running(True)

    with pytest.raises(ValueError, match="boom"), aaa.act("fails"):
        raise ValueError("boom")

    assert aaa.labelling()
