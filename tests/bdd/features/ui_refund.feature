Feature: Refunding a payment in the browser
  A merchant who prefers the web page to the API can return money from the payment's own page.

  @ui
  Scenario: A merchant refunds part of a payment on its page
    Given a captured payment of 20.00 UAH
    And the merchant has the payment page open
    When the merchant refunds 5.00 UAH on the page
    Then the page shows the payment as partially_refunded with 5.00 UAH refunded
    And the payment is partially_refunded with 5.00 UAH refunded
