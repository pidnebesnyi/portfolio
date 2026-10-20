"""Payment state machine. One table, so the rules are readable and testable in one place.

created -> authorized -> captured -> partially_refunded -> refunded
created -> failed (provider declined / errored / timed out)
authorized -> voided
`authorized -> failed` is intentionally absent.
"""

from enum import StrEnum


class PaymentStatus(StrEnum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"
    VOIDED = "voided"
    FAILED = "failed"


class Action(StrEnum):
    AUTHORIZE = "authorize"
    CAPTURE = "capture"
    VOID = "void"
    REFUND = "refund"


# Statuses from which each action may start. The target status is decided by the handler,
# because authorize and refund have more than one possible outcome.
ALLOWED_FROM: dict[Action, frozenset[PaymentStatus]] = {
    Action.AUTHORIZE: frozenset({PaymentStatus.CREATED}),
    Action.CAPTURE: frozenset({PaymentStatus.AUTHORIZED}),
    Action.VOID: frozenset({PaymentStatus.AUTHORIZED}),
    Action.REFUND: frozenset({PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED}),
}


def can(action: Action, status: PaymentStatus) -> bool:
    return status in ALLOWED_FROM[action]
