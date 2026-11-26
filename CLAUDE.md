# Souvenue — notes for Claude

Souvenue (souvenue.com) is a social concert logging app: browse artists and tour
dates, log shows you attended, check in (location / NFC tap), post photos, and
talk in show, venue and artist communities, with points and leaderboards.

## Stack
- Backend: Python. `app.py` is the Flask entry point Vercel runs; `server.py`
  holds routes and logic and also runs locally with the standard library.
  Local data is SQLite (`demo.sqlite3`); hosted data is Postgres via `DATABASE_URL`.
- Frontend: no build step. `templates/index.html` is the HTML shell that gets served
  (`public/index.html` is a copy, so keep both identical). `public/app.js` renders every
  page into `<main id="app">`; `public/style.css` holds all styles.
- Deploy: Vercel redeploys souvenue.com on every push to `main`
  (repo: github.com/bilaltiq/souvenue).

## Workflow
1. Edit the files.
2. Run `python3 server.py` and check http://127.0.0.1:4173 at desktop and
   phone width (390px).
3. Run `python3 -m unittest test_app.py`.
4. `git add -A && git commit -m "..." && git push` (this updates the live site).
   Push risky changes to a branch first and check them on the Vercel preview link.

## Design rules
- Night palette tokens (`:root` near the end of style.css): `--paper #080b18`,
  `--ink #f2f1ff`, `--accent #70caff` (primary blue), `--pink #ff74cb`
  (highlights, active states), `--line #30314e`, `--muted #b2b5d1`, `--panel #12152c`.
- Two typefaces, loaded from Google Fonts in `templates/index.html`: Bricolage Grotesque
  (bold, `--font-display`) for headings and big poster numbers, Hanken Grotesk
  (`--font-text`) for everything else, including the "souvenue" wordmark (medium weight).
- Text sizes outside headings: lead 18 · body 16 · UI 14 · meta 12. Nothing below 12px.
- No uppercase letter-spaced "eyebrow" tags above headings. Put real metadata
  (city, source, topic) in a sentence-case `.meta-line`.
- Primary buttons use solid `--accent`. Toggle/filter buttons use `aria-pressed`,
  which makes them chips: outlined, and filled blue when selected.
- Header breakpoints: from 761–1050px the nav tabs sit on their own row under the
  brand; at 760px and below they collapse into the `.menu-toggle` dropdown.

## style.css structure (important)
style.css is several themes stacked on each other: light green, then neon,
then cream (`.souvenue-home`), then the night palette, which overrides the
earlier ones, often with `!important`. Put all new or corrected styles in the
**"SOUVENUE DESIGN SYSTEM"** section at the bottom of the file. Don't edit the
older layers in place. The long-term plan is to move them into that section
and delete the dead ones. Check pages visually before and after any change.

## Product notes
- "Demo studio" (`/studio`) is a local developer tool. It is not in the nav; open
  it by URL locally. app.js only renders it when `state.hosted` is false.
- Event data is saved Ticketmaster snapshots (`ticketmaster-events.json`, `imports/`).
