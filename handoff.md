# Louw forum handoff — local build 1.2

## Purpose and status

This project is a local demonstration community forum using the logo supplied by the user. Members can discuss proposed peptide names, ask general questions, share personal stories and optional labeled progress photos, follow people and topics, save posts, vote, comment, and report content. The proposed names came from the user's list; their appearance **does not verify that Louw sells them**. Demo posts are fictional interface examples, explicitly marked as demonstration content. No medical outcome, endorsement, contact detail, price, or company policy is asserted by the app.

The laptop is the single server and SQLite data store. The installed Android app is a Flutter WebView shell for that server, not a second copy of the data. This is a local review build and is **not approved for public launch or sensitive health data**. The source specification and research notes are in the parent `outputs/` directory; `README.md` gives quick setup steps and `AGENTS.md` gives maintenance conventions.

## What is implemented

- **Navigation and accounts:** sign-in first; username/password registration; optional 30-day remembered session; five-button bottom navigation at all widths; profile, followers/following, saved posts, drafts, notifications, and account appearance settings. The five-step tutorial opens once after registration, with manual replay on Profile.
- **Community:** Home New/Top/Following filters, search, pagination, topic pages, topic follows, post creation/edit/deletion, text drafts, up to eight consented and captioned images, comments, post and comment votes, saves, reports, and moderator hide/restore/resolve actions with an action log.
- **Topics redesign in 1.2:** short visual community tiles and compact collapsible A–G/H–P/Q–Z groups, with instant name search. The disclaimer appears once above the proposed-name list. Mobile uses two tiles per row and single-column name rows. Keyboard focus, text-size and dark-mode settings remain supported.
- **Demo content in 1.2:** five marked sample posts about discussing peptide sources, reading a study, responsibly labeling progress photos, writing personal stories, and finding Retatrutide sources. They contain no claimed treatment outcomes or Louw endorsements. `python app.py seed-demo` updates older demo posts and is idempotent.
- **Security in 1.2:** scrypt password hashes; Change password in Settings, which invalidates other signed-in sessions; 12–128 character password validation; SQLite-backed login, registration, password-change and posting limits; trusted Host allowlist; same-origin redirect checks; CSRF on mutations; HttpOnly/SameSite signed cookies; server-side permission checks; parameterized user-supplied SQL; escaped templates; restricted and normalized image uploads; private old avatars and unpublished post media; restrictive response headers and no-store for HTML/media. The new schema version is 4.
- **Performance and polish in 1.2:** feed tags and cover images are fetched in batches instead of per post; saved/vote state is selected with the feed; index additions help tag and save lookups; page number is clamped. Static asset URLs include the app version, so the Android WebView receives the new design on reload. Feed filtering and delete confirmation have JavaScript enhancement plus HTML form fallback.

No application is guaranteed impossible to compromise. The controls above reduce common risks for this local build; they do not make an HTTP, laptop-hosted prototype suitable for public use.

## Main files and data

| Path | Responsibility |
| --- | --- |
| `app.py` | Flask routes, validation, auth, sessions, security headers, posts, moderation, and feed queries |
| `db.py` | SQLite schema/migrations, demo seed, integrity check, and database plus uploads backup |
| `templates/` | Jinja pages, including the responsive Topics directory and Settings |
| `static/css/app.css`, `static/js/app.js` | Responsive appearance, tutorial, upload previews, inline actions, and topic search |
| `static/brand/logo.jpeg` | User-supplied logo |
| `android_app/` | Installed Android shell; its current native version is 1.1.0, while the served website is 1.2 |
| `tests/test_journeys.py` | Temporary-database integration tests |
| `instance/forum.sqlite3`, `instance/uploads/` | Live accounts, posts, settings, and images; **private local data** |
| `instance/secret.key` | Local session signing secret; **never publish or rotate casually** |

Configuration: `DATABASE_PATH` and `UPLOAD_DIR` can move state; `SECRET_KEY` overrides the saved local secret; `FORUM_HOST` and `PORT` control the listener; `FORUM_TRUSTED_HOSTS` accepts comma-separated hostnames; `COOKIE_SECURE=1` is for an HTTPS deployment. The default listener and trusted hosts are loopback only. A hosted database needs a new adapter, migration, deployment and backup design.

## Run, update, and recover

1. From this folder, install `requirements.txt` with Python 3.11+, then run `python app.py init-db`, optionally `python app.py seed-demo`, and `python app.py run`. Windows launchers are `START-FORUM.cmd` and `START-FORUM-PHONE.cmd`. Open [the local forum](http://127.0.0.1:5000/); do not open files from `templates/` directly.
2. The installed phone app uses `http://127.0.0.1:5000/` over `adb reverse tcp:5000 tcp:5000`. Keep the laptop server and USB debugging connection active; relaunch the phone app to refresh the site. Android has no separate forum database.
3. Before another upgrade, run `python app.py backup-db`, save the source, and verify `python app.py check-db`. The 1.2 update was preceded by `instance/backups/forum-20261023-135607.zip` and `instance/backups/source-before-1.2.zip`. These archives contain private data or source and must be protected.
4. To recover the prior build, stop the server, restore source from `source-before-1.2.zip`, and restore the database and uploads from the matching forum archive. A version-4 database should not be handed to the older version-3 app without restoring its version-3 backup. Restart only after both source and data agree.

## Verification performed

- `python -m unittest discover -s tests -q`: **16 tests passed** in the preview and again in the live source after migration. Journeys include registration, login, tutorial, profile upload, post photos, validation, voting, commenting, search, reporting, moderation, settings, password change, hostile Host, SQL input, redirect handling, and rate-limit persistence.
- `node --check static/js/app.js` and Python compilation passed. Preview and live database integrity checks returned `ok`.
- The preview server on port 5001 and live server on port 5000 returned HTTP 200 for sign-in and the updated assets. The live listener is `127.0.0.1:5000`.
- The connected Android device reported the forum package installed and `adb reverse tcp:5000 tcp:5000` active. After the app was relaunched, the laptop log showed the phone fetching `/`, the versioned 1.2 CSS/JS, the logo, and an avatar successfully. No native Android code changed in 1.2. The phone screen was locked during screenshot capture, so an interactive phone visual review remains recommended before calling the experience final.

## Before public launch

Louw must approve its official identity, logo use, support email and phone, service area, approved peptide/product names, legal/privacy/terms text, community rules and moderation contacts, photo/testimonial consent and removal processes, age eligibility, and who may publish official announcements. Placeholder pages must be replaced. Medical, product, pricing, safety, and outcome claims need reliable substantiation and legal review.

Engineering still needed for a public service: HTTPS and an appropriate hosted server, production session/cookie configuration, production signing secrets, email verification and password reset, durable off-device backups, abuse monitoring, account/data export and deletion, a complete image removal flow, and a hosted database migration. The default slur list is a narrow moderation aid that Louw needs to review; human moderation remains necessary. The current network is treated as Public by Windows, so the laptop listener remains loopback-only; phone access is through USB rather than Wi-Fi.
