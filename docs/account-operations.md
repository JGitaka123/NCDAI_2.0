# Account operations

Named accounts now support authenticated password change and administrator activation/deactivation. These controls retain the existing facility boundary, clinical roles, CSRF checks and audited transactions. They do not change the application's clinical release status.

## Password change

`POST /api/auth/change-password` accepts `current_password` and `new_password`. The current password must verify against the stored hash. A new password must have 14–256 characters, differ from the current password and contain a non-whitespace character. Intentional leading/trailing spaces are preserved. Five attempts in ten minutes are allowed per account; the next attempt returns 429 with `Retry-After: 600`.

Success returns `{"status":"password_changed","other_sessions_revoked":N}`. The current session and its existing expiry remain valid; all other sessions for the account are revoked in the same transaction as the password hash and audit event. Passwords never enter audit records. Other browsers must sign in using the new password. A database row lock serializes password verification/session issuance with account changes so a concurrent old-password sign-in cannot survive revocation.

Incorrect current passwords return 400, invalid new passwords return 422, missing authentication returns 401 and absent/invalid CSRF returns 403. A failed current-password check adds an audited failed-attempt event but does not change the password or revoke sessions. An unavailable server can leave the browser unsure of the outcome; verify sign-in before repeating the action.

## Activate and deactivate accounts

`PATCH /api/users/{user_id}/status` accepts a strict boolean `active`. Only an active administrator in that account's facility may perform this action. Cross-facility and unknown targets return 404. A last active administrator cannot be deactivated, and administrators cannot deactivate themselves even if another administrator exists. These conflicts return 409. The operation serializes competing facility account changes and rechecks the acting administrator's session and role after waiting for its lock.

Deactivation changes the active flag and revokes every target session atomically. Reactivation does not resurrect previous sessions: it also clears residual session rows, and the user must sign in again. The password is unchanged. Responses contain the public account fields and `active`, never a password hash. A request for the already-current status is idempotent and does not add a duplicate status-change audit event.

The existing administrator account list exposes active status, including inactive accounts. Existing clinician/supervisor rights remain distinct from account-administration rights. Audit actions are `user.password_change`, `user.password_change_failed`, `user.deactivate` and `user.reactivate`.

## Operator responsibilities remaining

Initial administrator provisioning remains a deliberate trusted operator task. Forgotten-password recovery without a valid current password, MFA/SSO, role-transfer approval, external audit anchoring and emergency recovery when no administrator can sign in still need a documented operator process. Do not resolve those incidents by disabling authentication or sharing another person's credentials. Account changes are not a substitute for the institution's authorization and offboarding decisions.

Regression coverage is in `backend/tests/test_account_lifecycle.py`; actual execution results belong to the release evidence. The project owner reports existing DHA/ethics approvals cover care and medication recommendations, with office copies pending archival in the release records. This account increment does not independently verify those documents or replace evaluation of new dosing functionality.

Observed verification for this increment: **18 primary lifecycle cases passed**, **two additional audit-failure rollback cases passed**, and **one real-PostgreSQL concurrency case passed**. The PostgreSQL case includes both a password-change/old-password-login race and competing administrator deactivations; the former leaves no usable old-password session and the latter leaves one active administrator with an intact audit chain. The 21 distinct cases were executed in three focused runs. Two upstream test-client deprecation warnings were reported. These are account-security engineering results, not dosing or clinical validation.

The PostgreSQL case is opt-in via `NCDAI_DATABASE_TEST_URL`, restricted to the dedicated loopback test databases; it is skipped when no such test database is configured. The standard cases require no external service or provider call. Run the complete file with `python -m pytest tests/test_account_lifecycle.py -q` from `backend/` after installing dependencies.
