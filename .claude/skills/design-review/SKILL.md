---
name: design-review
description: |
  Souvenue design QA: screenshot the rendered site at desktop and phone width, measure it,
  find inconsistencies, AI-slop patterns and broken layouts, then fix them in style.css/app.js
  with before/after screenshots. Use when Sofia asks to "audit the design", "check consistency",
  "does this look good", "design polish", "visual QA", or after a big visual change. Also use
  with a page name to review just that page ("design review the event page").
---

# /design-review for Souvenue

Review the site the way a designer would, against Souvenue's own design system, then fix what
you find. Judge what is **rendered**, not what the CSS intends: style.css is several themes stacked
on each other, so the only truth is the screenshot and the computed styles.

## Ground rules from Sofia (these outrank generic design advice)

- **Nothing is pushed until Sofia has looked.** Commit locally if useful; push only when she says "push".
- She reviews at http://127.0.0.1:4173 (her server) or the copy server below. Tell her the URL to look at.
- She hates the "AI slop" look. In this project that has specifically meant:
  outlined boxes and harsh rectangles, divider rules between every block, dashed boxes,
  identical outlined pills, uppercase letter-spaced eyebrow tags, emoji or ★/＋ text glyphs used as icons,
  gradients for decoration, brown/orange/muddy colours, generic centred card grids.
- Colour: night palette with **pastel pinks, blues, purples and mint** only (gold star `#ffe7a0` is fine).
- Softness: rounded, filled surfaces (`#141834`, `#171b3a`, `#11142c`) instead of borders. Chips are
  filled; the selected chip is solid `--accent` with dark text.
- Things she has approved and that must stay consistent: the crayon artist marks (`public/marks/`,
  drawn by `scripts/crayon_marks.py`), the room-tab track and glowing checked-in stub on event pages,
  rounded filled form fields, the "Search for your fav artist." search.
