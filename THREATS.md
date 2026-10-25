# TrustVault threat notes

This document describes the current prototype boundary. It is not a production security review.

| Threat | Current mitigation | Coverage / limitation |
|---|---|---|
| Password theft from the database | Passwords use Argon2id through `argon2-cffi`; plaintext is never stored. | `test_registration_hashes_password_and_sets_http_only_cookie` checks the stored representation. No password reset or credential-stuffing controls. |
| Anonymous access to private documents | Authentication is required for document list, upload, download, and audit routes. | API tests check unauthenticated listing and authenticated workflows. |
| Another local account accesses a document without permission | Listing and file access check ownership or an explicit share, its separate `can_view`/`can_download` grants, expiry, and revocation status on every API request. Owners can share only with an existing account email. | `test_documents_require_auth_and_are_isolated_by_owner` checks denied cross-user access; `test_share_view_download_and_revocation` checks grant and revocation; `test_separate_permissions_and_expiry_are_enforced_by_api` checks view-only, download-only, and expiry behavior. No company tenancy or fine-grained document roles exist. |
| A regular user manages accounts or an admin disables the wrong account | The admin API checks the stored role on every request. Promotion requires a local operator command. Admins can only enable/disable regular users; self-disable and admin-disable are rejected. Deactivated users are blocked on every authenticated request. | `test_admin_can_manage_regular_accounts_but_users_cannot` checks regular-user denial, deactivation, reactivation, and self-disable protection. |
| Malicious filename/path traversal | Storage uses a server-generated UUID filename; only the basename of the supplied filename is retained. | Upload/download test covers ordinary names; dedicated traversal fuzzing is not included. |
| Oversized or unsupported upload | Extension allow-list, streaming byte limit, and empty-file rejection; failed partial files are removed. | `test_upload_validates_extension_and_size` checks rejected extension and size. Content is not deeply inspected or malware-scanned. |
| Session token theft / script access | Signed expiring JWT stored in an HttpOnly, SameSite=Lax cookie. Secure-cookie flag is configurable for HTTPS. | Cookie properties are configured in backend. No CSRF token, key rotation, or server-side session revocation yet. |
| Audit event loss or modification | Basic events are written to SQLite and scoped to the actor in the UI/API. | Events are not tamper-evident; a database owner can alter or delete them. Hash chaining, signing, and integrity tests are not implemented. |
| Secret disclosure | Secret comes from environment and is excluded from Git; the frontend receives no signing key. | Example value is a placeholder; set a generated secret locally. |

## Explicit production gaps

Company-level tenant isolation, fine-grained role permissions, tamper-evident audit logging, CSRF defenses, HTTPS-only deployment, rate limiting, encryption at rest, backups, malware scanning, and an operational security review are required before handling real sensitive documents. The current prototype must not be treated as tenant-safe or production-ready.
