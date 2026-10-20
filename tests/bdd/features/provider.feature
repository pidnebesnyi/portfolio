Feature: Card declined by the payment provider
  The bank behind the provider can say no. The payment must not stay half-finished:
  it ends as failed and says why.

  @integration
  Scenario: A declined card ends the payment as failed with a reason
    Given a 12.50 USD payment with a card the provider will decline
    When the merchant authorizes the payment
    Then the payment has failed because it was declined
    And the provider was asked to charge the card exactly once
