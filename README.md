# Louw Nutri-Balance community forum — local SQLite build

A working, local-only community forum based on the [planning specification](../forum-product-design-specification.md). This is a demonstration, **not an official Louw service**. Company contacts, product and peptide names, testimonials, terms, privacy policy, moderation commitments, and health copy remain unverified. The only brand asset is the logo supplied by the user.

The laptop runs Flask and stores accounts, posts, and images locally in SQLite and `instance/uploads/`. The installed Android companion shell shows the same website and needs a connection to the laptop while in use. On 2026-10-23 the hosted data was copied back into SQLite and the Supabase connection file was removed. See [HANDOFF.md](HANDOFF.md) for details.

## Stack

Flask 3, server-rendered Jinja templates, SQLite, Pillow for image normalization, and small vanilla JavaScript enhancements. `DATABASE_URL` is unset for the active local build. Uploaded JPEGs are stored in the private `instance/uploads/` folder and served through authorized Flask routes.

## Start locally

On Windows, double-click `START-FORUM.cmd` and keep its console window open. Then visit `http://127.0.0.1:5000/`. Do not open files from `templates/` directly; Flask renders those templates into the working website.

## Android companion (local testing)

The Android source is in `android_app/`. Build version `1.1.0+2` with `flutter build apk --release`; the output is `android_app/build/app/outputs/flutter-apk/app-release.apk`. It uses a development signing key and is for local installation only. Android WebView uses the site's mobile layout and the system photo picker for profile and post images.

For the connected phone, enable USB debugging and allow this laptop. Run `START-FORUM-PHONE.cmd` instead of `START-FORUM.cmd`; it sets `adb reverse tcp:5000 tcp:5000` and starts Flask. Install with `adb install -r android_app/build/app/outputs/flutter-apk/app-release.apk`. Keep the cable and laptop server connected. If the phone disconnects, reconnect and run `adb reverse tcp:5000 tcp:5000` again. The app's **Laptop connection** setting defaults to `http://127.0.0.1:5000/` for this USB route.

For phone use without USB on the current Wi-Fi, the laptop is `192.168.68.112` and the phone is `192.168.68.106`. A Windows Public-profile inbound rule named **Louw Forum Phone WiFi** permits port 5000 only from that phone IP to that laptop IP. Run `START-FORUM-WIFI.ps1` to start the Wi-Fi listener; it checks the rule and addresses first. In the Android app's **Laptop connection** setting, save `http://192.168.68.112:5000/`. The cable can then be unplugged. If either device's Wi-Fi IP changes, update the rule and app address before reconnecting. This is plain HTTP for local testing; use HTTPS and production hosting before public or sensitive-data use. The Android app does not work while the laptop server is off.

The Android package ID is `com.local.louwforum`. Public branding, app identity, distribution signing, and store release require Louw approval.

The five-step tutorial opens once immediately after registration. Skip or Finish records completion; refresh, sign-in, and navigation do not reopen it. Members can replay it from their Profile page. The bottom navigation appears at all screen widths.

Use PowerShell in this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py init-db
python app.py check-db
python app.py run
```

No `.env` is needed for the local database. Open `http://127.0.0.1:5000`. Signed-out visitors see the sign-in screen. `seed-demo` is optional and idempotent; its posts are marked **DEMO**. The local app creates `instance/secret.key` once and reuses it across restarts; keep this private. A `SECRET_KEY` environment variable overrides it and must remain stable if used.

Run `python app.py check-db` for SQLite integrity and `python app.py backup-db` for a database and image archive. The return from Supabase was prepared and checked before replacing the active SQLite file. The prior local copy and a ZIP backup remain in ignored `instance/`; protect them because they contain member data. The historical migration scripts in `supabase/` are not part of the active runtime.

## Moderator setup for local review

There is no public role elevation route. After registering a test account, stop the app and run this in the project folder, replacing `your_username`:

```powershell
python -c "from app import app; from db import connect_app; db=connect_app(app.config['DATABASE_PATH'],app.config['DATABASE_URL']); db.execute('UPDATE users SET role=? WHERE username=?', ('moderator','your_username')); db.close()"
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

This is **not ready for public launch**. Louw needs to approve its legal/trading name, logo use, contacts, service area, support route, age eligibility, policy text, community rules, photo/testimonial consent, retention/deletion process, moderators, official announcement publishers, and whether the proposed named discussion topics may appear publicly. The named topics do not present prices, availability, or product claims. Placeholder policy pages explicitly say they are pending approval. The laptop server still uses local HTTP and loopback/USB access; public deployment also needs HTTPS hosting, verified hosted backups, email verification/reset, abuse monitoring, data export/deletion flows, and a media removal workflow. No site can be guaranteed impossible to hack.

Drafts are text-only until publication and the preview does not render uploaded images. Post edits keep existing images; individual image replacement/removal is a pending workflow. Moderation review acts on reports; the slur filter is a narrow publication check and does not replace human review. Do not use the local prototype to collect real health or sensitive personal data.

## Verify

```powershell
python -m unittest discover -s tests -v
```

The tests cover registration, login, tutorial completion, profile image upload, progress photos, vote changes, comments, search, reports, moderation, CSRF, and upload validation. See [AGENTS.md](AGENTS.md) for conventions and security requirements.
