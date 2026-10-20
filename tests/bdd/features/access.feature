Feature: Merchants only see their own payments
  Two merchants use the service side by side. One must never learn
  anything about the other one's payments.

  Scenario: Another merchant cannot see my payment
    Given a payment that belongs to the merchant
    When another merchant asks for that payment
    Then the payment is reported as not found
    And the owner still sees the payment unchanged
