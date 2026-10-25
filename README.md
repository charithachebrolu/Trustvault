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

## Deploy a public demo on Render

The repository includes a Render Blueprint and Dockerfile. The Docker image builds the React app and serves it from FastAPI, so the website and API use the same public origin. This avoids a separate frontend/API proxy and cross-origin cookie setup. The Blueprint uses Render's free web service and does not attach a persistent disk.

1. Push the project to GitHub and make sure the repository contains `render.yaml`, `Dockerfile`, and `.dockerignore`.
2. Sign in to Render, choose **New → Blueprint**, connect the TrustVault GitHub repository, and select the branch to deploy.
3. Confirm the Blueprint shows the **Free** plan and no persistent disk, then deploy it. It generates `TRUSTVAULT_SECRET_KEY` and writes the SQLite database and uploaded files under `/tmp`.
4. Render builds the frontend and API into one Docker image. Wait until the service status is **Live**.
5. Open the service's public `https://…onrender.com` URL. Check `https://…onrender.com/health`; it should return `{"status":"ok","database":"ok"}`.
6. In the public website, create two test accounts and use fake documents to check upload, sharing, view-only denial, audit activity, revocation, and download. Do not upload confidential or real personal files to this prototype.

This free setup is for a temporary demo. Render free services sleep after inactivity and can take about a minute to wake. Their filesystem is temporary, so the SQLite database and uploaded documents may be erased after a restart or deployment; create test accounts and upload demo files again if that happens. For durable documents, a paid persistent disk or external database/file storage is required. The deployment URL is created by Render; it will not be `127.0.0.1`. A deployment is not created until you connect the repository and apply the Blueprint in your Render account. Pushing a later commit to the deployed branch triggers a new deployment by default.

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
