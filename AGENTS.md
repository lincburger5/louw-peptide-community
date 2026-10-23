# Louw forum project guide

Current deployment: local SQLite in `instance/forum.sqlite3`, uploaded JPEGs in
`instance/uploads/`, and no `DATABASE_URL` or `.env` connection file. The
Supabase migration notes below are historical; do not reconnect without a new
user decision. Back up SQLite and uploads together before changes.

## Structure

- `app.py`: Flask routes, validation, authentication, authorization, and moderation.
- `db.py`: SQLite and Postgres adapters, SQLite schema, seed and database initialization. `DATABASE_URL` selects Supabase Postgres; `DATABASE_PATH` selects local SQLite when no URL is set.
- `supabase/`: versioned private Postgres schema and one-time SQLite/data/image migration script.
- `templates/`: Jinja pages and reusable layout components.
- `static/css/`, `static/js/`, `static/brand/`: presentation and approved user-supplied logo.
- `instance/`: historical SQLite backup, local upload cache, and signing key; git-ignored and never served as a directory. Hosted image bytes are in private `forum.media_bytes`.
- `tests/`: integration tests using temporary databases and upload directories.
- `android_app/`: native Flutter Android shell for the local forum; Android's picker supplies image uploads. The Flask server remains the source of truth.

## Setup and run

Use Python 3.11+, a local `.venv`, and `python -m pip install -r requirements.txt`. The ignored `.env` holds the Supabase Session pooler `DATABASE_URL`; copy `.env.example` on another machine and fill it with that machine's private connection URI. Run `python app.py check-db`, then `python app.py run`. Local URL: `http://127.0.0.1:5000`. The app creates a private local `instance/secret.key` once; set a stable `SECRET_KEY` environment variable if overriding it. With no `DATABASE_URL`, run `python app.py init-db` for SQLite-only development.

`python app.py check-db` checks the selected database. `backup-db` only backs up historical/local SQLite plus upload cache; configure hosted Supabase backups independently. The pre-migration archive is private in `instance/backups`. For USB phone testing, `START-FORUM-PHONE.cmd` configures ADB reverse before starting the server. Build the Android shell with `cd android_app` and `flutter build apk --release`. The local APK is development signed; do not distribute it publicly.

## Conventions

Keep routes thin where possible. Validate all user input on the server; templates escape by default. Use parameterized SQL, named constants for limits, UTC timestamps, and authorization checks at object level. Add or update meaningful integration tests for behavior changes. Do not add unapproved business facts or health claims to seed data.

## Data and images

Use the private `forum` Postgres schema with indexes, foreign keys, and RLS; no `anon` or `authenticated` schema grants. SQLite remains for tests. Keep password hashes private. Store hosted JPEG bytes in `media_bytes` and a local upload cache outside `static`; serve only by media ID through an authorized Flask route. Allow JPEG, PNG, and WebP after Pillow decoding, normalize to JPEG, strip metadata, cap size, and generate random names. Never trust user filenames. Delete obsolete media only after database references are removed.

Keep Postgres schema changes in versioned `supabase/` SQL migrations; SQLite test schema still uses `PRAGMA user_version`. Back up and verify the hosted database before future migrations. Never add `.env`, the live database, uploaded images, signing keys, or backup archives to source control. The live session cookie is `louw_live_session`; keep it distinct from the preview cookie.

## Moderation

Members can report posts and comments. Moderators may hide/restore posts or comments and resolve reports, with logged actions. Authors may edit/delete their own posts and comments. Proposed name tags are discussion labels drawn from the user-supplied list; they do not verify Louw products or imply health benefits. Official announcements remain unavailable until Louw explicitly approves them. User stories and progress images do not establish treatment outcomes. Do not add dosing prompts or personalized medical advice.

## Security

Use scrypt password hashes, server-side validation, signed HttpOnly/SameSite session cookies, CSRF tokens on every mutation, restricted upload decoding, database-backed rate limits for authentication and posting, trusted Host validation, and security headers. Parameterize all user-supplied SQL values; interpolate only fixed internal query fragments. Require login for forum pages and mutations, and verify owner/moderator status server-side. Remembered sign-ins last 30 days only when chosen; ordinary sign-ins use browser-session cookies. Password changes must invalidate older sessions. Keep `.env` and the local signing key private. No production deployment with placeholder legal text or contact details. Do not expose local data files or email addresses in public pages.

## Verification

Run `python -m unittest discover -s tests -v`. Exercise a browser or test client through registration, login, profile photo upload, post with gallery, votes, comments, search, report/moderation, and tutorial persistence. Check keyboard focus, labels, mobile layout, and contrast during UI review. Recheck public launch approvals listed in `README.md` before deployment.

For Android, run `flutter analyze`, `flutter test`, and `flutter build apk --release` in `android_app/`. Confirm ADB authorization, install the APK, set `adb reverse tcp:5000 tcp:5000`, and verify login, navigation, and file selection on the physical phone.
