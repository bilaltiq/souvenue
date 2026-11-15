# Encore — local concert community prototype

## Artist pages and sourced tour dates

The home page now opens artist pages before individual shows. Olivia Rodrigo’s artist page lists upcoming dates, venues, cities, and venue-local times from Ticketmaster’s public artist listings, imported October 30, 2026. Search by city or venue and filter tour dates versus other appearances. Every show opens its own public discussions, Photos (including Merch stand), and separately gated attendee chat. Source links open Ticketmaster or the partner site supplied by Ticketmaster. No purchases are made inside Encore.

The import read all four source pages: 79 listings normalized to 70 distinct concert records after excluding premium/service packages and duplicate concert listings. As of October 30, 2026, 69 are upcoming (68 tour dates and one other appearance) in 20 cities. Upcoming includes today’s dates. Past dates are hidden as the server’s America/New_York calendar date advances. Dates and times shown for each concert use that venue’s time zone. The imported snapshot is not a guarantee of current availability or future schedule completeness. Original source listings remain the authority.

The original Boston placeholder is separate under “Development-only test event,” preserving existing test check-ins and posts. Noah Kahan now has imported tour dates; his original Citi Field placeholder stays separate under Development-only test event. Imported records are read-only in the demo editor.

To refresh intentionally, run `python3 import_ticketmaster.py` in this folder while online, then restart the local server. This reads public HTML and requires no credentials. It replaces ticketmaster-events.json only when pagination and source counts validate. Page-format changes or blocked access may require importer maintenance. It is not an official API integration or background sync. Restarting upserts by source ID, preserves check-ins, and marks removed source records unlisted without deleting their concert history. Existing local records are never merged with the Boston demo placeholder.


## Open the app

1. Open the `encore` folder and double-click **START.command**. Keep the terminal window open.
2. Visit **http://127.0.0.1:4173** in a browser on this Mac.
3. Choose an artist, then a date to browse a show. For the original test shows, choose **Demo studio**, then **Simulate tap**.
4. Your tap automatically records attendance and unlocks the matching chat. If signed out, create a demo account with a display name and a new password of at least eight characters. The app keeps the event destination and completes the check-in after sign-in.

If macOS does not run the launcher, open Terminal, type `python3 `, drag `server.py` into the window, and press Return. Python 3.12 or newer is recommended. The launcher also supports the bundled Codex Python runtime on this Mac. No package installation or paid service is needed.

Stop the app with Control-C in its terminal. Reopening it keeps your data. If port 4173 is busy, stop the older copy first.

## Try these journeys

- Browse either event while signed out: show-night and city discussions remain public. Posting requires an account, but never requires attendance.
- Enter Noah's tap link, create an account, and attendance records automatically. Check My nights: one event and one badge appear.
- Open the same link again: history still contains one check-in.
- Open Olivia's event: its attendee chat remains locked until you check into that event separately.
- Post a public message and optionally a JPEG, PNG, or WebP photo up to 25 MB. Check-in badges appear on that event's posts and photos; messages are not automatically pinned. The photo tab displays public show-night photo posts.
- Open Photos → Merch stand to view or contribute photos of the merch stand. Choose the Merch stand photo category and upload a photo with a caption. These also appear under All photos and in public show-night discussion; there is no product catalog or checkout.
- Use Demo studio to edit artist, venue, city, display date, poster style or upload event artwork. Every signed-in local demo account can edit events. Event IDs and NFC links stay stable after edits. Changing city moves an event to that city's forum; existing city forum posts remain with their original city.
- Create another local account to try independent check-ins. Accounts share this server's database, not browser-local storage.

## Test data

Noah Kahan / Citi Field / July 18 and Olivia Rodrigo / Boston / October 18 are editable references supplied for testing. Venue/date/year have not been verified. Olivia's specific venue is left unknown. All screens mark the events as unconfirmed test data. Artwork is abstract or founder-uploaded, not an official artist image.

## NFC links and physical tags

- Noah: `http://127.0.0.1:4173/tap/noah-kahan`
- Olivia: `http://127.0.0.1:4173/tap/olivia-rodrigo`

