import os
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL, bio TEXT NOT NULL DEFAULT '', avatar TEXT,
 role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('member','moderator','admin')),
 tutorial_done INTEGER NOT NULL DEFAULT 0, session_version INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_onboarding (
 user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 dismissed_at TEXT
);
CREATE TABLE IF NOT EXISTS user_appearance (
 user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 theme TEXT NOT NULL DEFAULT 'light' CHECK(theme IN ('light','dark')),
 font TEXT NOT NULL DEFAULT 'system' CHECK(font IN ('system','readable','serif')),
 text_size TEXT NOT NULL DEFAULT 'normal' CHECK(text_size IN ('small','normal','large','extra')),
 density TEXT NOT NULL DEFAULT 'comfortable' CHECK(density IN ('comfortable','compact')),
 motion TEXT NOT NULL DEFAULT 'system' CHECK(motion IN ('system','reduced'))
);
CREATE TABLE IF NOT EXISTS tags (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, slug TEXT NOT NULL UNIQUE,
 description TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 1,
 kind TEXT NOT NULL DEFAULT 'general'
);
CREATE TABLE IF NOT EXISTS posts (
 id INTEGER PRIMARY KEY, author_id INTEGER NOT NULL REFERENCES users(id),
 type TEXT NOT NULL CHECK(type IN ('story','question','progress')),
 title TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'published'
 CHECK(status IN ('draft','published','hidden','deleted')),
 is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS post_tags (
 post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
 tag_id INTEGER NOT NULL REFERENCES tags(id), PRIMARY KEY(post_id,tag_id)
);
CREATE TABLE IF NOT EXISTS media (
 id INTEGER PRIMARY KEY, post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
 user_id INTEGER NOT NULL REFERENCES users(id), filename TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('avatar','post')),
 label TEXT CHECK(label IN ('Before','After','Other')),
 caption TEXT NOT NULL DEFAULT '', consent INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS comments (
 id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL REFERENCES posts(id),
 author_id INTEGER NOT NULL REFERENCES users(id), parent_id INTEGER REFERENCES comments(id),
 body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'published'
 CHECK(status IN ('published','hidden','deleted')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS votes (
 user_id INTEGER NOT NULL REFERENCES users(id), target_type TEXT NOT NULL CHECK(target_type IN ('post','comment')),
 target_id INTEGER NOT NULL, value INTEGER NOT NULL CHECK(value IN (-1,1)),
 PRIMARY KEY(user_id,target_type,target_id)
);
CREATE TABLE IF NOT EXISTS reports (
 id INTEGER PRIMARY KEY, reporter_id INTEGER NOT NULL REFERENCES users(id),
 target_type TEXT NOT NULL CHECK(target_type IN ('post','comment')),
 target_id INTEGER NOT NULL, reason TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS moderation_actions (
 id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL REFERENCES users(id),
 target_type TEXT NOT NULL, target_id INTEGER NOT NULL,
 action TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS follows (
 user_id INTEGER NOT NULL REFERENCES users(id), tag_id INTEGER NOT NULL REFERENCES tags(id),
 PRIMARY KEY(user_id,tag_id)
);
CREATE TABLE IF NOT EXISTS user_follows (
 follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 following_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK(follower_id != following_id), PRIMARY KEY(follower_id,following_id)
);
CREATE TABLE IF NOT EXISTS saves (
 user_id INTEGER NOT NULL REFERENCES users(id), post_id INTEGER NOT NULL REFERENCES posts(id),
 PRIMARY KEY(user_id,post_id)
);
CREATE TABLE IF NOT EXISTS notifications (
 id INTEGER PRIMARY KEY, recipient_id INTEGER NOT NULL REFERENCES users(id),
 kind TEXT NOT NULL, message TEXT NOT NULL, url TEXT NOT NULL,
 read_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rate_limits (
 key TEXT PRIMARY KEY, window_started INTEGER NOT NULL, hits INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_feed ON posts(status,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id,created_at);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_follows_following ON user_follows(following_id);
CREATE INDEX IF NOT EXISTS idx_post_tags_tag ON post_tags(tag_id,post_id);
CREATE INDEX IF NOT EXISTS idx_saves_user ON saves(user_id,post_id);
"""

GENERAL_TAGS = [
    ('Stories','stories','Personal experiences shared by members.'),
    ('Questions','questions','General questions for community discussion.'),
    ('Progress','progress','Personal progress updates; images do not prove treatment results.'),
    ('Wellness','wellness','General wellness conversations.'),
    ('Peptide Questions','peptide-questions','General questions about peptide research and terminology; no dosing advice.'),
    ('Research & Safety','research-safety','Discuss sources, uncertainty, and safety questions without personal medical advice.'),
    ('Announcements','announcements','Reserved for future approved company announcements.'),
]

# Names supplied by the user as proposed discussion subjects, not verified Louw offerings.
PROPOSED_NAMES = [
    'Tesamorelin','BPC-157 + TB-500','Tirzepatide','GHK-Cu',
    'CJC-1295 + Ipamorelin','NAD+','Epithalon','Semaglutide','MOTS-C',
    'AOD-9604','Semax','Selank','BPC-157','HCG','Retatrutide',
    'Melanotan II','CagriSema','TB-500','IGF-1 LR3','Gonadorelin','Ipamorelin',
]

def tag_slug(name):
    import re
    return re.sub(r'[^a-z0-9]+','-',name.lower()).strip('-')

def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=5000')
    return db

def init_db(path):
    with closing(connect(path)) as db:
        version=db.execute('PRAGMA user_version').fetchone()[0]
        if version>4: raise RuntimeError('This database was created by a newer forum version.')
        with db:
            db.executescript(SCHEMA)
            columns={row['name'] for row in db.execute('PRAGMA table_info(tags)')}
            if 'kind' not in columns: db.execute("ALTER TABLE tags ADD COLUMN kind TEXT NOT NULL DEFAULT 'general'")
            user_columns={row['name'] for row in db.execute('PRAGMA table_info(users)')}
            if 'session_version' not in user_columns:
                db.execute('ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0')
            db.executemany("INSERT OR IGNORE INTO tags(name,slug,description,kind) VALUES(?,?,?,'general')", GENERAL_TAGS)
            db.executemany("INSERT OR IGNORE INTO tags(name,slug,description,kind) VALUES(?,?,?,'proposed')",
                [(name,tag_slug(name),f'Community discussion of {name}. Not a verified Louw product or medical guidance.') for name in PROPOSED_NAMES])
            db.execute('PRAGMA user_version=4')
        db.execute('PRAGMA journal_mode=WAL')

def check_db(path):
    with closing(connect(path)) as db:
        result=db.execute('PRAGMA integrity_check').fetchone()[0]
        if result!='ok': raise RuntimeError('Database integrity check failed: '+result)
        return result

def backup_data(path,uploads_dir,destination):
    """Create a consistent SQLite snapshot with its referenced local image files."""
    path=Path(path); uploads_dir=Path(uploads_dir); destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    check_db(path)
    with tempfile.TemporaryDirectory() as temp:
        snapshot=Path(temp)/'forum.sqlite3'
        with closing(connect(path)) as source, closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
        try:
            with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot,'forum.sqlite3')
                for image in uploads_dir.glob('*.jpg'):
                    archive.write(image,'uploads/'+image.name)
            with zipfile.ZipFile(destination) as archive:
                if archive.testzip() is not None: raise RuntimeError('Backup verification failed.')
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    return destination

def seed_demo(path):
    from werkzeug.security import generate_password_hash
    with closing(connect(path)) as db:
        with db:
            db.execute('INSERT OR IGNORE INTO users(username,password_hash,bio) VALUES(?,?,?)',
                       ('demo_member',generate_password_hash(os.urandom(24).hex()),'Demonstration account; no Louw affiliation.'))
            uid = db.execute('SELECT id FROM users WHERE username=?',('demo_member',)).fetchone()['id']
            examples = [
                ('Welcome to peptide discussions','story','Start here: good questions, clear sources','DEMONSTRATION POST: Ask general questions, share your own experience, and name sources when discussing research. Proposed peptide-name topics do not confirm Louw products. Please leave out dosing instructions and private medical details.','Peptide Questions'),
                ('How do you evaluate peptide research?','question','How do you read a peptide study?','DEMONSTRATION POST: Which details do you check beyond the headline: study size, design, limits, or conflicts of interest? Share how you evaluate a source without treating a forum reply as medical advice.','Research & Safety'),
                ('Progress photos and peptide conversations','progress','Sharing a progress gallery responsibly','DEMONSTRATION POST: A gallery can include clear Before and After labels, dates, and captions. Everyone identifiable should consent. Photos describe a personal experience and do not establish what caused a change.','Progress'),
                ('What belongs in a Stories post?','story','What belongs in a Stories post?','DEMONSTRATION POST: Describe your experience in your own words and add context you are comfortable sharing. Avoid private records and claims about what others will experience. Personal stories are not medical evidence.','Stories'),
                ('Retatrutide: finding reliable sources','question','Retatrutide: finding reliable sources','DEMONSTRATION POST: This name appears on the proposed discussion list. Which public sources explain the research stage and unanswered questions? Its presence here does not mean Louw offers it.','Retatrutide'),
            ]
            for old_title,typ,title,body,tag in examples:
                existing=db.execute('SELECT id FROM posts WHERE author_id=? AND is_demo=1 AND title IN (?,?)',(uid,old_title,title)).fetchone()
                if existing:
                    pid=existing['id']
                    db.execute('UPDATE posts SET type=?,title=?,body=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(typ,title,body,pid))
                    db.execute('DELETE FROM post_tags WHERE post_id=?',(pid,))
                else:
                    cur=db.execute('INSERT INTO posts(author_id,type,title,body,is_demo) VALUES(?,?,?,?,1)',(uid,typ,title,body))
                    pid=cur.lastrowid
                tid=db.execute('SELECT id FROM tags WHERE name=?',(tag,)).fetchone()['id']
                db.execute('INSERT OR IGNORE INTO post_tags(post_id,tag_id) VALUES(?,?)',(pid,tid))
