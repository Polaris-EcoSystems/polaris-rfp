# Auth & sessions

## Symptoms

- Users report “I keep getting logged out”
- Magic link opens but user bounces back to `/login`
- `/api/session/refresh` returns 503 (temporary auth degradation)

## Evidence to collect

- **Reference ID** (`x-request-id`) from UI toast or `/support`
- User email domain and approximate timestamp
- Browser + network conditions (VPN, corporate proxy)

## Checks

1. **Backend logs** (CloudWatch): filter by `request_id` to see:
   - `/api/auth/magic-link/*` and `/api/auth/session/refresh` failures
   - Cognito errors (JWKS fetch, admin_get_user, invalid token)
2. **Cognito**:
   - User pool health / throttling
   - SES send failures for magic links (look for `SES send_email failed` logs from the Cognito trigger if applicable)
3. **Frontend/BFF**:
   - If refresh is unavailable, BFF will set `x-polaris-auth-refresh: unavailable` and avoid clearing cookies.

## Mitigations

- If refresh is degraded (503s):
  - Avoid forcing logouts; let sessions recover automatically when Cognito stabilizes.
  - Communicate status and recommend retry after a few minutes.
- If incorrect domain / allowlist:
  - Verify `ALLOWED_EMAIL_DOMAIN` / `NEXT_PUBLIC_ALLOWED_EMAIL_DOMAIN`.

## Follow-ups (hardening)

- Add synthetic canary: magic-link request + verify.
- Add alert: sustained `x-polaris-auth-refresh: unavailable` events (needs metric filter).