These local links work only on this Mac. A phone's localhost refers to the phone itself. Do not write these localhost links to physical tags.

For a later approved hosted test, replace the origin with the phone-accessible HTTPS address, keep each event's `/tap/...` path, then copy the matching URL from Demo studio. In an NFC writing app, choose a URL/link record, paste the full URL, and write it to a basic writable NFC tag. Put the tag inside a labeled station and test it on a phone. No custom electronics are needed. No hardware has been purchased and this app has not been deployed.

A basic tag stores a copyable URL. Anyone with the link can record demo attendance from anywhere. A demo badge identifies an account's check-in; it does not prove physical presence or that any claim/photo is true. Opening a tap link automatically records attendance after sign-in and shows a slower, 4.5-second lock-opening animation; no attendance approval is needed.

## Storage and security boundaries

The Python standard-library server uses SQLite (`demo.sqlite3` beside server.py). Accounts use salted scrypt password hashes; opaque sessions are stored server-side in HttpOnly, SameSite=Strict cookies. Check-ins have a database uniqueness constraint. Attendee-chat reads and writes check the signed-in account's membership in that exact event on the server. Photos and edits persist in SQLite.

This is a local development prototype, bound only to 127.0.0.1. It is not ready for public or production use. There is no managed identity, password recovery, administrator permission model, moderation/reporting workflow, account deletion interface, rate limiting, email verification, production backup system, or real attendance verification. All local accounts can edit events. SQLite and photo data are not encrypted at rest. Local HTTP sessions lack a Secure cookie flag; HTTPS and Secure cookies are necessary for hosting. Anyone with access to the database or computer can inspect data. Use fictional names, disposable passwords, and non-sensitive photos.

No Ticketmaster integration, redeemable rewards, gift cards, purchases, or secure NFC provisioning are included. No venue partnership or official artist affiliation is implied.

## Checks

Run `python3 test_app.py` from this folder. It also checks imported event isolation, repeat import stability, imported-event editing protection, package exclusion, and duplicate removal. The test uses a separate temporary database and checks public access, registration/login/logout, password rejection, per-event chat access, check-in deduplication, badge attribution, photo posting, unknown-event rejection, and event editing. JavaScript syntax was checked with Node. A browser walkthrough confirmed tap → sign-in → saved attendance → unlocked matching chat. The home screen was checked at 390-pixel phone width with no horizontal overflow. The saved screenshot shows the successful test check-in.

The app uses responsive HTML/CSS/JavaScript and Python's standard library. Google Fonts is optional; system fonts provide an offline fallback.

Artist search on the home page filters available artists by name, including partial and case-insensitive matches. It searches the six artists currently imported in Encore, not Ticketmaster’s full catalog. Unlocked attendee-chat tabs have a glowing star and an Unlocked label; their conversation panel gets a highlighted welcome area. Reduced-motion preferences disable decorative animations.

## Show-night topic tags

Public Show night discussions and each separate attendee chat have All posts plus Merch, BST, Box Office, Questions, Outfits, Views, and Stories filter blocks. Select one topic to see posts carrying that tag; choose All posts to return to the whole feed, including older untagged posts. A post can have multiple tags and remains a single record in that discussion. Tag selection is optional. Filters preserve a draft and attached photo when switching topics. Existing merch-stand photos get the Merch tag automatically; a text-only Merch-tagged post does not need a photo. Each event and the public/attendee feeds retain their existing independent access rules.

## Expanded artist catalog — October 30, 2026

Ticketmaster public snapshots now cover Olivia Rodrigo (69 upcoming shows), Noah Kahan (43), sombr (52), Phoebe Bridgers (14), Gracie Abrams (64), and Charli XCX (7). Counts include today and sourced festival/other appearances, after filtering add-ons and duplicate listings; they describe this snapshot, not a guarantee of every announced date. All six artists are searchable and have dedicated pages with date, venue, city, venue-local time, source links, and per-show communities. Every artist has its own correct Ticketmaster artist source link and tour label. No screens or screen recordings were used to validate this update.

