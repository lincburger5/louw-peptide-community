# Louw Nutri-Balance community forum — version 1.2 local build

A working, local-only community forum based on the [planning specification](../forum-product-design-specification.md). This is a demonstration, **not an official Louw service**. Company contacts, product and peptide names, testimonials, terms, privacy policy, moderation commitments, and health copy remain unverified. The only brand asset is the logo supplied by the user.

Version 1.2 runs on the laptop and in the installed Android companion shell. The laptop runs Flask and stores accounts, posts, images, and appearance preferences in SQLite. The Android app shows the same responsive forum and keeps no separate database; the phone needs a connection to the laptop while in use. See [handoff.md](handoff.md) for the full implementation and review status.

## Stack

Flask 3, server-rendered Jinja templates, SQLite, Pillow for safe image normalization, and small vanilla JavaScript enhancements. This keeps the forum simple to run and audit while SQLite provides relational data and transactional writes. The SQLite path is configured with `DATABASE_PATH`; routes use a central connection function in `db.py`, so a hosted database can be introduced through a new adapter and migration without changing the templates. That migration still requires implementation and testing.

## Start locally

On Windows, double-click `START-FORUM.cmd` and keep its console window open. Then visit `http://127.0.0.1:5000/`. Do not open files from `templates/` directly; Flask renders those templates into the working website.

## Android companion (local testing)

The Android source is in `android_app/`. Build version `1.1.0+2` with `flutter build apk --release`; the output is `android_app/build/app/outputs/flutter-apk/app-release.apk`. It uses a development signing key and is for local installation only. Android WebView uses the site's mobile layout and the system photo picker for profile and post images.

For the connected phone, enable USB debugging and allow this laptop. Run `START-FORUM-PHONE.cmd` instead of `START-FORUM.cmd`; it sets `adb reverse tcp:5000 tcp:5000` and starts Flask. Install with `adb install -r android_app/build/app/outputs/flutter-apk/app-release.apk`. Keep the cable and laptop server connected. If the phone disconnects, reconnect and run `adb reverse tcp:5000 tcp:5000` again. The app's **Laptop connection** setting defaults to `http://127.0.0.1:5000/` for this USB route.

Wi-Fi access is currently disabled because Windows marks this network **Public**. The forum listens only on `127.0.0.1`, and the verified phone route is USB with `adb reverse tcp:5000 tcp:5000`. Enabling Wi-Fi later requires a trusted network and a firewall rule limited to the phone's address before binding a listener to the laptop's private IP. This is plain HTTP for local testing; use HTTPS and production hosting before public or sensitive-data use. The Android app does not work while the laptop server is off.

The Android package ID is `com.local.louwforum`. Public branding, app identity, distribution signing, and store release require Louw approval.

The five-step tutorial opens once immediately after registration. Skip or Finish records completion; refresh, sign-in, and navigation do not reopen it. Members can replay it from their Profile page. The bottom navigation appears at all screen widths.

Use PowerShell in this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py init-db
python app.py seed-demo
python app.py run
```

Open `http://127.0.0.1:5000`. Signed-out visitors see the sign-in screen. `seed-demo` is optional and idempotent. Its five posts are marked **DEMO**, contain no Louw endorsement or medical outcome, and the demo account has an unusable random password. Register your own account to interact. Data lives under `instance/forum.sqlite3`; normalized uploaded photos live under `instance/uploads/`. Both are ignored by Git. To use another local directory, set `DATABASE_PATH` and `UPLOAD_DIR` before initialization. The local app creates `instance/secret.key` once and reuses it across restarts; keep this private. A `SECRET_KEY` environment variable overrides it and must remain stable if used.

SQLite uses foreign keys, a five-second busy timeout, WAL journaling, and schema version 4. Version 2 adds the new-member checklist, version 3 stores appearance preferences, and version 4 adds persistent rate limits and session invalidation for password changes. Run `python app.py check-db` to verify integrity. Run `python app.py backup-db` to create a consistent database and upload archive under `instance/backups/`; store copies securely. Database access is centralized in `db.py`, but migration to a hosted database remains future work.

## Moderator setup for local review

There is no public role elevation route. After registering a test account, stop the app and run this in the project folder, replacing `your_username`:

```powershell
python -c "from app import app; from db import connect; db=connect(app.config['DATABASE_PATH']); db.execute('UPDATE users SET role=? WHERE username=?', ('moderator','your_username')); db.commit(); db.close()"
```

Restart the app and use **Profile → Moderation**. This command is for local setup only. A production role assignment workflow needs separate authorization and audit review.

## What works

- Username/password registration and sign-in, scrypt password hashes, password change with sign-out on other devices, signed HttpOnly sessions, sign-out, server validation, CSRF checks, persistent local rate limits, trusted Host checks, and object-level permissions.
- Optional **Keep me signed in on this device for 30 days** at registration or login. Without it, the sign-in cookie is browser-session-only. Sign-out ends either session.
- One-step bio and profile-photo saving, with a photo preview, format/size checks, random filenames, JPEG normalization, metadata stripping, and a default letter avatar. Saving only a bio retains the current photo.
- Responsive home, search, compact visual general topics and collapsible proposed-name groups, New/Top/Following feeds, pagination, post detail and profile pages. Named topics are discussion labels from the user-supplied list, not verified offerings.
- Story/question/progress posts with approved general tags, 3–120 character titles, a 1,000-word body limit, up to eight photos, explicit Before/After/Other labels, captions, consent prompt, author edit/delete, and inline validation that keeps the latest edits.
- Comments with one reply level; votes can be added, changed, or removed on posts and comments. Saved posts, topic follows, member follows, follower/following lists, and a following feed for both members and topics work.
- Reports, moderator queue, hide/restore/resolve actions, and action log.
- Five-step guided spotlight tutorial opens once after registration and can be replayed from Profile. A dismissible new-member checklist tracks topic follows, saved posts, and bio or photo completion.
- Five-button bottom navigation on laptop, tablet, and phone; centered Home and Topics layouts; per-account light/dark mode, font, text size, spacing, and animation preferences.
- A configurable, conservative identity-slur filter blocks matching published posts and comments while allowing ordinary swearing. The list and public rule wording require Louw approval.
- No pinned welcome card in the feed; welcome guidance appears in the tutorial after a new account is created.
- Private text drafts, a text preview, and in-app notifications for replies and moderation decisions.

## Current limitations and approval gates

This is **not ready for public launch**. Louw needs to approve its legal/trading name, logo use, contacts, service area, support route, age eligibility, policy text, community rules, photo/testimonial consent, retention/deletion process, moderators, official announcement publishers, and whether the proposed named discussion topics may appear publicly. The named topics do not present prices, availability, or product claims. Placeholder policy pages explicitly say they are pending approval. The local app is bound to loopback and uses SQLite-backed rate limiting; public deployment would also need HTTPS hosting, secure backups, email verification/reset, abuse monitoring, notification decisions, data export/deletion flows, media removal workflow, and a hosted database adapter. No site can be guaranteed impossible to hack.

Drafts are text-only until publication and the preview does not render uploaded images. Post edits keep existing images; individual image replacement/removal is a pending workflow. Moderation review acts on reports; the slur filter is a narrow publication check and does not replace human review. Do not use the local prototype to collect real health or sensitive personal data.

## Verify

```powershell
python -m unittest discover -s tests -v
```

The tests cover registration, login, tutorial completion, profile image upload, progress photos, vote changes, comments, search, reports, moderation, CSRF, and upload validation. See [AGENTS.md](AGENTS.md) for conventions and security requirements.
