"""Moving around: links, titles, redirects, the back button, and who may open which page."""

import re
from uuid import uuid4

import allure
import pytest
from playwright.sync_api import BrowserContext, Page, expect

from tests.clients.merchants_api import MerchantsApi
from tests.clients.payments_api import PaymentsApi
from tests.config import Settings
from tests.factories.merchant_factory import MerchantAccount
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.pages.admin_page import AdminPage
from tests.pages.login_page import LoginPage
from tests.pages.new_payment_page import NewPaymentPage
from tests.pages.payment_detail_page import PaymentDetailPage
from tests.pages.payments_page import PaymentsPage
from tests.ui.conftest import start_session
from tests.utils.allure_links import area, requirement

pytestmark = [pytest.mark.ui, area("UI navigation")]


def _main_heading(page: Page):
    return page.get_by_role("heading", level=1)


@pytest.mark.regression
@requirement("PAY-LIST")
@allure.title("The main navigation moves between the list and the new payment form")
def test_main_navigation_moves_between_the_list_and_the_new_payment_form(
    merchant_page: Page,
) -> None:
    payments = PaymentsPage(merchant_page)
    payments.open()

    payments.new_payment_link.click()
    form = NewPaymentPage(merchant_page)
    form.expect_loaded()
    expect(_main_heading(merchant_page)).to_have_text("New payment")

    form.payments_link.click()
    payments.expect_loaded()
    expect(_main_heading(merchant_page)).to_have_text("Payments")


@pytest.mark.regression
@requirement("PAY-LIST")
@pytest.mark.parametrize(
    ("path", "title", "heading"),
    [
        ("/ui/payments", "Payments", "Payments"),
        ("/ui/payments/new", "New payment", "New payment"),
    ],
)
@allure.title("{path} has its own title and one main heading")
def test_page_has_its_own_title_and_one_main_heading(
    merchant_page: Page, path: str, title: str, heading: str
) -> None:
    merchant_page.goto(path)

    expect(merchant_page).to_have_title(title)
    expect(_main_heading(merchant_page)).to_have_count(1)
    expect(_main_heading(merchant_page)).to_have_text(heading)


