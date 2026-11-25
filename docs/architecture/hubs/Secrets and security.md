---
type: hub
layer: cross
tags: [arch/hub]
generated: false
---
# Secrets and security

This hub covers the safety net around the app: how stored secrets are encrypted, how logs and error reports are scrubbed, how security-relevant actions are recorded, and how the cloud edge protects the API. The ideas are layered. A secret is encrypted at rest, never logged, and if it leaks into a message anyway a pattern-based redactor catches it. Requests in the cloud edition must come through the trusted Cloudflare edge and are rate limited before they reach the routes.

## How it works
- **Encryption at rest.** [[secrets_crypto]] has two ciphers chosen by edition. Local uses a Fernet key from `PORTFYL_LOCAL_SECRET_KEY`. Cloud calls Google Cloud KMS directly (key name in `PORTFYL_KMS_KEY_NAME`); KMS does the envelope encryption. Each value is stored as ciphertext plus a key version, so a later rotation can find what to re-encrypt. Broker keys and Discord webhook URLs use it ([[broker_connections (table)]], [[discord_webhooks (table)]]).
- **Moving old secrets.** [[0004_broker_secrets_expand]] and [[0005_discord_webhook_expand]] added the encrypted columns, [[migrations.encrypt_existing_secrets]] re-encrypts old rows, and [[0006_broker_secrets_contract]] and [[0007_discord_webhook_contract]] dropped the plaintext ones (expand, then migrate, then contract).
- **Redacted logging.** [[logging_setup]] installs one root handler that stamps a correlation id and redacts secret shapes (Discord webhook tokens, `Authorization` values, session and CSRF cookies, Stripe keys, IBKR Flex token, Brevo key, Firebase `oobCode`). Broker keys have no shape, so the real defence is never logging them.
- **Sentry.** [[error_monitoring]] is opt-in through `SENTRY_DSN`. It turns off PII and request bodies and runs every message and breadcrumb through the same `redact()`. The browser side is [[src.errorMonitoring]].
- **Audit log.** [[audit]] `record_audit_event` stages a row in [[audit_logs (table)]] in the same transaction as the change it describes, and passes metadata through the redactor. The runtime role only has SELECT and INSERT on the table ([[0009_audit_log]]), so rows cannot be edited or deleted by the app.
- **CSP and headers.** [[security_headers]] builds the Content-Security-Policy. It allows PostHog, Firebase, Sentry, the Google sign-in scripts (only if `PORTFYL_FIREBASE_AUTH_DOMAIN` is a valid hostname) and Cloudflare Turnstile (only when enabled). `frame-ancestors` is `'none'` in cloud and `'self'` in local.
- **Trusted edge.** [[edge_trust]] checks the `X-Portfyl-Edge-Token` header that Cloudflare injects; the token must match `PORTFYL_EDGE_TOKEN`, which the cloud edition requires at startup. [[cloud_gate]] is the middleware that runs this check, then the global per-IP rate limit, on every `/api` request.
- **Rate limiting.** [[rate_limit]] is a fixed-window limiter stored in [[rate_limit_buckets (table)]] ([[0012_rate_limit_buckets]]). Rules: `global`, `auth_session`, `broker_sync`, `auth_email` and `auth_email_target`. Limits come from `RATE_LIMIT_*` environment variables. Expired buckets are removed by a scheduler job (see [[Jobs and Cloud Scheduler]]).
- **Discord webhook validation.** [[discord_webhooks]] accepts only real Discord webhook endpoints (https, known hosts, no credentials, no port, strict path) and is re-checked before every outbound call, so a stored URL cannot be used for server-side request forgery.
- **Bot check and sessions.** See [[Auth and sessions]] for Turnstile, CSRF and revocable sessions.

## Key code
- [[secrets_crypto]]: Fernet and KMS ciphers, `build_secret_cipher`
- [[logging_setup]]: redaction patterns and correlation id
- [[audit]]: append-only audit events
- [[security_headers]]: CSP and related headers
- [[rate_limit]]: rules, buckets, `rate_limit` dependency
- [[edge_trust]]: trusted-edge token check
- [[cloud_gate]]: global cloud API gate middleware
- [[error_monitoring]]: Sentry setup and scrubbing
- [[discord_webhooks]]: webhook URL validator
- [[migrations.encrypt_existing_secrets]]: one-off re-encryption tool
- [[src.errorMonitoring]]: frontend error reporting

## Data
- [[audit_logs (table)]], [[rate_limit_buckets (table)]]
- [[broker_connections (table)]], [[discord_webhooks (table)]]
- [[0004_broker_secrets_expand]], [[0006_broker_secrets_contract]], [[0005_discord_webhook_expand]], [[0007_discord_webhook_contract]], [[0009_audit_log]], [[0012_rate_limit_buckets]]

## Related hubs
- [[Auth and sessions]]
- [[Tenancy and RLS]]
- [[Jobs and Cloud Scheduler]]
- [[Deploy and operations]]
- [[Alerts and integrations]]
- [[Broker importers and sync]]
- [[Backend]]
- [[Portfyl]]

## Docs
- [[superpowers/specs/2026-09-05-portfyl-rate-limiting-design]]: rate limiter and trusted edge design
- [[security/tenant-isolation-matrix]]: tenant isolation tests
- [[operations/security-incident-response]]: what to do when something leaks
- [[operations/incident-tabletop-2026-09-09]]: incident drill record
- [[compliance/data-processing-inventory]]: which data goes to which processor
