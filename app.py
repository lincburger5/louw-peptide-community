import io
import os
import re
import secrets
import sqlite3
import psycopg
import sys
import time
import unicodedata
from datetime import timedelta
from functools import wraps
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlsplit

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from PIL import Image, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import SecurityError

from db import backup_data, check_db, connect_app, init_db, seed_demo

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT/'.env')
APP_VERSION = '1.2.0-local'
MAX_UPLOAD = 10 * 1024 * 1024
ALLOWED_REASONS = {'Spam','Harassment','Privacy or consent','Medical advice or dosing','Misleading claim','Other'}
POST_WORD_LIMIT = 1000
# Conservative, configurable default. Louw must approve the public moderation rules.
DEFAULT_BLOCKED_SLURS = frozenset({'nigger', 'faggot', 'kike', 'spic'})
DEFAULT_APPEARANCE = {'theme':'light','font':'system','text_size':'normal','density':'comfortable','motion':'system'}
APPEARANCE_CHOICES = {
    'theme':{'light','dark'}, 'font':{'system','readable','serif'},
    'text_size':{'small','normal','large','extra'},
    'density':{'comfortable','compact'}, 'motion':{'system','reduced'},
}

def words(value):
    return re.findall(r"\b[\w]+(?:['’-][\w]+)*\b", value, flags=re.UNICODE)

def contains_blocked_slur(value, blocked):
    normalized = unicodedata.normalize('NFKC', value).casefold()
    return bool(set(words(normalized)) & set(blocked))

