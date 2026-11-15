# Souvenue source code

For hosted deployment, see [DEPLOYMENT.md](DEPLOYMENT.md). Vercel uses the
Flask entrypoint in `app.py` and a secret `DATABASE_URL` for durable Postgres
storage. Local development can still use SQLite.

The concert logging and fan community prototype developed for Sofia. This package contains the full local app as of November 14, 2026.

## Run locally

Install Python 3.12 or newer from https://www.python.org/downloads/.
Extract this ZIP, open a terminal in this folder, and run:

```sh
python3 server.py
```

On Windows, use `py -3 server.py` if `python3` is unavailable.
Open http://127.0.0.1:4173/ on the same computer. Keep the terminal running. Stop with Control-C.

No Python packages, Node installation, build step, or API keys are required to run the app. The first start creates `demo.sqlite3` with event and community data. Create a new account in the app. Later starts retain your local data.

## Code map

- `server.py` — HTTP routes, account sessions, SQLite storage, posts, communities, concert logs, points, and check-in logic.
- `public/app.js` — browser navigation and interfaces.
- `public/style.css` — dark theme and responsive styling.
- `public/index.html` — application shell.
- `public/artists/` — artist photographs.
- `*.json` and `imports/` — saved artist, event, historical show, genre, photo attribution, and venue location data.
- `import_*.py` and `fetch_artist_*.py` — optional data refresh scripts. These require internet access. Review them before refreshing saved datasets.
- `test_app.py` — existing behavior tests.
- `DEVELOPMENT_HISTORY.md` — original development notes. Earlier sections describe earlier versions and are superseded by later entries and current code.

To run existing tests:

```sh
python3 -m unittest test_app.py
```

## Features in this prototype

Artist browsing and search, show pages, photo feeds and carousels, profiles and privacy settings, friends, communities and discussion threads, venue and show chats, manual concert history, location check-ins, simulated NFC tap check-ins, points, and leaderboards.

## Development settings

- `PORT` changes the port from 4173.
- `ENCORE_DB` chooses a different SQLite file.
- `ENCORE_DEMO_CHECKINS=0` disables simulated check-ins. The legacy ENCORE variable names are used by the current code.

For example, on macOS/Linux:

```sh
ENCORE_DEMO_CHECKINS=0 python3 server.py
```

## Launch status

This is a local development prototype. Production work includes hosted authentication and password recovery, permission-controlled administration, moderation and reporting, account deletion, backups, HTTPS deployment, and secure attendance verification. GPS proximity checks exist, while secure NFC tag verification still needs implementation. Points are prototype balances and have no redeemable value.

Event datasets are saved snapshots and may be out of date. Import scripts currently read public pages and are not an official Ticketmaster API integration. Review data access terms and image permissions before release.

The standalone public concert signup form is maintained in a separate project. This package contains the local concert app.

Existing user databases, sessions, personal posts, and organizer credentials are excluded from this source package.
