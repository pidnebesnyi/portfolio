# Postman collection

`payments-qa-lab.postman_collection.json` is the API smoke in a form manual QA and developers can
open and click through. It runs the main path in 20 requests: health, admin login with a one-time
code, a new merchant, a payment created (and replayed with the same Idempotency-Key), authorized,
captured and partly refunded, the payment list, two access checks, and the merchant deleted again.
59 assertions; each response also has to carry `X-Request-ID`.

Folders are named after the requirement they check (`PAY-REFUND`, `AUTH-LOGIN`, ...), the same ids
the pytest suite uses, so a failed request points at a
[requirement issue](https://github.com/pidnebesnyi/portfolio/issues?q=label%3Arequirement).

The pytest suite stays the full regression; this collection is the hand-over: a quick check before
a demo, a request to copy into a bug report, a starting point for exploratory testing.

## In Postman

1. Start the stack (`docker compose up --build --wait db app provider-mock`).
2. Import both JSON files from this folder and select the `payments-qa-lab local` environment.
3. Put `ADMIN_PASSWORD` and `ADMIN_TOTP_SECRET` from your `.env` into the **current value** of
   `adminPassword` and `adminTotpSecret`. Current values stay on your machine; do not export the
   environment with them filled in.
4. Run the collection (Run collection, in order). The admin's one-time code is computed by the
   pre-request script of "Admin login, step 2", so no authenticator app is needed.

Each run creates its own merchant and deletes it at the end, so runs do not depend on existing
data. A run stopped halfway leaves that merchant behind; it does not affect the next run.

## With Newman

```bash
docker compose --profile postman run --rm newman
```

The `newman` service reads the credentials from `.env` through compose and passes them as
`--env-var`, so nothing secret is written to a file. The PR workflow runs the same command in the
`api` job after the pytest suite; a failed assertion fails the job.

## Changing it

Edit in Postman, export the collection (v2.1) over the file here and commit it. Keep the
environment file free of secret values: only `baseUrl` and `adminEmail` have defaults.
