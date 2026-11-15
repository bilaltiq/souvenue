# Deploy Souvenue to Vercel

This version is prepared for an early hosted beta. It keeps the existing
JavaScript UI and Python business logic, adds a Flask entrypoint, and uses
Postgres for durable data. Supabase Auth and Storage are not integrated yet:
accounts still use the application's password/session system, and small photos
are stored in Postgres. These are deliberate beta limitations, not a completed
public-launch backend.

## 1. Create a Supabase database

1. Create a project at https://supabase.com/dashboard (choose a region close to
   your users and Vercel function region).
2. Save the database password in your password manager.
3. Open **Connect > Session pooler** and copy the Postgres URI. The Session
   pooler works over IPv4 and supports the build-time importer. A Transaction
   pooler URI also works; prepared statements and pipelining are disabled in
   the adapter.
4. Replace `[YOUR-PASSWORD]` with your database password. URL-encode special
   characters in the password. Append `?sslmode=require` (or `&sslmode=require`
   if the URI already has a query string).

Use the database URI, **not** the Supabase project URL or anon key. Do not paste
the URI into GitHub, browser JavaScript, screenshots, or chat. Add it directly
to Vercel's environment variable form.

## 2. Import the GitHub repository into Vercel

1. Sign in at https://vercel.com/new using GitHub.
2. Import `bilaltiq/souvenue`. Grant Vercel access to this repository if needed.
3. Set **Root Directory** to the repository root (`./`). The source files should
   be directly at the root, not inside the original ZIP's nested directories.
4. Select **Flask** as the framework if it is not detected automatically.
5. Leave Install Command and Output Directory at their defaults. The repository
   sets Build Command to `python scripts/init_db.py`; keep that value.
6. Add these environment variables before clicking Deploy:

| Variable | Value | Scope |
| --- | --- | --- |
| `DATABASE_URL` | Your Postgres pooler URI with `sslmode=require` | Production |
| `ENCORE_DEMO_CHECKINS` | `0` | Production |

For previews, use a separate test database and a separate Preview-scoped
`DATABASE_URL`. Do not point untrusted pull-request previews at the production
database. A preview without a database URI will intentionally fail its build.

The build initializes tables and imports the bundled event snapshots. It does
not delete existing accounts or posts. Initialization takes a transaction lock
so concurrent builds cannot race schema creation. Future breaking database
changes need versioned migrations before enabling automatic deployment.

The application schema is `souvenue`, not Supabase's exposed `public` schema.
Leave it out of Supabase's Data API exposed schemas. Only the Python backend
should connect to it using the secret database URI.

## 3. Verify the live deployment

1. Open `/api/health`; expect `{"database":"postgres","ok":true}`.
2. Create two accounts using throwaway passwords. Sign out and sign back in.
3. Create a concert log, a community, a thread, and a small photo post.
4. Make one profile private. Confirm the other account cannot see its photo,
   including by opening the image URL directly. Accept a friend request and
   confirm the permitted view works.
5. Redeploy, sign in again, and confirm the saved records still exist.
6. Check that `/studio` is unavailable, the event-edit API is forbidden, and
   simulated check-ins are disabled.
7. Inspect Vercel function logs for failures. Never publish connection strings.

## 4. Attach your domain

In Vercel **Project > Settings > Domains**, add your domain and `www` hostname.
At your registrar/DNS provider, create the exact records Vercel displays.
Do not substitute guessed IP addresses. If using Cloudflare DNS, start with
the records set to **DNS only** while Vercel verifies the domain and provisions
HTTPS. Choose one canonical hostname and configure the other to redirect.

No domain purchase is required to test: the provided `.vercel.app` URL works.
Domain registration has no effect on iOS/Android compatibility.

## Current limits and launch work

- Hosted uploads: 2 MB per photo, 2.8 MB total per post, up to 10 photos.
  Images are served through private-access-checked endpoints rather than large
  inline feed JSON. Move media to object storage before significant traffic.
- Feed results are capped at the newest 50 posts; full pagination remains work.
- Password recovery, verified email, account deletion, abuse rate limits,
  reporting/blocking, and moderator tools remain public-launch requirements.
- GPS proximity does not prove attendance against spoofing. NFC remains a local
  simulation and is disabled on hosted deployments. Points have no cash value.
- Event information is a saved snapshot. There is no automatic refresh job.
  Review source-data terms and artist-photo licenses before public promotion.
- Database backups do not become verified recovery until a restore is tested.

## Local development

Install Python 3.12 or 3.13, then from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python server.py
```

Without `DATABASE_URL`, the original local server uses SQLite and creates its
tables automatically. `.env` files are ignored by Git and are not automatically
loaded; set environment variables in your shell if testing Postgres locally.

```powershell
.\.venv\Scripts\python -m unittest test_app.py test_deployment.py
```

Official references:
- https://vercel.com/docs/frameworks/backend/flask
- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://vercel.com/docs/domains/working-with-domains/add-a-domain
