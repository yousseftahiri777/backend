# LAMÁ admin and order security deployment

## Production environment

Generate a different 32-byte value for each secret:

```powershell
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLower()
```

Backend:

```dotenv
APP_ENV=production
BACKEND_PROXY_SECRET=<random-1>
ORDER_TOKEN_SECRET=<random-2>
ADMIN_USERNAME=<new-admin-username>
ADMIN_PASSWORD=<new-password-with-at-least-16-characters>
ADMIN_JWT_SECRET=<random-3>
ENABLE_LEGACY_ADMIN_ACCESS_KEY=false
ADMIN_ACCESS_KEY=
GEO_FAIL_OPEN=false
TEST_PHONE=
GOOGLE_SHEETS_WEBHOOK_URL=<apps-script-exec-url>
GOOGLE_SHEETS_WEBHOOK_SECRET=<random-4>
MAXMIND_ACCOUNT_ID=<production-account-id>
MAXMIND_LICENSE_KEY=<production-license-key>
```

Frontend:

```dotenv
BACKEND_INTERNAL_URL=http://backend:8000
BACKEND_PROXY_SECRET=<random-1>
```

Rotate the old admin key and passwords. Do not reuse secret values.

## Google Apps Script

1. Replace the spreadsheet Apps Script with `google_apps_script.js`.
2. Add Script Property `WEBHOOK_SECRET=<random-4>`.
3. Deploy a new Web App version as the owner with access set to Anyone.
4. Save its `/exec` URL as `GOOGLE_SHEETS_WEBHOOK_URL`.

Orders are written to the `Orders` tab and updated by Order ID without duplicate
rows. Customer-controlled cells are escaped against formula injection.

## Coordinated migration deployment

Migration `006` converts money columns, adds uniqueness, and queues historical
orders for Sheet reconciliation:

1. Take a PostgreSQL backup.
2. Stop checkout traffic or scale the old backend to zero.
3. Deploy backend and wait for `alembic upgrade head`.
4. Confirm `/health` reports `healthy` and `database: connected`.
5. Deploy frontend with the matching proxy secret.
6. Re-enable checkout.

Do not run old and new writers concurrently during migration `006`. Keep
PostgreSQL private and prefer an internal-only backend service.

## Test order

1. Submit one order from a valid KSA non-VPN connection.
2. Verify retry/double-click creates only one order.
3. Accept an upsell and confirm the server total.
4. Log in at `/admin/login` and locate the order.
5. Confirm Sheet state is `synced` and only one row exists.
6. Change status to `confirmed`, then `delivered`; the same row must update.
7. Confirm confirmed/delivered revenue cards update.
8. If needed, use Retry Sheet Sync from the order preview.
9. Confirm the old secret URL returns 404.

Historical orders remain admin-only because they predate public order tokens,
but migration `006` still reconciles them to the Sheet.