- Things she rejected (don't reintroduce): artist photos, margin confetti on inner pages.

## The design system (from CLAUDE.md, verify it is what renders)

- Tokens: `--paper #080b18`, `--ink #f2f1ff`, `--accent #70caff`, `--pink #ff74cb`, `--line #30314e`,
  `--muted #b2b5d1`, `--panel #12152c`.
- Type: Bricolage Grotesque (bold) for headings and big numbers; Hanken Grotesk for everything else.
  Sizes outside headings: lead 18 · body 16 · UI 14 · meta 12. **Nothing below 12px.**
- Toggles/filters use `aria-pressed`. Primary buttons are solid `--accent`.
- Header: tabs on their own row at 761–1050px; `.menu-toggle` dropdown at ≤760px.
- `templates/index.html` and `public/index.html` must stay identical.

## Setup

1. Never point the review at Sofia's real data. Start a copy server (keep it running all review):
   ```bash
   mkdir -p /tmp/souv && cp demo.sqlite3 /tmp/souv/copy.sqlite3
   SOUVENUE_DB=/tmp/souv/copy.sqlite3 PORT=4174 python3 server.py   # run_in_background
   ```
   If 4174 is already serving, reuse it. Restart it after any `server.py` change.
2. Scope: a page Sofia names, otherwise these pages: `/`, `/artists`, `/artist/olivia-rodrigo`,
   a searched artist (`/artist/mb/bf2bf522-581e-4c93-81c2-cb5b826b02e4`), `/event/<id>` signed in and
   checked in, `/log`, `/communities`, `/leaderboards`, `/profile` (signed in), `/credits`.
   Get an event id from `curl -s http://127.0.0.1:4174/api/state` (`events[0].id`).

## Phase 1: capture and measure

```bash
python3 .claude/skills/design-review/shot.py --pages / /artists /artist/olivia-rodrigo --widths 1280,390
python3 .claude/skills/design-review/shot.py --pages /event/<id> /profile --signin --checkin
```
Full-page PNGs plus `measure.json` land in `.design-review/<date>/` (git-ignored). `--tag before`
names files for before/after pairs. Add width 900 (the tablet header) when reviewing navigation.
If Chrome will not start, kill stale ones: `pkill -f remote-debugging-port=94`.

**Read every screenshot with the Read tool** before judging; Sofia sees them only if you show them.
Then read `measure.json`. What each field catches:

| Field | Problem it points at |
|---|---|
| `outlinedBoxes` | boxes with a visible border on 3+ sides: the harsh-rectangle look |
| `dividerRules` | count of wide top/bottom rules; many = the "line between everything" look |
| `tooSmallText` | text under 12px (breaks the type rule) |
| `fonts`, `fontSizes` | anything other than Bricolage/Hanken; sizes off the 12/14/16/18 scale |
| `colors`, `backgrounds` | colours outside the palette, browns/oranges |
| `radii` | mixed corner radii for the same kind of element |
| `smallTapTargets` | under 44px, matters most at 390 |
| `uppercaseLabels` | eyebrow tags (banned) |
| `textGlyphIcons` | ★ ＋ ✓ emoji standing in for drawn icons |
| `horizontalScroll`, `widestElements` | phone overflow and which element causes it |
| `consoleErrors` | JS errors on the page |

## Phase 2: first impression (write it before analysing)

For the main page in scope: what it communicates, what stands out, the first three things the eye
goes to, and one word for it. Be direct; Sofia asked for a designer's eye, not a QA log.

## Phase 3: page-by-page audit

For each page and width, check:

1. **Slop patterns** (the list in Ground rules). These are high impact on this project.
2. **Consistency across pages**: same chip style everywhere, same field style, same button shapes,
   same heading scale, same spacing rhythm, the crayon mark used wherever an artist is pictured,
   header and footer identical.
3. **Hierarchy**: one clear focal point, one primary action, more space above headings than below.
4. **Typography**: the two faces only, the size scale, balanced headings, body measure ≤ 75ch.
5. **Colour and contrast**: palette only; body text ≥ 4.5:1; secondary text tinted, not grey on colour.
6. **Responsive**: at 390 the layout should make sense on its own (not just stacked), no sideways
   scroll, tap targets ≥ 44px, nothing cut off (check tab rows and chip rows).
7. **States**: hover, focus-visible ring, empty states, loading text ("Loading…", with a real ellipsis), errors.
8. **Motion**: purposeful, respects `prefers-reduced-motion`.
9. **Copy**: Souvenue's own voice, sentence case, controls name their action.

Rate each finding **high** (hurts the first impression or breaks on phones), **medium** (felt, not seen)
or **polish**. Grade the site A–F overall and separately for "AI slop" (A = no slop).

## Phase 4: report, then fix

Write the findings to `.design-review/<date>/report.md` (screenshots referenced by file name) and
summarise them in chat: grades, the top findings with screenshots, and **quick wins**.

Ask before fixing when a fix changes something Sofia chose or approved, removes content, or
changes copy. Otherwise fix in impact order:

1. **Where to put CSS**: append to the "SOUVENUE DESIGN SYSTEM" section at the bottom of
   `public/style.css`. Never edit the older layers in place.
2. **Specificity traps** that have bitten before:
   - `button:not([aria-pressed]):not(.menu-toggle)` paints every button solid blue with `!important`;
     beat it with `html body #app …` selectors.
   - `*, ::before, ::after { background-image: none !important }` strips gradients; re-apply with
     `background-image: … !important` on a specific selector.
   - Old pill rules set `border-radius: 999px`; tiles need an explicit radius.
   - Check the winning rule with CDP `CSS.getMatchedStylesForNode` when a fix "doesn't work".
3. Prefer CSS-only fixes. If app.js markup must change, keep the change minimal and keep behaviour.
4. After each fix: re-shoot the page with `--tag finding-N-after`, Read the before and after, confirm
   no new console errors, and that the other width still looks right.
5. One local commit per fix if Sofia wants commits: `style(design): <what changed>`. Never push.
6. Run `python3 -m unittest test_app.py` after any app.js/server.py change.
7. Stop and check in with Sofia after 5 fixes, after anything you had to revert, or if a fix
   needs a decision about the look.

## Phase 5: wrap up

Re-run Phase 1 on the affected pages, give before → after grades, list what was fixed, what was
deferred and why, and the URL Sofia should open to look. Remind her nothing is pushed.

## Optional: write DESIGN.md

If Sofia agrees, record the rendered system (tokens, type scale, chip/field/button specs, radii,
spacing, the crayon-mark rules, the banned patterns above) in `DESIGN.md` at the repo root so later
reviews and new pages have one reference.