@pytest.mark.regression
@requirement("PAY-LIST")
@allure.title("A payment page is titled with the payment's id")
def test_payment_page_is_titled_with_the_payments_id(
    merchant_page: Page, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create()
    detail = PaymentDetailPage(merchant_page, payment.id)

    detail.open()

    expect(merchant_page).to_have_title(f"Payment {payment.id}")
    expect(detail.id).to_have_text(str(payment.id))


@pytest.mark.regression
@requirement("PAY-LIST")
@allure.title("The site root leads a logged-in merchant to the payment list")
def test_site_root_leads_a_logged_in_merchant_to_the_payment_list(merchant_page: Page) -> None:
    merchant_page.goto("/ui")

    PaymentsPage(merchant_page).expect_loaded()


@pytest.mark.regression
@requirement("PAY-LIST")
@allure.title("The back button returns to the filtered list")
def test_back_button_returns_to_the_filtered_list(
    merchant_page: Page, payment_factory: PaymentFactory
) -> None:
    payment_factory.create(PaymentStatus.CREATED)
    authorized = payment_factory.create(PaymentStatus.AUTHORIZED)
    payments = PaymentsPage(merchant_page)
    payments.open()
    payments.filter_by(status="authorized")
    payments.expect_total(1)

    payments.open_payment(authorized.id)
    merchant_page.go_back()

    expect(merchant_page).to_have_url(re.compile(r"/ui/payments\?.*status=authorized"))
    expect(payments.status_filter).to_have_value("authorized")
    payments.expect_total(1)


@pytest.mark.regression
@requirement("PAY-ACCESS")
@pytest.mark.parametrize("whose", ["another merchant's", "nobody's"])
@allure.title("Opening {whose} payment leads back to the list with a notice")
def test_opening_a_payment_that_is_not_yours_leads_back_to_the_list(
    merchant_page: Page, other_merchant: MerchantAccount, whose: str
) -> None:
    if whose == "nobody's":
        payment_id = uuid4()
    else:
        payment_id = other_merchant.api.create(description="not for you").expect(201).id

    merchant_page.goto(f"/ui/payments/{payment_id}")

    payments = PaymentsPage(merchant_page)
    payments.expect_loaded()
    expect(payments.flash_error).to_have_text("Payment not found")
    # The notice is the same for both, so it does not reveal that the other payment exists.
    expect(merchant_page.get_by_text("not for you")).to_have_count(0)
    expect(merchant_page.get_by_text(str(payment_id))).to_have_count(0)


@pytest.mark.regression
@requirement("PAY-ACCESS")
@allure.title("Another merchant's payment cannot be refunded through the page either")
def test_another_merchants_payment_cannot_be_refunded_through_the_page(
    merchant_page: Page, other_merchant: MerchantAccount
) -> None:
    foreign = other_merchant.api.create().expect(201)
    other_merchant.api.authorize(foreign.id).expect(200)
    other_merchant.api.capture(foreign.id).expect(200)

    # No refund form is offered, so send what the form would send.
    response = merchant_page.request.post(
        f"/ui/payments/{foreign.id}/refund", form={"amount": "100"}
    )

    assert response.ok  # followed the redirect to the list
    assert "Payment not found" in response.text()
    stored = other_merchant.api.get(foreign.id).expect(200)
    assert (stored.status, stored.refunded_amount) == (PaymentStatus.CAPTURED, 0)


@pytest.mark.regression
@requirement("PAY-ACCESS")
@pytest.mark.parametrize("cookie", ["not-a-token", "a.b.c", ""])
@allure.title("A session cookie that is not a valid token leads to the login page")
def test_invalid_session_cookie_leads_to_the_login_page(
    page: Page, context: BrowserContext, settings: Settings, cookie: str
) -> None:
    start_session(context, settings, cookie)

    page.goto(PaymentsPage.path)

    LoginPage(page).expect_loaded()


@pytest.mark.regression
@requirement("MERCH-DELETE")
@allure.title("A session outlives its merchant for nothing: the page asks to log in")
def test_session_of_a_deleted_merchant_leads_to_the_login_page(
    merchant_page: Page, merchant: MerchantAccount, admin_api: MerchantsApi
) -> None:
    payments = PaymentsPage(merchant_page)
    payments.open()

    admin_api.delete(merchant.id).expect_no_content()
    merchant_page.reload()

    LoginPage(merchant_page).expect_loaded()


@pytest.mark.regression
@requirement("PAY-ACCESS")
@allure.title("An admin sees the merchant list and no merchant navigation")
def test_admin_sees_the_merchant_list_and_no_merchant_navigation(
    admin_page: Page, merchant: MerchantAccount
) -> None:
    admin = AdminPage(admin_page)
    admin.open()

    expect(admin.role_badge).to_have_text("admin")
    expect(_main_heading(admin_page)).to_have_text("Merchants")
    expect(admin.merchant_row(merchant.id)).to_contain_text(merchant.email)
    expect(admin.payments_link).to_have_count(0)
    expect(admin.new_payment_link).to_have_count(0)


@pytest.mark.regression
@requirement("PAY-ACCESS")
@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/ui/payments/new", id="new-payment-form"),
        pytest.param("/ui/payments/00000000-0000-4000-8000-000000000000", id="a-payment"),
    ],
)
@allure.title("An admin who opens a merchant page lands on the merchant list")
def test_admin_who_opens_a_merchant_page_lands_on_the_merchant_list(
    admin_page: Page, path: str
) -> None:
    admin_page.goto(path)

    expect(admin_page).to_have_url(re.compile(r"/ui/payments$"))
    expect(_main_heading(admin_page)).to_have_text("Merchants")


@pytest.mark.regression
@requirement("PAY-ACCESS")
@allure.title("An admin cannot use the page's status endpoint")
def test_admin_cannot_use_the_status_endpoint(
    admin_page: Page, merchant: MerchantAccount, api: PaymentsApi
) -> None:
    payment = api.create().expect(201)

    response = admin_page.request.get(f"/ui/payments/{payment.id}/status")

    assert response.status == 401
