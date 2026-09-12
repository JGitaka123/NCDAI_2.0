# Security and privacy engineering review

Reviewed 12 September 2026. Scope: source inspection, dependency advisories and automated synthetic-record regression tests. This is an engineering review, not an independent penetration test, regulatory approval or evidence of safe clinical deployment.

## Changes from the review

| Finding | Implemented control | Regression evidence |
| --- | --- | --- |
| An AI request could persist after its initiating session was revoked during provider latency | Reauthenticate the original opaque session and recheck active clinical role after the external response, before persisting any result | Logout, expiry, disabled-account and role-change cases verify unchanged encounter version and no stored briefing |
| Administrator accounts inherited clinical record read access | Clinical roles are required for patient lists/details, encounter records, referral lists and FHIR exports. Administrators retain aggregate counts, account management and audit metadata | Every affected route is denied to the administrator |
| Per-field validation happened after an unbounded request body had been received | An outer ASGI envelope caps mutation bodies at 1 MiB, checks actual streamed bytes, and sets a 15-second body delivery deadline | Oversized declared and undeclared/chunked requests never reach the application |
| Malformed Host values could influence request URL interpretation | Reject malformed or duplicate Host values before routing; the SQLite lock uses the original ASGI path | Slash, backslash, userinfo, query and fragment payloads are rejected |
| Early rejection responses missed security headers | Response envelope covers successful responses and controlled errors with no-store, nosniff, no-referrer, frame denial and disabled unnecessary browser capabilities; secure-cookie configuration adds HSTS | Validation and cross-origin errors have the required headers |
| Pair-only login throttling could be bypassed by rotating identities or network sources | Ten attempts per account/source pair, 30 per account and 100 per source in ten minutes; keyed digests protect stored identities. PostgreSQL locks each bucket in consistent order across workers | Pair limit, rotating-account source limit and independent account-bucket tests |
| Outdated dependency versions had published advisories | FastAPI 0.141.1 / Starlette 1.6.0 and pytest 9.1.1 pinned; local installer updated to pip 26.2.1 | Dependency audit and complete backend suite are recorded in the release test evidence |

Existing controls retained: facility scope on server-side queries, parameterized SQL, same-origin mutation checks, session-bound CSRF, opaque HttpOnly SameSite cookies, bounded session lifetime, active-account enforcement, salted password hashing, immutable reviewed encounters, optimistic encounter versions, audit records in the same database transaction, bounded clinical fields and redacted validation/database conflict responses. AI keys remain server-side; provider URLs are fixed, redirects/environment proxies are disabled, and provider response bytes and total elapsed time are bounded.

The initial package audit identified vulnerable `starlette`, `pytest` and local `pip` versions. Its 28 advisory records included duplicate vulnerability identifiers; that number is not a count of 28 distinct defects in this application. Relevant primary references are [Starlette's published advisories](https://github.com/Kludex/starlette/security/advisories), the [Host validation advisory](https://github.com/Kludex/starlette/security/advisories/GHSA-86qp-5c8j-p5mr), [FastAPI releases](https://pypi.org/project/fastapi/), [pytest releases](https://pypi.org/project/pytest/) and [pip-audit](https://github.com/pypa/pip-audit).

## Deployment and governance work still required

This release is restricted to synthetic records. Live patient deployment requires approved identity administration, data handling and clinical governance. Do not interpret a synthetic marker as automatic de-identification of user-entered text.

The hosting operator must provide HTTPS, an ingress hostname allowlist, trusted proxy configuration, connection/rate limits, appropriately restricted PostgreSQL credentials, encrypted disks/backups, tested restoration, patching and access logging without clinical payloads. The application rejects malformed Host syntax; it does not choose the organization's production hostname. Ingress must reject other valid but unapproved names.

Set `NCDAI_PUBLIC_ORIGIN` to the exact browser origin when a reverse proxy uses an internal upstream hostname. Production requires an explicit HTTPS origin. For the bundled local Vite preview use `http://127.0.0.1:5173`. The application never treats arbitrary forwarded headers as authorization for an Origin. Configure the ingress to serve frontend and `/api` through that same public origin; an origin setting alone does not enable cross-origin cookies or CORS.

Administrator provisioning authority can create clinical accounts and therefore needs personnel controls and audit review. MFA/SSO, a complete access-revocation administration workflow, external audit anchoring and tamper-resistant log retention remain deployment requirements. The database hash chain alone cannot detect a privileged full-history rewrite or deletion of its unanchored tail.

The login limiter bounds database-backed account/source buckets. Edge controls are still needed against distributed volumetric attacks and slow connections. External AI use also requires provider account spending limits, controlled user access and operational rate monitoring; provider timeout/byte limits do not impose an account monetary budget.

Retention schedules, breach response, controller/processor agreements, transfer safeguards, Kenyan regulatory obligations and any vendor data processing approval require the responsible organization's review. This document does not claim legal compliance or certification. Real Aifya/QAfya connectivity and patient-data transfers remain outside the standalone release.

## Reproduce

Run the complete backend suite with `python -m pytest tests -q`, including `tests/test_security_review.py`. Run `python -m pip_audit` in the installed backend environment, and separately audit the release container because operating-system packages and platform-specific dependencies differ. The final release report must state the observed result; installing patched versions alone is not evidence that a scan passed.

Observed after dependency updates: `python -m pip_audit --format json` exited **0**, reporting **No known vulnerabilities found** across **59 installed dependencies**, including test/audit tooling, in the Windows backend environment on 12 September 2026. The complete backend run passed **98 tests**, with **8 optional live-provider tests skipped**. The dedicated security regression run passed **16 tests**, and the later focused public-origin/production-configuration run passed **10 tests**. These runs overlap and should not be summed as distinct test counts. Two upstream test-client deprecation warnings remain; neither reported a test failure.
