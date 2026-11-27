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
- One typeface for everything: Bricolage Grotesque, loaded from Google Fonts in
  `templates/index.html` (weights 400–800, optical sizing on). `--font-display` (bold) for
  headings and big poster numbers, `--font-text` for everything else. The only exception
  is the "souvenue" wordmark, which stays in Hanken Grotesk medium (only weight 500 is loaded).
- Text sizes outside headings: lead 18 · body 16 · UI 14 · meta 12. Nothing below 12px.
- No uppercase letter-spaced "eyebrow" tags above headings. Put real metadata
  (city, source, topic) in a sentence-case `.meta-line`.
- Button colours each have one job (tokens at the end of style.css): main actions are solid
  pink `--btn-pink #ff9fd6` with dark text; secondary buttons are pastel lavender
  `--soft-lilac-bg #cdb4ff` (the confetti lavender) with dark text; blue `--accent` stays for the header account
  button, text links, row actions ("Open show", "Log show") and focus rings.
- Toggle/filter buttons use `aria-pressed`, which makes them chips: filled `#1a1e3d` with no
  outline, and turquoise `--chip-mint #74e4dd` with dark text when selected (hover keeps it).
- No outlined boxes anywhere: panels, cards and fields are soft filled surfaces.
- Header breakpoints: from 761–1240px the nav tabs sit on their own row under the
  brand; at 760px and below they collapse into the `.menu-toggle` dropdown.
- The header always has a pink "Log a concert" button (`.log-cta`, links to `/log`; it reads
  "Log" on phones). At 760px and below, Sign in / Sign out moves into the menu
  (`.nav-account`, which clicks the hidden `#account`), so the phone header is logo · Log · menu.

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
