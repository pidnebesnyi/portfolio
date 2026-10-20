"""Network interception with page.route: the detail page's "Refresh status" button fetches
/ui/payments/{id}/status. The tests replace that one endpoint (error, slow answer, dropped
connection, made-up JSON) to check what the page does with each, which no real server can be
made to do on demand. Every route is removed at teardown; waits are expect() on the page."""

from collections.abc import Iterator

import allure
import pytest
from playwright.sync_api import Page, Route, expect

from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.pages.payment_detail_page import PaymentDetailPage
from tests.utils.allure_links import area, requirement

pytestmark = [pytest.mark.ui, area("UI payments"), requirement("PAY-REFRESH")]

STATUS_ENDPOINT = "**/ui/payments/*/status"


@pytest.fixture(autouse=True)
def _drop_routes(merchant_page: Page) -> Iterator[None]:
    yield
    merchant_page.unroute_all(behavior="ignoreErrors")


@pytest.fixture
def detail(merchant_page: Page, payment_factory: PaymentFactory) -> PaymentDetailPage:
    """The detail page of a fresh `created` payment, already open."""
    payment = payment_factory.create(PaymentStatus.CREATED)
    page = PaymentDetailPage(merchant_page, payment.id)
    page.open()
    expect(page.status).to_have_text("created")
    return page


@pytest.mark.regression
@allure.title("Refresh status shows the status the server has now")
def test_refresh_status_shows_the_status_the_server_has_now(
    merchant_page: Page, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create(PaymentStatus.CREATED)
    detail = PaymentDetailPage(merchant_page, payment.id)
    detail.open()
    expect(detail.status).to_have_text("created")
    payment_factory.api.authorize(payment.id).expect(200)  # changed behind the page's back

    detail.refresh_status()

    expect(detail.status).to_have_text("authorized")
    expect(detail.refresh_error).to_be_hidden()


@pytest.mark.smoke
@allure.title("The status badge renders what the endpoint answers")
def test_status_badge_renders_what_the_endpoint_answers(detail: PaymentDetailPage) -> None:
    seen: list[str] = []

    def fake_answer(route: Route) -> None:
        seen.append(route.request.url)
        route.fulfill(json={"status": "refunded"})  # not a state this payment is in

    detail.page.route(STATUS_ENDPOINT, fake_answer)

    detail.refresh_status()

    expect(detail.status).to_have_text("refunded")
    expect(detail.refresh_error).to_be_hidden()
    assert len(seen) == 1
    assert seen[0].endswith("/status")


@pytest.mark.regression
@allure.title("A 500 answer shows an error and leaves the status as it was")
def test_a_500_answer_shows_an_error_and_leaves_the_status_as_it_was(
    detail: PaymentDetailPage,
) -> None:
    detail.page.route(
        STATUS_ENDPOINT, lambda route: route.fulfill(status=500, json={"code": "internal_error"})
    )

    detail.refresh_status()

    expect(detail.refresh_error).to_have_text("Could not refresh the status")
    expect(detail.status).to_have_text("created")
    expect(detail.refresh_button).to_be_enabled()


@pytest.mark.regression
@allure.title("A dropped connection shows an error and leaves the status as it was")
def test_a_dropped_connection_shows_an_error_and_leaves_the_status_as_it_was(
    detail: PaymentDetailPage,
) -> None:
    detail.page.route(STATUS_ENDPOINT, lambda route: route.abort("internetdisconnected"))

    detail.refresh_status()

    expect(detail.refresh_error).to_be_visible()
    expect(detail.status).to_have_text("created")
    expect(detail.refresh_button).to_be_enabled()


@pytest.mark.regression
@allure.title("A slow answer shows a loading state, then the new status")
def test_a_slow_answer_shows_a_loading_state_then_the_new_status(
    detail: PaymentDetailPage,
) -> None:
    held: list[Route] = []

    def hold(route: Route) -> None:
        held.append(route)  # not answered: the request waits until the test says so

    detail.page.route(STATUS_ENDPOINT, hold)

    with detail.page.expect_request(STATUS_ENDPOINT):
        detail.refresh_status()

    expect(detail.refresh_button).to_be_disabled()
    expect(detail.refresh_button).to_have_text("Refreshing...")
    expect(detail.status).to_have_text("created")
    # The request event and the route event leave the driver together, and the expect() calls
    # above are round trips that come after both, so the held route is here by now.
    (route,) = held
    route.fulfill(json={"status": "captured"})
    expect(detail.status).to_have_text("captured")
    expect(detail.refresh_button).to_be_enabled()
    expect(detail.refresh_button).to_have_text("Refresh status")


@pytest.mark.regression
@allure.title("The error goes away after a retry that works")
def test_the_error_goes_away_after_a_retry_that_works(
    detail: PaymentDetailPage, payment_factory: PaymentFactory
) -> None:
    def failing(route: Route) -> None:
        route.fulfill(status=503, json={"code": "unavailable"})

    detail.page.route(STATUS_ENDPOINT, failing)
    detail.refresh_status()
    expect(detail.refresh_error).to_be_visible()

    detail.page.unroute(STATUS_ENDPOINT, failing)  # the real server answers from here on
    detail.refresh_status()

    expect(detail.refresh_error).to_be_hidden()
    expect(detail.status).to_have_text("created")
