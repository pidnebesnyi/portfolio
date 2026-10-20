Feature: Safe retries of a payment request
  If a merchant's system repeats a request because it never saw the answer,
  the customer must not be charged twice.

  Scenario: Repeating a payment request returns the same payment
    Given the merchant has sent a request for a 5.00 UAH payment
    When the merchant sends exactly the same request again
    Then the merchant gets the same payment back, marked as a repeat
    And the merchant has only one payment
