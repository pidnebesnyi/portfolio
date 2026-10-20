Feature: Refunding a payment
  A merchant can give money back to a customer in several parts,
  but never more than the customer paid.

  Scenario Outline: Refunds add up and never exceed the payment
    Given a captured payment of 10.00 UAH
    And the merchant has already refunded <already> UAH
    When the merchant refunds <asked> UAH
    Then the refund is <outcome>
    And the payment is <status> with <refunded> UAH refunded

    Examples: parts that fit
      | already | asked | outcome  | status             | refunded |
      | 0.00    | 3.00  | accepted | partially_refunded | 3.00     |
      | 3.00    | 2.00  | accepted | partially_refunded | 5.00     |
      | 5.00    | 5.00  | accepted | refunded           | 10.00    |

    Examples: parts that do not fit
      | already | asked | outcome  | status             | refunded |
      | 7.00    | 3.01  | rejected | partially_refunded | 7.00     |
      | 0.00    | 10.01 | rejected | captured           | 0.00     |
