# Louw forum project guide

## Structure

- `app.py`: Flask routes, validation, authentication, authorization, and moderation.
- `db.py`: SQLite connection, schema, seed and database initialization. Database path comes from `DATABASE_PATH`.
- `templates/`: Jinja pages and reusable layout components.
- `static/css/`, `static/js/`, `static/brand/`: presentation and approved user-supplied logo.
- `instance/`: local SQLite database and uploaded images; git-ignored and never served as a directory.
- `tests/`: integration tests using temporary databases and upload directories.
- `android_app/`: native Flutter Android shell for the local forum; Android's picker supplies image uploads. The Flask server remains the source of truth.

## Setup and run

Use Python 3.11+ and `python -m pip install -r requirements.txt`. Initialize with `python app.py init-db`, optionally `python app.py seed-demo`, and start with `python app.py run`. Local URL: `http://127.0.0.1:5000`. The app creates a private local `instance/secret.key` once; set a stable `SECRET_KEY` environment variable if overriding it. Optional `DATABASE_PATH` and `UPLOAD_DIR` environment variables move local state. The database functions isolate SQLite calls so a hosted adapter can replace them later.

Database checks: `python app.py check-db` and `python app.py backup-db`. Backups include a SQLite snapshot and uploaded JPEGs. For USB phone testing, `START-FORUM-PHONE.cmd` configures ADB reverse before starting the server. Build the Android shell with `cd android_app` and `flutter build apk --release`. The local APK is development signed; do not distribute it publicly.

## Conventions

Keep routes thin where possible. Validate all user input on the server; templates escape by default. Use parameterized SQL, named constants for limits, UTC timestamps, and authorization checks at object level. Add or update meaningful integration tests for behavior changes. Do not add unapproved business facts or health claims to seed data.

## Data and images

Use SQLite with foreign keys and indexes. Keep email and password hashes private. Store uploaded images outside `static`; serve only by media ID through an authorized Flask route. Allow JPEG, PNG, and WebP after Pillow decoding, normalize to JPEG, strip metadata, cap size, and generate random names. Never trust user filenames. Delete obsolete physical files only after database references are removed.

Keep schema upgrades versioned with `PRAGMA user_version`; version 2 adds new-member onboarding, version 3 adds account appearance preferences, and version 4 adds persistent rate limits and session invalidation. Back up the database before future migrations. Never add the live database, uploaded images, signing keys, or backup archives to source control. The live session cookie is `louw_live_session`; keep it distinct from the preview cookie.

## Moderation

Members can report posts and comments. Moderators may hide/restore posts or comments and resolve reports, with logged actions. Authors may edit/delete their own posts and comments. Proposed name tags are discussion labels drawn from the user-supplied list; they do not verify Louw products or imply health benefits. Official announcements remain unavailable until Louw explicitly approves them. User stories and progress images do not establish treatment outcomes. Do not add dosing prompts or personalized medical advice.

## Security

Use scrypt password hashes, server-side validation, signed HttpOnly/SameSite session cookies, CSRF tokens on every mutation, restricted upload decoding, SQLite-backed rate limits for authentication and posting, trusted Host validation, and security headers. Parameterize all user-supplied SQL values; interpolate only fixed internal query fragments. Require login for forum pages and mutations, and verify owner/moderator status server-side. Remembered sign-ins last 30 days only when chosen; ordinary sign-ins use browser-session cookies. Password changes must invalidate older sessions. Keep the local signing key private and use a stable secret on deployment. No production deployment with placeholder legal text or contact details. Do not expose local data files or email addresses in public pages.

## Verification

Run `python -m unittest discover -s tests -v`. Exercise a browser or test client through registration, login, profile photo upload, post with gallery, votes, comments, search, report/moderation, and tutorial persistence. Check keyboard focus, labels, mobile layout, and contrast during UI review. Recheck public launch approvals listed in `README.md` before deployment.

For Android, run `flutter analyze`, `flutter test`, and `flutter build apk --release` in `android_app/`. Confirm ADB authorization, install the APK, set `adb reverse tcp:5000 tcp:5000`, and verify login, navigation, and file selection on the physical phone.
