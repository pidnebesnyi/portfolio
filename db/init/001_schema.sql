-- Schema for the payments lab. Money is stored as integer minor units (1050 = 10.50).
-- Child tables cascade from merchants so test cleanup is a single DELETE /merchants/{id}.

CREATE TABLE merchants (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text        NOT NULL,
    email       text        NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email          text NOT NULL UNIQUE,
    password_hash  text NOT NULL,
    role           text NOT NULL CHECK (role IN ('merchant', 'admin')),
    merchant_id    uuid REFERENCES merchants (id) ON DELETE CASCADE,
    totp_secret    text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    -- merchants belong to a merchant, admins to nobody
    CHECK ((role = 'merchant') = (merchant_id IS NOT NULL))
);

CREATE TABLE payments (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id      uuid        NOT NULL REFERENCES merchants (id) ON DELETE CASCADE,
    amount           integer     NOT NULL CHECK (amount > 0),
    currency         text        NOT NULL CHECK (currency IN ('UAH', 'USD', 'EUR')),
    description      text        NOT NULL DEFAULT '',
    card_token       text        NOT NULL,
    status           text        NOT NULL CHECK (status IN (
        'created', 'authorized', 'captured', 'partially_refunded',
        'refunded', 'voided', 'failed')),
    failure_reason   text,
    refunded_amount  integer     NOT NULL DEFAULT 0,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    -- last line of defence: even a buggy app cannot refund more than was paid
    CHECK (refunded_amount >= 0 AND refunded_amount <= amount)
);
CREATE INDEX payments_merchant_created_idx ON payments (merchant_id, created_at DESC);

CREATE TABLE refunds (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id  uuid        NOT NULL REFERENCES payments (id) ON DELETE CASCADE,
    amount      integer     NOT NULL CHECK (amount > 0),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX refunds_payment_idx ON refunds (payment_id);

CREATE TABLE idempotency_keys (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key           text        NOT NULL,
    merchant_id   uuid        NOT NULL REFERENCES merchants (id) ON DELETE CASCADE,
    request_hash  text        NOT NULL,
    payment_id    uuid        NOT NULL REFERENCES payments (id) ON DELETE CASCADE,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (key, merchant_id)
);