Additional artist snapshots live in imports/. Refresh one artist with `python3 import_ticketmaster.py --artist noah-kahan` (or sombr, phoebe-bridgers, gracie-abrams, charli-xcx, olivia-rodrigo). Use `python3 import_ticketmaster.py --all` to refresh all six. Restart the server afterward. Existing Olivia show URLs and original test-event URLs are preserved. Importing one artist no longer unlists another artist’s events. For shared festival listings, artists have independent Encore communities keyed by artist plus source event ID. Imports do not change existing posts, attendance, accounts, or sessions.

## Personal photo feeds

Photo feed in the navigation opens public personal photo posts from everyone using this local server. Choose New photo post, select a JPEG/PNG/WebP photo up to 25 MB, add an optional caption, and optionally tag one show. Search the event picker by artist, venue, city, or date. Post to my feed saves the post under the signed-in account. My profile now includes a personal photo feed plus the existing concert history. Clicking an author opens their public photo profile. Public profiles reveal display name and photo posts, not their private account credentials or concert history.

A tagged post remains one personal-feed record. It also appears in the tagged event’s Photos and links back to that event. It is not duplicated into a chat thread. Chats continue as independent message streams. A Merch stand category lets tagged personal photos appear in the show’s Merch stand photo subgroup. Tagging a show never creates attendance or grants access to attendee chat. Event-specific attendance badges on personal photos come from server-side attendance records, not from the photo tag. Untagged photos are supported too.

Posts are public within this local prototype; there are no follower relationships, private-profile settings, likes, comments on feed posts, or multi-image carousels yet. Uploads, captions, and event tags persist in SQLite on this computer. As before, this is a local demonstration, not production hosting or verified physical attendance.

Artist tiles now use locally saved primary artist photos from the corresponding public Ticketmaster artist pages, beneath the existing blue/pink gradient overlays. Source URLs and credits are recorded in artist-photos.json, and tiles show a photo credit. Run `python3 fetch_artist_photos.py` intentionally to refresh all six images while online. The server reads the photo manifest for artist cards; event poster uploads and abstract show artwork retain their existing behavior.

## Friends and communities

Find friends searches display names among accounts on this local server. Send requests, accept or decline incoming requests, cancel outgoing ones, view your friends’ public photo profiles, and remove friends. Friendships require acceptance and are visible to the two accounts involved. No external contacts or social networks are connected, and direct messages are not included.

Communities has searchable artist and city rooms, a My communities filter, real member counts, and a create-community form. Nine starter rooms are independent empty fan groups, not invented active communities. Joining needs an account, but no event attendance. Only joined members can read or send a room’s messages; access is checked server-side on every request. Chat refreshes every five seconds and shows the latest 300 messages. Leaving removes access but retains your past messages. Communities are separate from city/show forums and event-specific attendee chats. Community titles and descriptions are public in the directory. These local group chats have no production moderation or notification system yet.

## Public and private profiles

My profile → Profile privacy lets an account choose Public or Private. Existing accounts remain Public until the owner changes this setting. Private personal photo posts are returned only to their owner and accepted friends, including through the global feed, direct profile feed, and tagged event photo feed. Pending requests do not grant access; removing a friendship revokes access on subsequent requests. Display names remain searchable for friend requests. A private profile displays a locked state to non-friends. The setting applies to existing and new personal feed posts. It does not retract content previously seen or saved by someone else.

Posts and photos sent directly to a public show/city discussion remain public; attendee and community chats keep their separate membership rules. The privacy settings explain that distinction. Profile privacy is persisted in SQLite and enforced by the server, not merely hidden in the interface.

## 50-artist catalog — November 1, 2026

The catalog now contains 50 artists, including Tame Impala, with verified Ticketmaster artist pages and locally saved tile photos. Tame Impala is featured near the top of artist discovery and is searchable. Artist-page dates are sourced snapshots, not a live or comprehensive touring database. Artists with zero upcoming listings are included with an explicit empty state and a source link; no dates were invented for them. Blue/pink photo overlays remain in place.

The 44 added artist identities and primary source URLs are in additional-artists.json. The importer and photo helper both load that catalog, so future refreshes include the expanded selection. Existing accounts, privacy choices, friend relationships, chats, personal feeds, and check-ins are retained. The original six event snapshots keep their previous import dates; the 44 additions were read November 1.

