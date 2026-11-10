# Go Daily — Security review (Task 25)

Reviewed 2026-10-30 against the Task 25 checklist. Each area lists what is in place, how it is tested, and what remains a risk. Deployment-side controls (TLS, edge rate limits, secrets) are in [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Authentication

- Opaque random session tokens. Only their SHA-256 hash is stored, so a database leak does not expose usable tokens. Admin sessions last 12 h, driver sessions 30 days, and any session expires after 72 h idle.
- Passwords are hashed with Argon2id. The per-account lockout is 5 failures for 15 minutes and is audited.
- **No account-existence leaks (U33).**
  - **One answer.** A wrong password, an unknown or malformed phone number, and a locked account get the same 401 `invalid_credentials` response and message. The password is checked against a dummy hash, or against the real one while locked, so the timing is the same too. The message says that repeated failures pause login for a while, so a real user knows to wait.
  - **Audit evidence:** unknown numbers are recorded masked, and locks record the remaining time.
  - **After a correct password:** only then does the response differ (account deactivated, wrong client type, the 2FA step, a lock at the code step). Whoever sees those already knows the password.
  - **Password resets:** there is no self-service reset; resets are done by administrators.
- Per-client-IP login throttle (60 attempts per 5 minutes, configurable). Because the admin web logs users in from its own server, the limit is generous and the edge proxy should add a stricter per-IP limit.
- **Re-authentication for sensitive actions (U35).**
  - **What needs it:** creating users, changing roles or account status, password and two-factor resets for others, company policy changes, and finalizing a settlement of at least `REAUTH_SETTLEMENT_AMOUNT` (10,000 EGP).
  - **What counts:** a login, or a confirmation of the password (plus the two-factor code when enabled), within `REAUTH_WINDOW_MINUTES` (10).
  - **Otherwise:** the API answers 403 `reauth_required`. The admin web sends the user to «تأكيد الهوية» and back to the page.
  - **Audit and limits:** confirmations and failed confirmations are audited (`auth.reauth`, `auth.reauth.failed`), and they share the per-user sensitive-action rate limit.
  - **Reading** is never blocked.
- **Security event dashboard (U36).** «أحداث الأمان» (`/security`, `GET /security/events`, `settings:manage`) summarises the audit log for the last 24 h, 72 h or a week:
  - **Counts:** failed logins (per-hour chart, with a spike warning at 20 or more in an hour), lockouts, wrong two-factor codes, failed re-confirmations, two-factor resets or disables, admin password resets, permission denials and attempts on unknown numbers.
  - **Top sources:** the accounts and addresses with the most failures.
  - **Recent events.**
  - **Configuration warnings:** not in production, privileged accounts without two-factor login, two-factor login not enforced, no shared rate-limit store, metrics off, bootstrap password still set.
  - **Permission denials** are now audited (`auth.permission_denied`, with the route template, method and missing permission), since staff never see actions they cannot use.
  - **Never shown:** secrets, codes or national IDs. Unknown numbers appear only masked, as the audit log stores them.
- **Distributed rate limits (U32).**
  - **Shared count:** with `REDIS_URL` set, the login, 2FA-code and sensitive-action limits are counted in a Redis-compatible store, so every API worker and server shares one count (fixed windows, atomic `INCR` + `EXPIRE`). Spreading attempts across workers does not get around them.
  - **Sensitive actions** (password change, enabling or turning off 2FA, new recovery codes) are limited per user: 10 per 15 minutes.
  - **Privacy:** keys (IPs, user ids) are hashed before they are stored, and counters expire with their window.
  - **When the store fails:** each request falls back to the in-process limiter. Limits stay on (per worker) rather than being switched off, and the database-backed account lockout still applies. Each failure is logged (`ratelimit_backend_unavailable`) and counted (`godaily_ratelimit_backend_errors_total` on `/metrics`), and should alert if it keeps rising.
  - **Without `REDIS_URL`** the limits are per process, which is fine for a single worker or development.
- Staff accounts cannot use the mobile client and driver accounts cannot use staff endpoints.
- Deactivating a user or resetting a password revokes all of that user's sessions.
- No default accounts. The first `SUPER_ADMIN` comes from one-time environment variables.
- **Two-factor login (U31).** Staff can protect their account with TOTP (RFC 6238, any authenticator app); `TWOFA_ENFORCE` makes it mandatory for `TWOFA_REQUIRED_ROLES`.
  - **Login:** the password step returns only an encrypted, 5-minute challenge (no session and no user details). The code step opens the session.
  - **Codes:** a code is accepted once (the last used time step is stored), with one step of clock drift either way. Wrong codes count towards the account lockout.
  - **Storage:** secrets are stored Fernet-encrypted with `DATA_ENCRYPTION_KEY`. The 10 recovery codes are shown once and stored as SHA-256.
  - **Turning it off and new recovery codes** need the password and a current code. Required roles cannot turn it off.
  - **Admin reset:** an administrator can reset two-factor login for a user who lost their phone. It needs a reason, follows the same role rules as password resets, and ends that user's sessions.
  - **Audit:** setup, enable, disable, renewal, reset, failed codes and the login method (password, TOTP or recovery code) are audited. Secrets and codes are never logged or audited.
- Tests: `test_auth.py`, `test_users_rbac.py`, `test_security.py::test_login_is_throttled_per_client`, `test_two_factor.py`, `test_totp.py`, `test_ratelimit_shared.py`, `test_reauth.py`, `test_security_events.py`.

## Authorization and least privilege

- Every staff route declares its permissions through `require_permissions(...)`, enforced in the API. Hiding things in the web is never the control.
- `test_security.py` generates the checks from the route table, so new routes are covered automatically:
  - every route except health checks and login returns 401 without a session;
  - every route is classified: it declares permissions, is driver-only, or is on an explicit allowlist of "own data" routes;
  - for every staff role and every route, a role missing a permission gets 403;
  - driver accounts get 403 on every non-driver route, and staff get 403 on driver routes.
- **Change made in this review:** accountants no longer have `tracking:read`. They work from approved records and per-shift distances, not live positions or routes, and drivers' location is personal data. They still see the evidence attached to the review cases they handle.
- Least-privilege rules are pinned in `test_role_permission_matrix_least_privilege`:
  - only admins manage users, read the audit log or see national IDs;
  - operations cannot write revenue or finalise settlements;
  - accountants cannot edit vehicles or see tracking.

## IDOR

- Single company: staff access is by role, not by record owner.
- Records that belong to one person are scoped in the service and covered by tests:
  - sessions and notifications belong to the caller; another user's notification returns 404;
  - driver-app endpoints act on the logged-in driver's own profile, shifts, fuel entries and receipts.
- Files follow the permissions of the record that owns them. A driver can attach a receipt only to their own pending entry.
- IDs are UUIDs, but nothing relies on them being unguessable.

## Mass assignment and input validation

- Request bodies are Pydantic models listing the accepted fields. Services copy fields one by one; nothing does `setattr(model, **body)`.
- Role, active state, approval, finalisation and voiding each have their own endpoint with its own check. Tests cover role escalation: an admin cannot create or promote to admin roles or modify a super admin.
- Field limits:
  - Money is `Decimal` with 2 decimal places, never floats.
  - Phone numbers are normalised, and Arabic digits are accepted.
  - Text lengths, enums, date ranges and coordinates are bounded.
  - Reports allow at most one year and 20,000 rows.

## Uploads

- The file type is detected from the content, not from the extension or the browser. Only JPEG, PNG, WebP and PDF are accepted, up to 10 MB.
- Storage keys are generated by the server. Original file names are kept as metadata only.
- Storage is private. Files are served only through the API after a permission check, with `nosniff` and a sandbox CSP. They are never served from a public bucket.
- Deletion is a soft delete with a reason and is audited. Evidence locks once a record is approved or voided.

## Tokens on clients

- Admin web: the token is kept in an `httpOnly`, `SameSite=Lax` cookie (`Secure` when `SESSION_COOKIE_SECURE=true`), and the browser never sees it. Server actions check bound arguments (`lib/bound.ts`), and redirects only go to internal paths.
- Driver app: the token is encrypted with an AES-GCM key held in the Android Keystore. Backups are disabled, release builds are HTTPS-only, and requests are never logged.

## CORS and headers

- CORS allows only the origins in `CORS_ORIGINS`. The admin web calls the API from its server, so browsers do not need CORS for it.
- API responses send:
  - `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`;
  - `Cache-Control: no-store`, because responses carry personal and financial data;
  - HSTS in production.
- **The admin web's CSP (U34)** is set per request in `src/proxy.ts` with a fresh nonce. Next.js puts the nonce on its own scripts, and every page is rendered per request so each one gets it.
  - `script-src 'self' 'nonce-…' 'strict-dynamic'`: no `'unsafe-inline'` and, in production, no `'unsafe-eval'`. An injected inline script cannot run.
  - `style-src 'self' 'nonce-…'` for style elements.
  - **Remaining exception:** `style-src-attr 'unsafe-inline'`. React `style={…}` and the map library (Leaflet) position elements with style attributes. Style attributes cannot run script.
  - **Images:** may come from HTTPS sources (map tiles) and `data:` (the 2FA QR code).
  - **Requests:** same-origin requests and forms only; `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`.
  - **Other headers:** `nosniff`, frame denial, referrer and permissions policies.
  - **Development server:** keeps `'unsafe-eval'` and inline styles for hot reload.
  - **Checked** on the production build in a browser: login, dashboard, live tracking map, shift map, account (2FA QR), pilot, review cases, cash and vehicles, with no CSP violations; all page scripts carry the nonce. Recheck after adding a third-party script or a new map provider.
- In production, OpenAPI docs are disabled.

## Logging and error leakage

- Logs are JSON lines with a request ID. They record the path but never the query string, and Uvicorn's access log is turned off.
- Values are scrubbed by key, even when passed by mistake: passwords and hashes, tokens and authorisation headers, cookies, idempotency keys, encryption and storage secrets, national IDs, phone numbers and coordinates (`test_logs_scrub_sensitive_and_personal_fields`).
- Unhandled errors return a generic Arabic message, and details go only to the log. Validation errors never repeat the submitted values (`test_validation_errors_do_not_echo_input`).

## Location data retention

- Points recorded outside a shift are refused and never stored. For integrity review only their count and time range are kept (`docs/GPS_INTEGRITY.md`).
- Raw GPS points of finished shifts are deleted after `GPS_RETENTION_DAYS` (default 180) by `python -m app.cli prune-gps`.
- The same job removes coordinates from the evidence of **closed** review cases older than that period. Times, durations and distances stay, so the review record remains readable. Open cases keep their evidence until they are reviewed (`test_old_closed_cases_lose_their_coordinates`).

## Audit integrity

- `audit_logs` is append-only, enforced by PostgreSQL triggers that block `UPDATE`, `DELETE` and `TRUNCATE`.
- Each entry records the actor, role, IP, user agent, request ID, field-level changes and the reason.
- Financial corrections create new linked rows instead of editing old ones, and review steps on exception cases are audited.

## Dependency vulnerabilities

- `make audit` runs `pip-audit` on the API's runtime dependencies and `pnpm audit --prod` on the web.
- On 2026-10-30 both reported **no known vulnerabilities**: 119 Python packages and the Node production tree.
- Android dependencies are pinned in `gradle/libs.versions.toml` but are not scanned automatically. Review them before each release.

## Residual risks and follow-ups

| Risk | Why it remains | Suggested follow-up |
| --- | --- | --- |
| Web CSP allows `'unsafe-inline'` scripts | Next.js inline bootstrap scripts need nonces, which would make every page dynamic, and the app is already authenticated and dynamic | Add nonce-based CSP via the Next.js proxy when convenient |
| Login throttle is per API process | No shared store (Redis) is part of the stack | Edge proxy rate limit (documented in DEPLOYMENT.md) |
| No second factor for admins | Not in scope for v1 | TOTP for `SUPER_ADMIN`/`ADMIN` |
| The lockout message shows that an account exists | After 5 failures a real account gets "temporarily locked" while an unknown number keeps getting "wrong credentials" | Return the generic message while locked (keeping the audit entry), or lock by phone number whether or not it exists |
| Sessions are not bound to a device | Simpler mobile re-login | Device binding for driver sessions if tokens leak in practice |
