from datetime import timedelta

import pytest
from playwright.sync_api import Page, expect

from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.pages.payment_detail_page import PaymentDetailPage
from tests.pages.payments_page import PaymentsPage
from tests.utils.allure_links import area, requirement

pytestmark = [pytest.mark.ui, area("UI payments"), requirement("PAY-LIST")]


@pytest.mark.regression
def test_payment_list_shows_own_payments_with_their_status(
    merchant_page: Page, payment_factory: PaymentFactory
) -> None:
    created = payment_factory.create(PaymentStatus.CREATED)
    captured = payment_factory.create(PaymentStatus.CAPTURED)
    payments = PaymentsPage(merchant_page)

    payments.open()

    payments.expect_total(2)
    expect(payments.status_of(created.id)).to_have_text("created")
    expect(payments.status_of(captured.id)).to_have_text("captured")
    payments.open_payment(captured.id)
    expect(PaymentDetailPage(merchant_page).status).to_have_text("captured")


@pytest.mark.regression
def test_status_filter_narrows_the_list_and_reset_restores_it(
    merchant_page: Page, payment_factory: PaymentFactory
) -> None:
    created = payment_factory.create(PaymentStatus.CREATED)
    authorized = payment_factory.create(PaymentStatus.AUTHORIZED)
    captured = payment_factory.create(PaymentStatus.CAPTURED)
    payments = PaymentsPage(merchant_page)
    payments.open()
    payments.expect_total(3)

    payments.filter_by(status="authorized")

    payments.expect_total(1)
    expect(payments.row(authorized.id)).to_be_visible()
    expect(payments.row(created.id)).to_have_count(0)
    expect(payments.row(captured.id)).to_have_count(0)
    expect(payments.status_filter).to_have_value("authorized")

    payments.reset_filter.click()

    payments.expect_total(3)
    expect(payments.status_filter).to_have_value("")


@pytest.mark.regression
def test_date_range_filter_includes_today_and_excludes_other_days(
    merchant_page: Page, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create()
    # The server stores UTC; the filter inputs are UTC days too, so derive them from the payment.
    day = payment.created_at.date()
    payments = PaymentsPage(merchant_page)
    payments.open()

    payments.filter_by(created_from=day.isoformat(), created_to=day.isoformat())
    payments.expect_total(1)
    expect(payments.row(payment.id)).to_be_visible()

    payments.filter_by(created_from=(day + timedelta(days=1)).isoformat())
    payments.expect_total(0)
    expect(payments.empty_state).to_be_visible()

    payments.filter_by(created_to=(day - timedelta(days=1)).isoformat())
    payments.expect_total(0)
    expect(payments.row(payment.id)).to_have_count(0)


@pytest.mark.regression
def test_status_and_date_filters_combine(
    merchant_page: Page, payment_factory: PaymentFactory
) -> None:
    refunded = payment_factory.create(PaymentStatus.REFUNDED)
    payment_factory.create(PaymentStatus.CAPTURED)
    day = refunded.created_at.date().isoformat()
    payments = PaymentsPage(merchant_page)
    payments.open()

    payments.filter_by(status="refunded", created_from=day, created_to=day)

    payments.expect_total(1)
    expect(payments.row(refunded.id)).to_be_visible()