Photo uploads now allow up to 25 MB per image in personal feeds, discussion posts, and the demo event editor. The server request limit accounts for base64 encoding overhead, and server-side size checks enforce the same image limit.

## Shared venue chat

The event-page City forum tab is replaced by Venue chat. All show dates at the same confirmed venue share one public discussion, including shows by different artists. The server assigns a venue key from normalized venue name, city, region, and country, independent of artist and event date. Different venues in one city and identically named venues in different locations remain separate. Unconfirmed placeholder venues remain isolated rather than being merged into real venues. Source spelling or venue renaming can require later identity reconciliation.

Venue chat includes an expandable list of the known dates that share its conversation. Reading is public, posting needs an account, and no attendance check-in is required. Show night, personal event photos, and attendee-only chat remain event-specific. Existing city-forum posts are retained under their old scope and are not ambiguously copied to venue chats.

## Home preview and full artist directory

Home shows six complete artist tiles, then an unfocusable decorative preview fading into Explore artists. Both Explore artists buttons and the Artists navigation open /artists. That page lists all 50 artists with search at the top, a genre dropdown, and shortcut filters. Search and genre filters combine; an empty result offers Clear filters.

Genre and subgenre names are read directly from each public Ticketmaster artist page’s minorCategory and subMinorCategory fields. The source names, IDs, hierarchy levels, source URL, and retrieval date are recorded in artist-genres.json. Filters match these actual categories rather than guessed editorial genres; an artist can match multiple source categories. Run `python3 fetch_artist_genres.py` to intentionally refresh the classification snapshot while online. Artists without a classification display Genre not listed.

## Community category tiles

Community discovery starts with Artists, Venues, Tours, and General category tiles. Choosing a tile reveals its rooms; search, My communities, and Browse all communities can also reveal results. New communities choose one of the four categories. Existing Artist fans starter rooms are categorized as Artists; city and general concert rooms remain under General. Existing community IDs, memberships, and messages are preserved. Empty Venues or Tours categories offer room creation rather than invented groups or member counts.

## Threads within chats

Community rooms, public show-night discussions, venue chats, and attendee-only chats now have a Threads section with Start a thread. A thread has a title and opening post; clicking it opens a dedicated page with comments, author links, a comment count, and Refresh comments. Main chat messages remain a separate continuous stream. Threads and comments persist in SQLite and inherit the parent scope’s server-side authorization. Leaving a community revokes access to its threads; an event attendance badge does not unlock other events’ threads. Public chat threads are readable without attendance, while posting and commenting require an account. Comments are flat within each thread; nested replies and voting are not included yet.

Thread authors can delete their own threads, removing all comments in that thread. Comment authors can delete their own comments. Ownership is enforced on the server, and the interface asks for confirmation. Delete buttons appear on the thread detail page; other users cannot delete content they do not own.

## Multi-photo carousel posts

Personal-feed posts support 1–10 photos, up to 25 MB each and 100 MB total per post. Add photos in multiple selections, preview the selection, remove photos, and move them earlier or later before publishing. Carousels support horizontal swiping/scrolling, previous/next arrows, direct photo dots, arrow keys, and a photo count. They appear in profile feeds, the community photo feed, and tagged show Photos. Existing single-photo posts still display normally. Captions, event tags, and server-enforced privacy apply to the whole carousel.

Photo posts now open at /post/post-id by clicking a photo, caption, or View post. Carousel photo links preserve the chosen slide. The expanded page shows the complete caption, carousel, author, and event tag. Direct post retrieval uses the same server-side visibility rules as feeds; a copied link does not reveal a private post to a non-friend.

## Expanded communities and General topics

Starter rooms now cover all 50 catalog artists, 30 venues selected from the sourced event catalog, and 14 tour groups derived from the saved artist snapshots. General contains 22 rooms across Lounge, Meetups & concert buddies, Merch & collectibles, Buy / Sell / Trade, Box office & tickets, Questions & first-timers, Outfits & looks, Views & photo tips, Stories & memories, Travel & logistics, and City crowds. These are independent room templates, not fabricated active groups.

