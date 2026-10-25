# TrustVault

TrustVault is a local document-sharing prototype built with React, TypeScript, Vite, FastAPI, and SQLite. Users can create an account, sign in, upload supported files, list and view their documents, and download them. Owners can grant an existing TrustVault account separate view and download permissions, optionally set an expiry, and revoke access later. Recent activity is also recorded.

## Project layout

- `backend/app`: FastAPI routes, SQLite setup, password hashing, and signed sessions.
- `backend/tests`: API integration tests using temporary SQLite databases and storage directories.
- `frontend`: React/Vite client.
- `THREATS.md`: prototype threat model and current mitigations.

## Requirements

Python 3.11+ and Node.js 20.19+ with npm.

## Start locally

From this directory:

```sh
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated value into `TRUSTVAULT_SECRET_KEY` in `.env`. Keep `.env` private.

After dependencies are installed, the easiest way to run both servers together is:

```sh
./start-trustvault.sh
```

Keep that terminal open. When Vite reports that it is ready, open <http://127.0.0.1:5173>. Press Ctrl+C in the terminal to stop both servers.

Backend (terminal 1):

```sh
cd backend
python -m venv .venv
. .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python -m app
```

Frontend (terminal 2):

```sh
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. The Vite development server proxies `/api` and `/health` to FastAPI at `127.0.0.1:8000`. SQLite and uploaded files live under `backend/` by default. The API initializes the database on startup. For a deployed HTTPS environment set `TRUSTVAULT_COOKIE_SECURE=true` and configure the allowed origins.

## Administrator account

Create and sign in to the account that should administer TrustVault. In a third terminal, from `backend/`, promote that existing account:

```sh
.venv/bin/python -m app.admin promote you@example.com
```

Replace the email with the account's email. Sign out and back in; the **Admin** button will appear. The admin page lists login accounts and lets the administrator disable or re-enable regular accounts. Admins cannot disable themselves or another admin. Disabled users are signed out immediately. Administrator promotion is a local operator command, so regular users cannot grant themselves admin access from the website.

## Tests and frontend build

```sh
cd backend
python -m pytest -q
cd ../frontend
npm run build
```

The backend tests use a fresh temporary database and local file directory for each test. No external API is required.

## Prototype scope

Sharing is limited to existing account emails. Owners choose whether recipients can view or download and may set an expiry. Permissions and expiry are checked by the API; revocation is immediate and retained in share history. Admins can disable regular accounts. The prototype does not implement company/tenant isolation, fine-grained roles, CSRF defenses for cross-site deployments, encrypted-at-rest file storage, rate limiting, password reset, malware scanning, or tamper-evident audit storage. The audit table is mutable by anyone with database file access. Do not use this prototype for sensitive production documents. See [THREATS.md](THREATS.md).
