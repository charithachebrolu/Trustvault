# Project prompts and scope

## Initial prototype prompt

Build a basic TrustVault secure document-sharing prototype using React + TypeScript + Vite, FastAPI, SQLite, and Pytest. Inspect and preserve the existing repository. Include database health/init, securely hashed passwords, backend authentication, owner-authorized document upload/list/download, local file storage, activity events, error handling, automated tests, and README/.env.example/.gitignore/THREATS.md/PROMPTS.md. Validate upload types and size, do not store plaintext passwords or secrets in frontend code, and document that the prototype is not production-safe until tenant isolation, permissions, and audit integrity are implemented and tested.

## Follow-up local verification prompt

Run FastAPI and React locally, run the automated tests, inspect and fix errors, and verify authentication, upload, listing, and authorized downloads against the real local database. Report only checks that actually pass.

## Deferred hardening scope

Implement company-level tenant isolation, fine-grained role-based access, and tamper-evident audit logging. Extend tests for cross-company access, unauthorized downloads, role escalation, and audit-log modification. Update THREATS.md with each threat, mitigation, and corresponding test. Run the tests and report actual results.

The initial prototype supports read-only document sharing with existing accounts and owner-controlled revocation. It also has a local-operator-promoted admin role for account activation controls. Company isolation, fine-grained permissions, and audit integrity remain deferred.