General has topic filters, and new General communities can choose their topic. Category, topic, search, and My communities filters combine. Results initially show 24 rooms with Show more communities for larger lists. Existing community IDs, memberships, threads, and messages are retained; starter seeding is idempotent. Venue community groups remain distinct from the public venue chats linked from individual show pages.

## Concert tracking, demo points, and leaderboards

My profile shows unique check-ins, badges, and demo points, with a link to /concerts for the full tracker and per-show point entries. Every unique attendance record counts for 100 non-redeemable demo points, including records made before this feature. Points are calculated server-side from deduplicated attendance, not a client-provided balance. Repeat taps add zero. The tap animation shows points only for a newly recorded check-in.

/leaderboards has all-time, this-month, and friends filters. Monthly scores use check-in timestamps in America/New_York, not scheduled concert dates. Equal scores share a rank. The top 100 participants are displayed with an own-rank indicator when applicable. My profile has an explicit opt-in checkbox for publishing display name, concert count, and score; existing and new accounts default to hidden. Photo/profile privacy remains independent. Friends rankings include only accepted friends who opted in. These scores are for testing, are not redeemable, and do not verify physical attendance.


Concert log and past shows
-------------------------
The profile and concert tracker combine manual concert logs with check-ins. Add a concert at /log, search the past-year archive by artist/city/venue/date, or enter any past show yourself (including older dates). Artist pages link to the artist's past-show picker. Logged entries use plain lettering; check-ins keep the neon star and exclusive access. Only attendance records contribute points or rankings. Manual logs are private to the account; they are not exposed through public profiles or the leaderboard.

The source snapshot in past-events.json covers November 2, 2025–November 2, 2026 and contains factual date/venue listings from public setlist.fm artist pages. It is separate from Ticketmaster's upcoming-date snapshots. Source links are retained. Forty-five artists have at least one in-window listing; five had no in-window listing in the retrieved histories. Some source pages were unavailable, so coverage is incomplete; the picker explicitly permits missing shows to be added manually. These are community-maintained historical records, not attendance verification. The importer saves status per artist and never imports song lists.

Repeated manual saves of the same normalized artist/venue/city/date do not create duplicates. An exact matching check-in, or a check-in for the same selected event, takes precedence in history without counting the concert twice. Removing a manual log requires its owning account and never removes a check-in.


Location and future NFC check-ins
--------------------------------
Show pages now offer an explicit “Check in with location” action. The browser asks for location permission only after this action, requests one fresh high-accuracy reading, and sends it to the local server for validation. The server uses venue coordinates retained from Ticketmaster in venue-locations.json. No GPS coordinates are stored in attendance, profiles, or posts; attendance retains only the method (gps or demo), event, account, and check-in time. Existing attendance is migrated to method demo.

Location check-in requires a finite reading no older than 60 seconds, accuracy of 100 metres or better, and distance plus reported uncertainty within 500 metres of the venue. A show with a known time opens four hours before and closes eight hours after that time, in the venue time zone. Date-only listings open from 06:00 on the show date through 06:00 the next day in the venue time zone. Missing venue coordinates/time zones/dates and cancelled/postponed shows fail closed. Current source data configures GPS for 434 of 445 imported shows; remaining shows show why location is unavailable. Refresh venue coordinates independently with import_venue_locations.py.

A successful GPS check-in uses the existing 4.5-second unlock, attendee access, points, and neon history. Repeat check-ins add no points. Manual concert logs remain independent and do not unlock attendee chats. NFC /tap links and the demo studio remain for hardware development; real NFC tag verification has not been implemented. Development simulation is shown inside Development tools. Set ENCORE_DEMO_CHECKINS=0 to disable the simulation endpoint and automatic /tap simulation before any real release. This environment switch is enforced by the server, not just the UI.

Browser geolocation requires permission and a secure context. Localhost / 127.0.0.1 can be used for laptop testing; a phone accessing a non-localhost development server generally needs HTTPS. No site has been published as part of this change. Automated tests use synthetic locations, so actual device permission and GPS behavior still need testing at a venue. Browser-supplied coordinates can be spoofed: this is proximity screening for the prototype, not tamper-proof attendance verification. A real launch also needs hosted accounts/storage and removal of prototype administration paths.