def local_secret():
    """Keep local login cookies valid across development-server restarts."""
    path=ROOT/'instance'/'secret.key'
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        try:
            with path.open('x',encoding='ascii') as target:
                target.write(secrets.token_hex(32))
        except FileExistsError:
            pass
    return path.read_text(encoding='ascii').strip()

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=(test_config or {}).get('SECRET_KEY') or os.environ.get('SECRET_KEY') or local_secret(),
        DATABASE_PATH=os.environ.get('DATABASE_PATH') or str(ROOT/'instance'/'forum.sqlite3'),
        DATABASE_URL=os.environ.get('DATABASE_URL',''),
        UPLOAD_DIR=os.environ.get('UPLOAD_DIR') or str(ROOT/'instance'/'uploads'),
        MAX_CONTENT_LENGTH=35*1024*1024,
        SESSION_COOKIE_NAME='louw_live_session',
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE')=='1',
        TRUSTED_HOSTS=[host.strip() for host in os.environ.get('FORUM_TRUSTED_HOSTS','localhost,127.0.0.1').split(',') if host.strip()],
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        BLOCKED_SLURS=DEFAULT_BLOCKED_SLURS,
    )
    if test_config: app.config.update(test_config)
    if test_config and 'DATABASE_PATH' in test_config and 'DATABASE_URL' not in test_config:
        app.config['DATABASE_URL']=''
    Path(app.config['UPLOAD_DIR']).mkdir(parents=True, exist_ok=True)
    if not app.config['DATABASE_URL']: init_db(app.config['DATABASE_PATH'])

    def db():
        if 'db' not in g: g.db=connect_app(app.config['DATABASE_PATH'],app.config['DATABASE_URL'])
        return g.db

    @app.teardown_appcontext
    def close_db(exc):
        conn=g.pop('db',None)
        if conn: conn.close()

    @app.before_request
    def load_user():
        # Validate Host before url_for can be called in the login redirect.
        request.host
        g.user=None
        g.show_tutorial=False
        g.appearance=DEFAULT_APPEARANCE.copy()
        if session.get('uid'):
            g.user=db().execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
            if not g.user or session.get('auth_version',0)!=g.user['session_version']:
                session.clear(); g.user=None
            else:
                choice=db().execute('SELECT theme,font,text_size,density,motion FROM user_appearance WHERE user_id=?',(g.user['id'],)).fetchone()
                if choice: g.appearance=dict(choice)
        if g.user and request.method=='GET' and request.endpoint not in {'static','media_file'}:
            g.show_tutorial=bool(session.pop('tour_pending',False))
        if 'csrf' not in session: session['csrf']=secrets.token_urlsafe(24)
        if not g.user and request.endpoint not in {'login','register','static','rules','privacy','terms','help_page'}:
            return redirect(url_for('login',next=request.path))
        if request.method in ('POST','PUT','PATCH','DELETE'):
            token=request.form.get('csrf') or request.headers.get('X-CSRF-Token')
            if not token or not secrets.compare_digest(token, session['csrf']): abort(400,'Invalid form token. Refresh and try again.')

    @app.context_processor
    def inject():
        def page_url(page):
            args=request.args.to_dict(flat=True)
            args['page']=page
            return url_for(request.endpoint,**(request.view_args or {}),**args)
        return {'current_user':g.get('user'),'csrf_token':lambda:session['csrf'],
                'app_version':APP_VERSION,
                'show_tutorial':g.get('show_tutorial',False),
                'appearance':g.get('appearance',DEFAULT_APPEARANCE),
                'page_url':page_url,
                'all_tags':db().execute('SELECT * FROM tags WHERE approved=1 AND slug != ? ORDER BY kind,name',('announcements',)).fetchall()}

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers['Cross-Origin-Resource-Policy']='same-origin'
        if response.mimetype=='text/html' or request.endpoint=='media_file':
            response.headers['Cache-Control']='private, no-store'
        return response

    def login_required(fn):
        @wraps(fn)
        def inner(*args,**kwargs):
            if not g.user:
                flash('Sign in to continue.','info')
                return redirect(url_for('login',next=request.path))
            return fn(*args,**kwargs)
        return inner

    def moderator_required(fn):
        @wraps(fn)
        @login_required
        def inner(*args,**kwargs):
            if g.user['role'] not in ('moderator','admin'): abort(403)
            return fn(*args,**kwargs)
        return inner

    def limited(key, count=12, window=60):
        now=int(time.time())
        with db() as conn:
            if app.config['DATABASE_URL']: conn.execute('SELECT pg_advisory_xact_lock(hashtext(?))',(key,))
            else: conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT window_started,hits FROM rate_limits WHERE key=?',(key,)).fetchone()
            if row and now-row['window_started']<window:
                hits=row['hits']+1
                conn.execute('UPDATE rate_limits SET hits=? WHERE key=?',(hits,key))
            else:
                hits=1
                conn.execute('INSERT INTO rate_limits(key,window_started,hits) VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET window_started=excluded.window_started,hits=1',(key,now))
            if now % 97 == 0:
                conn.execute('DELETE FROM rate_limits WHERE window_started<?',(now-86400,))
        if hits>count: abort(429,'Too many attempts. Try again shortly.')

    def safe_next_path(value):
        if not value or not value.startswith('/') or value.startswith('//') or '\\' in value or any(ord(char)<32 for char in value):
            return '/'
        parts=urlsplit(value)
        return value if not parts.scheme and not parts.netloc else '/'

    def same_origin_back(fallback):
        reference=request.referrer
        if reference:
            parts=urlsplit(reference)
            if parts.scheme in ('http','https') and parts.netloc==request.host and parts.path.startswith('/') and '\\' not in parts.path:
                target=parts.path+('?' + parts.query if parts.query else '')
                return redirect(target)
        return redirect(fallback)

    def render_feed(where='p.status=?',params=('published',),sort='new',page=1):
        order={'new':'p.created_at DESC,p.id DESC','top':'score DESC,p.created_at DESC,p.id DESC'}.get(sort,'p.created_at DESC,p.id DESC')
        page=max(1,min(page,10000)); per=8; uid=g.user['id'] if g.user else 0
        rows=db().execute(f'''SELECT p.*,u.username,u.avatar,
          COALESCE((SELECT SUM(value) FROM votes v WHERE v.target_type='post' AND v.target_id=p.id),0) score,
          (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id AND c.status='published') comment_count,
          COALESCE((SELECT value FROM votes v WHERE v.user_id=? AND v.target_type='post' AND v.target_id=p.id),0) my_vote,
          EXISTS(SELECT 1 FROM saves s WHERE s.user_id=? AND s.post_id=p.id) saved
          FROM posts p JOIN users u ON u.id=p.author_id WHERE {where}
          ORDER BY {order} LIMIT ? OFFSET ?''',(uid,uid,*params,per+1,(page-1)*per)).fetchall()
        has_more=len(rows)>per; rows=rows[:per]
        posts=[dict(row) for row in rows]
        if not posts: return posts,has_more
        ids=[post['id'] for post in posts]
        placeholders=','.join('?' for _ in ids)
        tags_by_post={post_id:[] for post_id in ids}
        for tag in db().execute(f'''SELECT pt.post_id,t.* FROM post_tags pt JOIN tags t ON t.id=pt.tag_id
            WHERE pt.post_id IN ({placeholders}) ORDER BY t.kind,t.name''',ids):
            tags_by_post[tag['post_id']].append(tag)
        covers={}
        for cover in db().execute(f"SELECT * FROM media WHERE kind='post' AND post_id IN ({placeholders}) ORDER BY post_id,id",ids):
            covers.setdefault(cover['post_id'],cover)
        for post in posts:
            post['tags']=tags_by_post[post['id']]
            post['cover']=covers.get(post['id'])
            post['saved']=bool(post['saved'])
        return posts,has_more

    @app.route('/')
    def index():
        sort=request.args.get('sort','new')
        if sort not in ('new','top','following'): sort='new'
        page=request.args.get('page',1,type=int)
        tag=request.args.get('tag','')
        where='p.status=?'; params=['published']
        if tag:
            where+=' AND EXISTS (SELECT 1 FROM post_tags pt JOIN tags t ON t.id=pt.tag_id WHERE pt.post_id=p.id AND t.slug=? AND t.approved=1)'; params.append(tag)
        if sort=='following':
            if not g.user: return redirect(url_for('login',next='/'))
            where+=' AND (EXISTS (SELECT 1 FROM post_tags pt JOIN follows f ON f.tag_id=pt.tag_id WHERE pt.post_id=p.id AND f.user_id=?) OR EXISTS (SELECT 1 FROM user_follows uf WHERE uf.following_id=p.author_id AND uf.follower_id=?))'; params.extend((g.user['id'],g.user['id']))
        posts,more=render_feed(where,tuple(params),'top' if sort=='top' else 'new',page)
        onboarding=None
        if g.user and sort=='new' and page==1 and not tag:
            row=db().execute('SELECT * FROM user_onboarding WHERE user_id=? AND dismissed_at IS NULL',(g.user['id'],)).fetchone()
            if row:
                followed=bool(db().execute('SELECT 1 FROM follows WHERE user_id=? LIMIT 1',(g.user['id'],)).fetchone())
                saved=bool(db().execute('SELECT 1 FROM saves WHERE user_id=? LIMIT 1',(g.user['id'],)).fetchone())
                profile_ready=bool(g.user['bio'].strip() or g.user['avatar'])
                onboarding={'followed':followed,'saved':saved,'profile_ready':profile_ready,'count':sum((followed,saved,profile_ready)),
                            'suggestions':db().execute("SELECT * FROM tags WHERE approved=1 AND kind='general' AND slug IN ('questions','stories','wellness') ORDER BY name").fetchall()}
        return render_template('feed.html',posts=posts,more=more,page=page,sort=sort,active_tag=tag,title='Community feed',onboarding=onboarding)

    @app.route('/search')
    def search():
        q=request.args.get('q','').strip()[:100]
        page=request.args.get('page',1,type=int)
        if not q: return render_template('feed.html',posts=[],more=False,page=1,sort='new',active_tag='',title='Search',query=q)
        pattern='%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        operator='ILIKE' if app.config['DATABASE_URL'] else 'LIKE'
        posts,more=render_feed(f"p.status='published' AND (p.title {operator} ? ESCAPE '\\' OR p.body {operator} ? ESCAPE '\\')",(pattern,pattern),'new',page)
        return render_template('feed.html',posts=posts,more=more,page=page,sort='new',active_tag='',title='Search results',query=q)

    @app.route('/topics')
    def topics():
        tags=db().execute('SELECT t.*, (SELECT COUNT(*) FROM post_tags pt JOIN posts p ON p.id=pt.post_id WHERE pt.tag_id=t.id AND p.status=?) post_count FROM tags t WHERE approved=1 AND slug!=? ORDER BY kind,name',('published','announcements')).fetchall()
        general=[tag for tag in tags if tag['kind']=='general']
        proposed=[tag for tag in tags if tag['kind']=='proposed']
        ranges=(('A–G','a-g','A','G'),('H–P','h-p','H','P'),('Q–Z','q-z','Q','Z'))
        groups=[{'label':label,'slug':slug,'tags':[tag for tag in proposed if start <= tag['name'][0].upper() <= end]}
                for label,slug,start,end in ranges]
        return render_template('topics.html',general=general,groups=groups)

    @app.route('/topics/<slug>')
    def topic(slug):
        tag=db().execute('SELECT * FROM tags WHERE slug=? AND approved=1',(slug,)).fetchone()
        if not tag: abort(404)
        page=request.args.get('page',1,type=int); sort=request.args.get('sort','new')
        posts,more=render_feed("p.status='published' AND EXISTS (SELECT 1 FROM post_tags pt WHERE pt.post_id=p.id AND pt.tag_id=?)",(tag['id'],),'top' if sort=='top' else 'new',page)
        following=bool(g.user and db().execute('SELECT 1 FROM follows WHERE user_id=? AND tag_id=?',(g.user['id'],tag['id'])).fetchone())
        return render_template('feed.html',posts=posts,more=more,page=page,sort=sort,active_tag=slug,title=tag['name'],description=tag['description'],topic=tag,following=following)

    @app.post('/topics/<slug>/follow')
    @login_required
    def follow(slug):
        tag=db().execute('SELECT * FROM tags WHERE slug=? AND approved=1',(slug,)).fetchone()
        if not tag: abort(404)
        with db() as conn:
            old=conn.execute('SELECT 1 FROM follows WHERE user_id=? AND tag_id=?',(g.user['id'],tag['id'])).fetchone()
            if old: conn.execute('DELETE FROM follows WHERE user_id=? AND tag_id=?',(g.user['id'],tag['id']))
            else: conn.execute('INSERT INTO follows(user_id,tag_id) VALUES(?,?)',(g.user['id'],tag['id']))
        if request.headers.get('Accept')=='application/json': return jsonify(following=not bool(old))
        return redirect(url_for('topic',slug=slug))

    @app.route('/register',methods=['GET','POST'])
    def register():
        if g.user: return redirect(url_for('index'))
        if request.method=='POST':
            limited('register-ip:'+str(request.remote_addr),5,300)
            username=request.form.get('username','').strip(); password=request.form.get('password','')
            if not re.fullmatch(r'[A-Za-z0-9_]{3,24}',username) or username.lower() in ('admin','moderator','staff','louw','support'):
                flash('Username must be 3–24 letters, numbers, or underscores and cannot imply staff status.','error')
            elif len(password)<12 or len(password)>128:
                flash('Use a password between 12 and 128 characters.','error')
            elif request.form.get('rules')!='yes' or request.form.get('privacy')!='yes':
                flash('Please acknowledge the community and privacy notices.','error')
            else:
                try:
                    with db() as conn:
                        created=conn.execute('INSERT INTO users(username,password_hash) VALUES(?,?) RETURNING id',(username,generate_password_hash(password,method='scrypt'))).fetchone()
                        conn.execute('INSERT INTO user_onboarding(user_id) VALUES(?)',(created['id'],))
                    session.clear(); session['uid']=created['id']; session['auth_version']=0; session['csrf']=secrets.token_urlsafe(24)
                    session['tour_pending']=True
                    session.permanent=request.form.get('remember')=='yes'
                    return redirect(url_for('index'))
                except (sqlite3.IntegrityError, psycopg.errors.UniqueViolation): flash('That username is unavailable.','error')
        return render_template('auth.html',mode='register')

    @app.route('/login',methods=['GET','POST'])
    def login():
        if g.user: return redirect(url_for('index'))
        if request.method=='POST':
            username=request.form.get('username','').strip()[:100]
            password=request.form.get('password','')
            limited('login-ip:'+str(request.remote_addr),20,300)
            limited('login-name:'+username.casefold(),8,300)
            user=db().execute('SELECT * FROM users WHERE lower(username)=lower(?)',(username,)).fetchone()
            if user and len(password)<=128 and check_password_hash(user['password_hash'],password):
                session.clear(); session['uid']=user['id']; session['auth_version']=user['session_version']; session['csrf']=secrets.token_urlsafe(24)
                session.permanent=request.form.get('remember')=='yes'
                dest=request.args.get('next','/')
                return redirect(safe_next_path(dest))
            flash('Invalid username or password.','error')
        return render_template('auth.html',mode='login')

    @app.post('/logout')
    @login_required
    def logout():
        session.clear(); flash('Signed out.','info'); return redirect(url_for('index'))

    def image_upload(file):
        if not file or not file.filename: raise ValueError('Choose an image first.')
        raw=file.read(MAX_UPLOAD+1)
        if len(raw)>MAX_UPLOAD: raise ValueError('Image must be 10 MB or smaller.')
        try:
            im=Image.open(io.BytesIO(raw)); im.verify()
            im=Image.open(io.BytesIO(raw))
            if im.format not in ('JPEG','PNG','WEBP'): raise ValueError('Only JPEG, PNG, and WebP images are allowed.')
            if im.width*im.height>25_000_000: raise ValueError('Image dimensions are too large.')
            im=im.convert('RGB'); im.thumbnail((2000,2000))
            name=secrets.token_hex(20)+'.jpg'; dest=Path(app.config['UPLOAD_DIR'])/name
            im.save(dest,'JPEG',quality=86,optimize=True)
            return name
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc:
            raise ValueError('The image could not be decoded safely.') from exc

    def save_media(conn, media_id, filename):
        if app.config['DATABASE_URL']:
            content=(Path(app.config['UPLOAD_DIR'])/filename).read_bytes()
            conn.execute('INSERT INTO media_bytes(media_id,content) VALUES(?,?)',(media_id,content))

    @app.route('/members/<username>')
    def profile(username):
        user=db().execute('SELECT id,username,bio,avatar,role,created_at FROM users WHERE username=?',(username,)).fetchone()
        if not user: abort(404)
        page=max(1,request.args.get('page',1,type=int))
        posts,more=render_feed("p.status='published' AND p.author_id=?",(user['id'],),'new',page)
        followers=db().execute('SELECT COUNT(*) n FROM user_follows WHERE following_id=?',(user['id'],)).fetchone()['n']
        following_count=db().execute('SELECT COUNT(*) n FROM user_follows WHERE follower_id=?',(user['id'],)).fetchone()['n']
        is_following=bool(g.user and db().execute('SELECT 1 FROM user_follows WHERE follower_id=? AND following_id=?',(g.user['id'],user['id'])).fetchone())
        return render_template('profile.html',profile=user,posts=posts,more=more,page=page,followers=followers,following_count=following_count,is_following=is_following)

    @app.post('/members/<username>/follow')
    @login_required
    def follow_member(username):
        user=db().execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()
        if not user: abort(404)
        if user['id']==g.user['id']: abort(400,'You cannot follow yourself.')
        with db() as conn:
            old=conn.execute('SELECT 1 FROM user_follows WHERE follower_id=? AND following_id=?',(g.user['id'],user['id'])).fetchone()
            if old: conn.execute('DELETE FROM user_follows WHERE follower_id=? AND following_id=?',(g.user['id'],user['id']))
            else: conn.execute('INSERT INTO user_follows(follower_id,following_id) VALUES(?,?)',(g.user['id'],user['id']))
        if request.headers.get('Accept')=='application/json': return jsonify(following=not bool(old))
        return redirect(url_for('profile',username=username))

    @app.route('/members/<username>/connections')
    def member_connections(username):
        user=db().execute('SELECT id,username,avatar FROM users WHERE username=?',(username,)).fetchone()
        if not user: abort(404)
        view=request.args.get('view','followers')
        if view not in ('followers','following'): abort(404)
        page=max(1,request.args.get('page',1,type=int)); limit=24
        if view=='followers':
            rows=db().execute('SELECT u.id,u.username,u.avatar FROM user_follows f JOIN users u ON u.id=f.follower_id WHERE f.following_id=? ORDER BY f.created_at DESC,f.follower_id DESC LIMIT ? OFFSET ?',(user['id'],limit+1,(page-1)*limit)).fetchall()
        else:
            rows=db().execute('SELECT u.id,u.username,u.avatar FROM user_follows f JOIN users u ON u.id=f.following_id WHERE f.follower_id=? ORDER BY f.created_at DESC,f.following_id DESC LIMIT ? OFFSET ?',(user['id'],limit+1,(page-1)*limit)).fetchall()
        return render_template('connections.html',profile=user,view=view,members=rows[:limit],more=len(rows)>limit,page=page)

    @app.route('/settings',methods=['GET','POST'])
    @login_required
    def settings():
        if request.method=='POST':
            bio=request.form.get('bio','').strip()
            errors={}
            if len(bio)>500: errors['bio']='Bio must be 500 characters or fewer.'
            upload=request.files.get('avatar')
            name=None
            if upload and upload.filename and not errors:
                try: name=image_upload(upload)
                except ValueError as exc: errors['avatar']=str(exc)
            if errors:
                return render_template('settings.html',profile_bio=bio,errors=errors),422
            try:
                with db() as conn:
                    avatar_id=g.user['avatar']
                    if name:
                        avatar_id=conn.execute("INSERT INTO media(user_id,filename,kind,consent) VALUES(?,?,'avatar',1) RETURNING id",(g.user['id'],name)).fetchone()['id']
                        save_media(conn,avatar_id,name)
                    conn.execute('UPDATE users SET bio=?,avatar=? WHERE id=?',(bio,avatar_id,g.user['id']))
            except Exception:
                if name: (Path(app.config['UPLOAD_DIR'])/name).unlink(missing_ok=True)
                raise
            flash('Profile updated.','success')
            return redirect(url_for('settings'))
        return render_template('settings.html',profile_bio=g.user['bio'] or '',errors={})

    @app.post('/settings/appearance')
    @login_required
    def save_appearance():
        values={key:request.form.get(key,'') for key in DEFAULT_APPEARANCE}
        if any(value not in APPEARANCE_CHOICES[key] for key,value in values.items()):
            abort(400,'Choose an available appearance setting.')
        with db() as conn:
            conn.execute('''INSERT INTO user_appearance(user_id,theme,font,text_size,density,motion)
                VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                theme=excluded.theme,font=excluded.font,text_size=excluded.text_size,
                density=excluded.density,motion=excluded.motion''',
                (g.user['id'],values['theme'],values['font'],values['text_size'],values['density'],values['motion']))
        flash('Appearance saved.','success')
        return redirect(url_for('settings')+'#appearance')

    @app.post('/settings/password')
    @login_required
    def change_password():
        limited('password-user:'+str(g.user['id']),5,900)
        current=request.form.get('current_password','')
        replacement=request.form.get('new_password','')
        confirmation=request.form.get('confirm_password','')
        if not check_password_hash(g.user['password_hash'],current):
            error='Current password is incorrect.'
        elif not 12<=len(replacement)<=128:
            error='New password must be 12–128 characters.'
        elif replacement!=confirmation:
            error='New passwords do not match.'
        elif replacement==current:
            error='Choose a different new password.'
        else:
            error=None
        if error:
            return render_template('settings.html',profile_bio=g.user['bio'] or '',errors={},password_error=error),422
        with db() as conn:
            conn.execute('UPDATE users SET password_hash=?,session_version=session_version+1 WHERE id=?',
                         (generate_password_hash(replacement,method='scrypt'),g.user['id']))
            version=conn.execute('SELECT session_version FROM users WHERE id=?',(g.user['id'],)).fetchone()['session_version']
        remembered=session.permanent
        session.clear(); session['uid']=g.user['id']; session['auth_version']=version
        session['csrf']=secrets.token_urlsafe(24); session.permanent=remembered
        flash('Password changed. Other signed-in devices must sign in again.','success')
        return redirect(url_for('settings')+'#password')

    @app.post('/avatar')
    @login_required
    def avatar():
        # Compatibility for older forms and bookmarks; the settings form is canonical.
        if not request.files.get('avatar') or not request.files['avatar'].filename:
            return render_template('settings.html',profile_bio=g.user['bio'] or '',errors={'avatar':'Choose an image first.'}),422
        try: name=image_upload(request.files['avatar'])
        except ValueError as exc: return render_template('settings.html',profile_bio=g.user['bio'] or '',errors={'avatar':str(exc)}),422
        with db() as conn:
            avatar_id=conn.execute("INSERT INTO media(user_id,filename,kind,consent) VALUES(?,?,'avatar',1) RETURNING id",(g.user['id'],name)).fetchone()['id']
            save_media(conn,avatar_id,name)
            conn.execute('UPDATE users SET avatar=? WHERE id=?',(avatar_id,g.user['id']))
        flash('Profile updated.','success'); return redirect(url_for('settings'))

    @app.route('/media/<int:media_id>')
    def media_file(media_id):
        item=db().execute('SELECT m.*,p.status post_status FROM media m LEFT JOIN posts p ON p.id=m.post_id WHERE m.id=?',(media_id,)).fetchone()
        if not item: abort(404)
        if item['kind']=='avatar' and not db().execute('SELECT 1 FROM users WHERE avatar=?',(media_id,)).fetchone():
            if not (g.user and (g.user['id']==item['user_id'] or g.user['role'] in ('moderator','admin'))): abort(404)
        if item['kind']=='post' and item['post_status']!='published' and not (g.user and (g.user['id']==item['user_id'] or g.user['role'] in ('moderator','admin'))): abort(404)
        path=Path(app.config['UPLOAD_DIR'])/item['filename']
        if path.is_file(): return send_file(path,mimetype='image/jpeg',max_age=0)
        if app.config['DATABASE_URL']:
            stored=db().execute('SELECT content FROM media_bytes WHERE media_id=?',(media_id,)).fetchone()
            if stored: return send_file(io.BytesIO(stored['content']),mimetype='image/jpeg',max_age=0)
        abort(404)

    def valid_post(form):
        typ=form.get('type','story'); title=form.get('title','').strip(); body=form.get('body','').strip()
        errors={}
        if typ not in ('story','question','progress'): errors['type']='Choose a post type.'
        if not 3<=len(title)<=120: errors['title']='Title must be 3–120 characters.'
        if len(body)<10: errors['body']='Post must be at least 10 characters.'
        elif len(words(body))>POST_WORD_LIMIT: errors['body']='Post must be 1,000 words or fewer.'
        elif len(body)>10000: errors['body']='Post must be 10,000 characters or fewer.'
        if contains_blocked_slur(title,app.config['BLOCKED_SLURS']): errors['title']='Remove identity-based slurs before publishing.'
        if contains_blocked_slur(body,app.config['BLOCKED_SLURS']): errors['body']='Remove identity-based slurs before publishing.'
        tag_ids=[]
        for raw in form.getlist('tags'):
            if not raw.isdigit(): continue
            tag=db().execute("SELECT id FROM tags WHERE id=? AND approved=1 AND slug!='announcements'",(int(raw),)).fetchone()
            if tag and tag['id'] not in tag_ids: tag_ids.append(tag['id'])
        if not tag_ids: errors['tags']='Choose at least one available topic.'
        return (typ,title,body,tag_ids),errors

    def composer_error(post,errors):
        if 'application/json' in request.headers.get('Accept',''):
            return jsonify({'errors':errors}),422
        values={key:request.form.get(key,'') for key in ('type','title','body')}
        selected=[int(x) for x in request.form.getlist('tags') if x.isdigit()]
        return render_template('composer.html',post=post,form_values=values,selected=selected,
                               errors=errors,consent_checked=request.form.get('photo_consent')=='yes',
                               file_reset=bool(request.files.getlist('images') and any(f.filename for f in request.files.getlist('images')))),422

    @app.route('/create',methods=['GET','POST'])
    @login_required
    def create_post():
        if request.method=='POST':
            limited('post:'+str(g.user['id']),8,60)
            if request.form.get('intent')=='draft':
                title=request.form.get('title','').strip()[:120]
                body=request.form.get('body','').strip()
                if len(words(body))>POST_WORD_LIMIT or len(body)>10000:
                    return composer_error(None,{'body':'Draft must be 1,000 words and 10,000 characters or fewer.'})
                typ=request.form.get('type','story')
                if typ not in ('story','question','progress'): typ='story'
                with db() as conn:
                    cur=conn.execute("INSERT INTO posts(author_id,type,title,body,status) VALUES(?,?,?,?,'draft')",(g.user['id'],typ,title,body))
                flash('Private draft saved. Photos are added when you publish.','success')
                return redirect(url_for('drafts'))
            (typ,title,body,tag_ids),errors=valid_post(request.form)
            files=[f for f in request.files.getlist('images') if f.filename]
            if len(files)>8: errors['images']='Upload no more than eight images.'
            if files and request.form.get('photo_consent')!='yes': errors['photo_consent']='Confirm photo rights and consent before publishing.'
            labels=request.form.getlist('image_label'); captions=request.form.getlist('image_caption')
            if files and typ=='progress' and (len(labels)<len(files) or any(x not in ('Before','After','Other') for x in labels[:len(files)])):
                errors['images']='Label each progress image Before, After, or Other.'
            if errors: return composer_error(None,errors)
            names=[]
            try:
                for file in files: names.append(image_upload(file))
                with db() as conn:
                    pid=conn.execute('INSERT INTO posts(author_id,type,title,body) VALUES(?,?,?,?) RETURNING id',(g.user['id'],typ,title,body)).fetchone()['id']
                    conn.executemany('INSERT INTO post_tags(post_id,tag_id) VALUES(?,?)',[(pid,x) for x in tag_ids])
                    for i,name in enumerate(names):
                        caption=captions[i].strip()[:300] if i<len(captions) else ''
                        label=labels[i] if i<len(labels) and labels[i] in ('Before','After','Other') else 'Other'
                        media_id=conn.execute("INSERT INTO media(post_id,user_id,filename,kind,label,caption,consent) VALUES(?,?,?,'post',?,?,1) RETURNING id",(pid,g.user['id'],name,label,caption)).fetchone()['id']
                        save_media(conn,media_id,name)
            except ValueError as exc:
                for name in names: (Path(app.config['UPLOAD_DIR'])/name).unlink(missing_ok=True)
                return composer_error(None,{'images':str(exc)})
            except Exception:
                for name in names: (Path(app.config['UPLOAD_DIR'])/name).unlink(missing_ok=True)
                raise
            flash('Post published.','success'); return redirect(url_for('post_detail',post_id=pid))
        return render_template('composer.html',post=None,form_values={'type':'story','title':'','body':''},selected=[],errors={},consent_checked=False,file_reset=False)

    @app.route('/drafts')
    @login_required
    def drafts():
        rows=db().execute("SELECT * FROM posts WHERE author_id=? AND status='draft' ORDER BY updated_at DESC,id DESC",(g.user['id'],)).fetchall()
        return render_template('drafts.html',drafts=rows)

    @app.route('/posts/<int:post_id>')
    def post_detail(post_id):
        post=db().execute('SELECT p.*,u.username,u.avatar FROM posts p JOIN users u ON u.id=p.author_id WHERE p.id=?',(post_id,)).fetchone()
        if not post or post['status']=='deleted': abort(404)
        if post['status']=='draft' and not (g.user and (g.user['id']==post['author_id'] or g.user['role'] in ('moderator','admin'))): abort(404)
        if post['status']=='hidden' and not (g.user and (g.user['id']==post['author_id'] or g.user['role'] in ('moderator','admin'))): abort(404)
        tags=db().execute('SELECT t.* FROM tags t JOIN post_tags pt ON pt.tag_id=t.id WHERE pt.post_id=?',(post_id,)).fetchall()
        images=db().execute("SELECT * FROM media WHERE post_id=? AND kind='post' ORDER BY id",(post_id,)).fetchall()
        sort=request.args.get('comments','top')
        if sort not in ('top','new','oldest'): sort='top'
        rows=db().execute('''SELECT c.*,u.username,u.avatar,COALESCE((SELECT SUM(value) FROM votes v WHERE v.target_type='comment' AND v.target_id=c.id),0) score
          FROM comments c JOIN users u ON u.id=c.author_id WHERE c.post_id=? AND c.status!='deleted' ''', (post_id,)).fetchall()
        visible=[dict(x) for x in rows if x['status']=='published' or (g.user and g.user['role'] in ('moderator','admin'))]
        def ordered(items):
            if sort=='top': return sorted(items,key=lambda x:(-x['score'],x['created_at'],x['id']))
            return sorted(items,key=lambda x:(x['created_at'],x['id']),reverse=(sort=='new'))
        roots=ordered([x for x in visible if x['parent_id'] is None])
        comments=[]
        for root in roots:
            comments.append(root)
            comments.extend(ordered([x for x in visible if x['parent_id']==root['id']]))
        score=db().execute("SELECT COALESCE(SUM(value),0) n FROM votes WHERE target_type='post' AND target_id=?",(post_id,)).fetchone()['n']
        mine=db().execute("SELECT value FROM votes WHERE user_id=? AND target_type='post' AND target_id=?",(g.user['id'],post_id)).fetchone() if g.user else None
        saved=bool(g.user and db().execute('SELECT 1 FROM saves WHERE user_id=? AND post_id=?',(g.user['id'],post_id)).fetchone())
        comment_attempt=g.get('comment_attempt',{})
        if comment_attempt.get('post_id')!=post_id: comment_attempt={}
        return render_template('post.html',post=post,tags=tags,images=images,comments=comments,sort=sort,score=score,my_vote=mine['value'] if mine else 0,saved=saved,comment_attempt=comment_attempt)

    @app.route('/posts/<int:post_id>/edit',methods=['GET','POST'])
    @login_required
    def edit_post(post_id):
        post=db().execute('SELECT * FROM posts WHERE id=?',(post_id,)).fetchone()
        if not post or post['status']=='deleted': abort(404)
        if g.user['id']!=post['author_id'] and g.user['role'] not in ('moderator','admin'): abort(403)
        if request.method=='POST':
            if request.form.get('intent')=='draft' and post['status']=='draft':
                title=request.form.get('title','').strip()[:120]; body=request.form.get('body','').strip()
                if len(words(body))>POST_WORD_LIMIT or len(body)>10000:
                    return composer_error(post,{'body':'Draft must be 1,000 words and 10,000 characters or fewer.'})
                typ=request.form.get('type','story')
                if typ not in ('story','question','progress'): typ='story'
                with db() as conn: conn.execute('UPDATE posts SET type=?,title=?,body=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(typ,title,body,post_id))
                flash('Draft updated.','success'); return redirect(url_for('drafts'))
            (typ,title,body,tag_ids),errors=valid_post(request.form)
            if errors: return composer_error(post,errors)
            with db() as conn:
                conn.execute("UPDATE posts SET type=?,title=?,body=?,status='published',updated_at=CURRENT_TIMESTAMP WHERE id=?",(typ,title,body,post_id))
                conn.execute('DELETE FROM post_tags WHERE post_id=?',(post_id,))
                conn.executemany('INSERT INTO post_tags(post_id,tag_id) VALUES(?,?)',[(post_id,x) for x in tag_ids])
            flash('Post updated. Existing photos remain attached.','success'); return redirect(url_for('post_detail',post_id=post_id))
        selected=[r['tag_id'] for r in db().execute('SELECT tag_id FROM post_tags WHERE post_id=?',(post_id,))]
        return render_template('composer.html',post=post,form_values={'type':post['type'],'title':post['title'],'body':post['body']},selected=selected,errors={},consent_checked=False,file_reset=False)

    @app.post('/posts/<int:post_id>/delete')
    @login_required
    def delete_post(post_id):
        post=db().execute('SELECT * FROM posts WHERE id=?',(post_id,)).fetchone()
        if not post: abort(404)
        if g.user['id']!=post['author_id'] and g.user['role'] not in ('moderator','admin'): abort(403)
        with db() as conn: conn.execute("UPDATE posts SET status='deleted',updated_at=CURRENT_TIMESTAMP WHERE id=?",(post_id,))
        flash('Post removed from public view.','success'); return redirect(url_for('index'))

    @app.post('/posts/<int:post_id>/comment')
    @login_required
    def add_comment(post_id):
        limited('comment:'+str(g.user['id']),15,60)
        if not db().execute("SELECT 1 FROM posts WHERE id=? AND status='published'",(post_id,)).fetchone(): abort(404)
        body=request.form.get('body','').strip(); parent=request.form.get('parent_id','')
        error=None
        if not 2<=len(body)<=2000: error='Comment must be 2–2,000 characters.'
        elif contains_blocked_slur(body,app.config['BLOCKED_SLURS']): error='Remove identity-based slurs before publishing.'
        if error:
            g.comment_attempt={'post_id':post_id,'parent':parent,'body':body,'error':error}
            return post_detail(post_id),422
        parent_id=None
        if parent:
            row=db().execute("SELECT id,parent_id FROM comments WHERE id=? AND post_id=? AND status='published'",(parent,post_id)).fetchone()
            if not row: abort(400)
            parent_id=row['parent_id'] or row['id']
        with db() as conn:
            conn.execute('INSERT INTO comments(post_id,author_id,parent_id,body) VALUES(?,?,?,?)',(post_id,g.user['id'],parent_id,body))
            post_author=conn.execute('SELECT author_id FROM posts WHERE id=?',(post_id,)).fetchone()['author_id']
            if post_author!=g.user['id']:
                conn.execute('INSERT INTO notifications(recipient_id,kind,message,url) VALUES(?,?,?,?)',(post_author,'comment',f"{g.user['username']} commented on your post",url_for('post_detail',post_id=post_id)+'#comments'))
        return redirect(url_for('post_detail',post_id=post_id)+'#comments')

    @app.post('/comments/<int:comment_id>/delete')
    @login_required
    def delete_comment(comment_id):
        row=db().execute('SELECT * FROM comments WHERE id=?',(comment_id,)).fetchone()
        if not row: abort(404)
        if g.user['id']!=row['author_id'] and g.user['role'] not in ('moderator','admin'): abort(403)
        with db() as conn: conn.execute("UPDATE comments SET status='deleted',body='[removed]' WHERE id=?",(comment_id,))
        return redirect(url_for('post_detail',post_id=row['post_id'])+'#comments')

    @app.post('/vote/<target_type>/<int:target_id>')
    @login_required
    def vote(target_type,target_id):
        if target_type not in ('post','comment'): abort(404)
        table='posts' if target_type=='post' else 'comments'
        if not db().execute(f"SELECT 1 FROM {table} WHERE id=? AND status='published'",(target_id,)).fetchone(): abort(404)
        try: value=int(request.form.get('value',0))
        except ValueError: abort(400)
        if value not in (-1,1): abort(400)
        with db() as conn:
            old=conn.execute('SELECT value FROM votes WHERE user_id=? AND target_type=? AND target_id=?',(g.user['id'],target_type,target_id)).fetchone()
            if old and old['value']==value:
                conn.execute('DELETE FROM votes WHERE user_id=? AND target_type=? AND target_id=?',(g.user['id'],target_type,target_id))
                active=0
            else:
                conn.execute('INSERT INTO votes(user_id,target_type,target_id,value) VALUES(?,?,?,?) ON CONFLICT(user_id,target_type,target_id) DO UPDATE SET value=excluded.value',(g.user['id'],target_type,target_id,value))
                active=value
            score=conn.execute('SELECT COALESCE(SUM(value),0) n FROM votes WHERE target_type=? AND target_id=?',(target_type,target_id)).fetchone()['n']
        if request.headers.get('Accept')=='application/json': return jsonify(score=score,active=active)
        return same_origin_back(url_for('index'))

    @app.post('/posts/<int:post_id>/save')
    @login_required
    def save_post(post_id):
        if not db().execute("SELECT 1 FROM posts WHERE id=? AND status='published'",(post_id,)).fetchone(): abort(404)
        with db() as conn:
            old=conn.execute('SELECT 1 FROM saves WHERE user_id=? AND post_id=?',(g.user['id'],post_id)).fetchone()
            if old: conn.execute('DELETE FROM saves WHERE user_id=? AND post_id=?',(g.user['id'],post_id))
            else: conn.execute('INSERT INTO saves(user_id,post_id) VALUES(?,?)',(g.user['id'],post_id))
        if request.headers.get('Accept')=='application/json': return jsonify(saved=not bool(old))
        return same_origin_back(url_for('post_detail',post_id=post_id))

    @app.post('/onboarding/dismiss')
    @login_required
    def dismiss_onboarding():
        with db() as conn:
            conn.execute('UPDATE user_onboarding SET dismissed_at=CURRENT_TIMESTAMP WHERE user_id=?',(g.user['id'],))
        return redirect(url_for('index'))

    @app.route('/saved')
    @login_required
    def saved_posts():
        posts,more=render_feed("p.status='published' AND EXISTS (SELECT 1 FROM saves s WHERE s.post_id=p.id AND s.user_id=?)",(g.user['id'],),'new',request.args.get('page',1,type=int))
        return render_template('feed.html',posts=posts,more=more,page=request.args.get('page',1,type=int),sort='new',active_tag='',title='Saved posts')

    @app.route('/report/<target_type>/<int:target_id>',methods=['GET','POST'])
    @login_required
    def report(target_type,target_id):
        if target_type not in ('post','comment'): abort(404)
        table='posts' if target_type=='post' else 'comments'
        if not db().execute(f'SELECT 1 FROM {table} WHERE id=?',(target_id,)).fetchone(): abort(404)
        if request.method=='POST':
            reason=request.form.get('reason',''); detail=request.form.get('detail','').strip()
            if reason not in ALLOWED_REASONS or len(detail)>1000: flash('Choose a reason and keep details under 1,000 characters.','error')
            else:
                with db() as conn:
                    report_id=conn.execute('INSERT INTO reports(reporter_id,target_type,target_id,reason,detail) VALUES(?,?,?,?,?) RETURNING id',(g.user['id'],target_type,target_id,reason,detail)).fetchone()['id']
                flash(f'Report #{report_id} received for moderator review.','success')
                return redirect(url_for('index'))
        return render_template('report.html',target_type=target_type,target_id=target_id,reasons=sorted(ALLOWED_REASONS))

    @app.route('/moderation')
    @moderator_required
    def moderation():
        reports=db().execute('SELECT r.*,u.username reporter FROM reports r JOIN users u ON u.id=r.reporter_id WHERE r.status=? ORDER BY r.created_at DESC,r.id DESC',('open',)).fetchall()
        actions=db().execute('SELECT a.*,u.username actor FROM moderation_actions a JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 20').fetchall()
        return render_template('moderation.html',reports=reports,actions=actions)

    @app.post('/moderation/<int:report_id>')
    @moderator_required
    def moderate(report_id):
        report_row=db().execute('SELECT * FROM reports WHERE id=?',(report_id,)).fetchone()
        if not report_row: abort(404)
        action=request.form.get('action'); reason=request.form.get('reason','').strip()
        if action not in ('hide','restore','resolve') or not reason or len(reason)>500: abort(400)
        table='posts' if report_row['target_type']=='post' else 'comments'
        status={'hide':'hidden','restore':'published'}.get(action)
        with db() as conn:
            if status: conn.execute(f'UPDATE {table} SET status=? WHERE id=?',(status,report_row['target_id']))
            conn.execute("UPDATE reports SET status='resolved' WHERE id=?",(report_id,))
            conn.execute('INSERT INTO moderation_actions(actor_id,target_type,target_id,action,reason) VALUES(?,?,?,?,?)',(g.user['id'],report_row['target_type'],report_row['target_id'],action,reason))
            row=conn.execute(f'SELECT author_id FROM {table} WHERE id=?',(report_row['target_id'],)).fetchone()
            if row:
                conn.execute('INSERT INTO notifications(recipient_id,kind,message,url) VALUES(?,?,?,?)',(row['author_id'],'moderation',f'A moderator recorded an action on your {report_row["target_type"]}.',url_for('help_page')))
        flash('Moderation action recorded.','success'); return redirect(url_for('moderation'))

    @app.route('/notifications',methods=['GET','POST'])
    @login_required
    def notifications():
        if request.method=='POST':
            with db() as conn: conn.execute('UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE recipient_id=? AND read_at IS NULL',(g.user['id'],))
            return redirect(url_for('notifications'))
        rows=db().execute('SELECT * FROM notifications WHERE recipient_id=? ORDER BY created_at DESC,id DESC LIMIT 50',(g.user['id'],)).fetchall()
        return render_template('notifications.html',notifications=rows)

    @app.post('/tutorial/finish')
    @login_required
    def finish_tutorial():
        with db() as conn: conn.execute('UPDATE users SET tutorial_done=1 WHERE id=?',(g.user['id'],))
        session.pop('tour_pending',None)
        if request.headers.get('Accept')=='application/json': return jsonify(ok=True)
        return redirect(url_for('index'))

    @app.post('/tutorial/replay')
    @login_required
    def replay_tutorial():
        session['tour_pending']=True
        return redirect(url_for('index'))

    @app.route('/rules')
    def rules(): return render_template('policy.html',kind='Community rules')
    @app.route('/privacy')
    def privacy(): return render_template('policy.html',kind='Privacy notice')
    @app.route('/terms')
    def terms(): return render_template('policy.html',kind='Terms of use')
    @app.route('/help')
    def help_page(): return render_template('policy.html',kind='Help and support')

    @app.errorhandler(SecurityError)
    def untrusted_host(exc):
        return 'Untrusted host.',400

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    @app.errorhandler(429)
    def error_page(exc): return render_template('error.html',code=exc.code,message=exc.description),exc.code

    return app

app=create_app()

if __name__=='__main__':
    command=sys.argv[1] if len(sys.argv)>1 else 'run'
    if command=='init-db':
        if app.config['DATABASE_URL']: raise SystemExit('Hosted schema uses supabase/001_forum_schema.sql; it is already applied.')
        init_db(app.config['DATABASE_PATH']); print('Database initialized:',app.config['DATABASE_PATH'])
    elif command=='seed-demo': seed_demo(app.config['DATABASE_PATH'],app.config['DATABASE_URL']); print('Demo content ready.')
    elif command=='check-db':
        if app.config['DATABASE_URL']:
            with connect_app(app.config['DATABASE_PATH'],app.config['DATABASE_URL']) as conn:
                print('Hosted database reachable. Posts:',conn.execute('SELECT count(*) n FROM posts').fetchone()['n'])
        else: print('Database integrity:',check_db(app.config['DATABASE_PATH']))
    elif command=='backup-db':
        if app.config['DATABASE_URL']: raise SystemExit('This command only backs up historical SQLite data; configure hosted backups in Supabase.')
        stamp=time.strftime('%Y%m%d-%H%M%S',time.localtime())
        target=ROOT/'instance'/'backups'/f'forum-{stamp}.zip'
        print('Backup created:',backup_data(app.config['DATABASE_PATH'],app.config['UPLOAD_DIR'],target))
    elif command=='run':
        app.run(host=os.environ.get('FORUM_HOST','127.0.0.1'),port=int(os.environ.get('PORT','5000')),debug=False)
    else: raise SystemExit('Use run, init-db, seed-demo, check-db, or backup-db')

