import io
import re
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path

from PIL import Image
from app import create_app
from db import backup_data, check_db, connect, init_db, seed_demo


def image_file():
    out=io.BytesIO()
    Image.new('RGB',(80,80),(30,100,55)).save(out,'PNG')
    out.seek(0)
    return out


class ForumJourneys(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)
        self.app=create_app({'TESTING':True,'SECRET_KEY':'test-key','DATABASE_PATH':str(self.path/'forum.db'),'UPLOAD_DIR':str(self.path/'uploads')})
        self.client=self.app.test_client()

    def tearDown(self): self.tmp.cleanup()

    def test_preview_tour_navigation_and_first_step(self):
        self.register()
        home=self.client.get('/').data
        self.assertIn(b'id="start-title"',home)
        for item in (b'home-nav',b'topics-nav',b'create-nav',b'following-nav',b'profile-nav'):
            self.assertIn(b'data-tour-target="'+item+b'"',home)
        self.assertIn(b'aria-label="Main navigation"',home)
        self.assertNotIn(b'class="desktop-nav"',home)
        self.assertIn(b'1 of 5',home)
        self.assertIn(b'data-tour-shade="top"',home)
        profile=self.client.get('/members/alice').data
        self.assertIn(b'class="mobile-account-actions"',profile)
        self.assertIn(b'View tutorial',profile)
        self.assertIn(b'Sign out',profile)
        self.client.post('/topics/stories/follow',data={'csrf':self.token('/topics/stories')})
        self.assertIn(b'1 of 3 complete',self.client.get('/').data)

    def test_database_integrity_and_backup_include_images(self):
        self.register()
        upload_dir=Path(self.app.config['UPLOAD_DIR'])
        (upload_dir/'sample.jpg').write_bytes(b'local-backup-test')
        archive=self.path/'backup.zip'
        self.assertEqual(check_db(self.app.config['DATABASE_PATH']),'ok')
        backup_data(self.app.config['DATABASE_PATH'],upload_dir,archive)
        with zipfile.ZipFile(archive) as saved:
            self.assertIn('forum.sqlite3',saved.namelist())
            self.assertEqual(saved.read('uploads/sample.jpg'),b'local-backup-test')
            (self.path/'snapshot.sqlite3').write_bytes(saved.read('forum.sqlite3'))
        with closing(connect(self.path/'snapshot.sqlite3')) as snapshot:
            self.assertEqual(snapshot.execute('PRAGMA user_version').fetchone()[0],4)
            self.assertEqual(snapshot.execute('SELECT COUNT(*) FROM users').fetchone()[0],1)

    def token(self, path='/'):
        html=self.client.get(path).data.decode()
        return re.search(r'<meta name="csrf-token" content="([^"]+)"',html).group(1)

    def register(self,name='alice'):
        r=self.client.post('/register',data={'csrf':self.token('/register'),'username':name,'password':'this is a strong password','rules':'yes','privacy':'yes'},follow_redirects=True)
        self.assertEqual(r.status_code,200)
        return r

    def test_registration_login_avatar_tutorial(self):
        signed_out=self.client.get('/')
        self.assertEqual(signed_out.status_code,302)
        self.assertIn('/login',signed_out.headers['Location'])
        self.assertIn(b'Welcome back',self.client.get('/login').data)
        registered=self.register()
        self.assertIn(b'data-first-visit="true"',registered.data)
        self.assertIn(b'id="tour-skip-form"',registered.data)
        tour_tag=re.search(rb'<div id="tutorial"[^>]+>',registered.data).group()
        self.assertNotIn(b'hidden',tour_tag)
        self.assertIn(b'data-first-visit="false"',self.client.get('/').data)
        self.assertIn(b'data-first-visit="false"',self.client.get('/topics/stories').data)
        self.assertNotIn(b'PINNED',self.client.get('/').data)
        r=self.client.post('/tutorial/finish',headers={'X-CSRF-Token':self.token(),'Accept':'application/json'})
        self.assertEqual(r.status_code,200)
        self.assertIn(b'data-first-visit="false"',self.client.get('/').data)
        r=self.client.post('/avatar',data={'csrf':self.token('/settings'),'avatar':(image_file(),'face.png')},content_type='multipart/form-data',follow_redirects=True)
        self.assertIn(b'Profile updated',r.data)
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            uid=db.execute("SELECT avatar FROM users WHERE username='alice'").fetchone()['avatar']
        response=self.client.get(f'/media/{uid}')
        self.assertEqual(response.status_code,200)
        response.close()
        self.client.post('/logout',data={'csrf':self.token()})
        bad=self.client.post('/login',data={'csrf':self.token('/login'),'username':'alice','password':'wrong'})
        self.assertIn(b'Invalid username',bad.data)
        good=self.client.post('/login',data={'csrf':self.token('/login'),'username':'alice','password':'this is a strong password'},follow_redirects=True)
        self.assertEqual(good.status_code,200)
        self.assertIn(b'data-first-visit="false"',good.data)

    def test_tutorial_skip_works_without_javascript(self):
        self.register()
        token=self.token('/topics/stories')
        skipped=self.client.post('/tutorial/finish',data={'csrf':token},follow_redirects=True)
        self.assertEqual(skipped.status_code,200)
        self.assertIn(b'data-first-visit="false"',skipped.data)
        replayed=self.client.post('/tutorial/replay',data={'csrf':self.token()},follow_redirects=True)
        self.assertEqual(replayed.status_code,200)
        self.assertIn(b'data-first-visit="true"',replayed.data)

    def test_replay_only_once_and_checklist_dismissal(self):
        self.register()
        replayed=self.client.post('/tutorial/replay',data={'csrf':self.token('/members/alice')},follow_redirects=True)
        self.assertIn(b'data-first-visit="true"',replayed.data)
        self.assertIn(b'data-first-visit="false"',self.client.get('/topics/stories').data)
        self.assertIn(b'0 of 3 complete',self.client.get('/').data)
        dismissed=self.client.post('/onboarding/dismiss',data={'csrf':self.token()},follow_redirects=True)
        self.assertNotIn(b'id="start-title"',dismissed.data)
        self.assertNotIn(b'id="start-title"',self.client.get('/').data)

    def test_checklist_uses_real_activity_and_legacy_accounts_are_not_prompted(self):
        seed_demo(self.app.config['DATABASE_PATH'])
        self.register()
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            post_id=db.execute('SELECT id FROM posts WHERE is_demo=1 LIMIT 1').fetchone()['id']
        self.assertIn(b'0 of 3 complete',self.client.get('/').data)
        csrf=self.token('/topics/stories')
        response=self.client.post('/topics/stories/follow',data={'csrf':csrf},headers={'Accept':'application/json'})
        self.assertTrue(response.json['following'])
        self.assertIn(b'1 of 3 complete',self.client.get('/').data)
        response=self.client.post(f'/posts/{post_id}/save',data={'csrf':csrf},headers={'Accept':'application/json'})
        self.assertTrue(response.json['saved'])
        self.assertIn(b'2 of 3 complete',self.client.get('/').data)
        self.client.post('/settings',data={'csrf':csrf,'bio':'A general introduction.'})
        self.assertIn(b'3 of 3 complete',self.client.get('/').data)
        response=self.client.post(f'/posts/{post_id}/save',data={'csrf':csrf},headers={'Accept':'application/json'})
        self.assertFalse(response.json['saved'])
        self.assertIn(b'2 of 3 complete',self.client.get('/').data)
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            with db:
                db.execute('DELETE FROM user_onboarding')
                db.execute('PRAGMA user_version=1')
        init_db(self.app.config['DATABASE_PATH'])
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM user_onboarding').fetchone()[0],0)
        self.assertNotIn(b'id="start-title"',self.client.get('/').data)

    def test_appearance_settings_persist_and_reject_invalid_choices(self):
        self.register()
        token=self.token('/settings')
        values={'csrf':token,'theme':'dark','font':'serif','text_size':'large','density':'compact','motion':'reduced'}
        response=self.client.post('/settings/appearance',data=values,follow_redirects=True)
        self.assertEqual(response.status_code,200)
        for expected in (b'data-theme="dark"',b'data-font="serif"',b'data-text-size="large"',b'data-density="compact"',b'data-motion="reduced"'):
            self.assertIn(expected,response.data)
            self.assertIn(expected,self.client.get('/topics').data)
        invalid=dict(values,theme='unknown')
        self.assertEqual(self.client.post('/settings/appearance',data=invalid).status_code,400)
        self.assertIn(b'data-theme="dark"',self.client.get('/settings').data)
        self.client.post('/logout',data={'csrf':self.token()})
        self.client.post('/login',data={'csrf':self.token('/login'),'username':'alice','password':'this is a strong password'})
        self.assertIn(b'data-theme="dark"',self.client.get('/').data)
        self.assertIn(b'class="page-home"',self.client.get('/').data)
        self.assertIn(b'class="page-topics"',self.client.get('/topics').data)

    def test_proposed_topics_demo_copy_and_member_follows(self):
        seed_demo(self.app.config['DATABASE_PATH'])
        seed_demo(self.app.config['DATABASE_PATH'])
        self.register('alice')
        topics=self.client.get('/topics')
        self.assertIn(b'Retatrutide',topics.data)
        self.assertIn(b'A topic does not confirm a Louw product',topics.data)
        self.assertIn(b'class="community-grid"',topics.data)
        self.assertIn(b'class="topic-letter-section"',topics.data)
        self.assertIn(b'id="topics-a-g"',topics.data)
        self.assertIn(b'id="topics-h-p"',topics.data)
        self.assertIn(b'id="topics-q-z"',topics.data)
        self.assertLess(topics.data.index(b'id="topics-a-g"'),topics.data.index(b'id="topics-h-p"'))
        self.assertLess(topics.data.index(b'id="topics-h-p"'),topics.data.index(b'id="topics-q-z"'))
        create_page=self.client.get('/create').data
        self.assertIn(b'id="upload-zone"',create_page)
        self.assertIn(b'id="image-fields"',create_page)
        self.assertIn(b'How do you read a peptide study?',self.client.get('/').data)
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            tag=db.execute("SELECT id FROM tags WHERE slug='retatrutide'").fetchone()['id']
            self.assertEqual(db.execute('SELECT COUNT(*) FROM posts WHERE is_demo=1').fetchone()[0],5)
        post=self.client.post('/create',data={'csrf':self.token('/create'),'intent':'publish','type':'question','title':'A peptide discussion question','body':'How do members assess published peptide research?','tags':str(tag)})
        self.assertEqual(post.status_code,302)
        self.client.post('/logout',data={'csrf':self.token()})
        self.register('bob')
        followed=self.client.post('/members/alice/follow',data={'csrf':self.token('/members/alice')},follow_redirects=True)
        self.assertIn(b'1</strong> followers',followed.data)
        self.assertIn(b'Following',followed.data)
        self.assertIn(b'alice',self.client.get('/members/bob/connections?view=following').data)
        self.assertIn(b'bob',self.client.get('/members/alice/connections?view=followers').data)
        self.assertIn(b'A peptide discussion question',self.client.get('/?sort=following').data)
        self.assertEqual(self.client.post('/members/bob/follow',data={'csrf':self.token()} ).status_code,400)
        unfollowed=self.client.post('/members/alice/follow',data={'csrf':self.token('/members/alice')},follow_redirects=True)
        self.assertIn(b'0</strong> followers',unfollowed.data)
        self.assertIn(b'data-first-visit="false"',self.client.get('/topics/stories').data)

    def test_post_images_vote_comment_search_report_moderation(self):
        self.register()
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            tag=db.execute("SELECT id FROM tags WHERE slug='stories'").fetchone()['id']
        data={'csrf':self.token('/create'),'type':'progress','title':'My demonstration progress gallery','body':'This is a demonstration story with no medical outcome claim.','tags':str(tag),'photo_consent':'yes','image_label':['Before','After'],'image_caption':['First demo photo','Second demo photo'],'images':[(image_file(),'a.png'),(image_file(),'b.png')]}
        r=self.client.post('/create',data=data,content_type='multipart/form-data',follow_redirects=True)
        self.assertEqual(r.status_code,200)
        self.assertIn(b'First demo photo',r.data)
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            pid=db.execute('SELECT id FROM posts ORDER BY id DESC LIMIT 1').fetchone()['id']
        self.assertIn(b'My demonstration progress gallery',self.client.get('/search?q=demonstration+progress').data)
        self.assertIn(b'My demonstration progress gallery',self.client.get('/topics/stories').data)
        t=self.token(f'/posts/{pid}')
        def vote(value):
            r=self.client.post(f'/vote/post/{pid}',data={'csrf':t,'value':value},headers={'Accept':'application/json'})
            self.assertEqual(r.status_code,200)
            return r.json
        self.assertEqual(vote('1')['score'],1)
        self.assertEqual(vote('-1')['score'],-1)
        self.assertEqual(vote('-1')['score'],0)
        r=self.client.post(f'/posts/{pid}/comment',data={'csrf':t,'body':'A respectful demonstration comment.'},follow_redirects=True)
        self.assertIn(b'A respectful demonstration comment.',r.data)
        self.assertEqual(self.client.get(f'/posts/{pid}?comments=new').status_code,200)
        report=self.client.post(f'/report/post/{pid}',data={'csrf':t,'reason':'Spam','detail':'Testing moderation'},follow_redirects=True)
        self.assertIn(b'Report #',report.data)
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            rid=db.execute('SELECT id FROM reports ORDER BY id DESC LIMIT 1').fetchone()['id']
            db.execute("UPDATE users SET role='moderator' WHERE username='alice'")
            db.commit()
        queue=self.client.get('/moderation')
        self.assertIn(b'Testing moderation',queue.data)
        action=self.client.post(f'/moderation/{rid}',data={'csrf':self.token('/moderation'),'action':'hide','reason':'Test review'},follow_redirects=True)
        self.assertIn(b'Test review',action.data)
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            self.assertEqual(db.execute('SELECT status FROM posts WHERE id=?',(pid,)).fetchone()['status'],'hidden')
        # Moderator can see and restore the hidden content after a new report.
        self.client.post(f'/report/post/{pid}',data={'csrf':self.token(),'reason':'Other'})
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            rid2=db.execute('SELECT id FROM reports ORDER BY id DESC LIMIT 1').fetchone()['id']
        self.client.post(f'/moderation/{rid2}',data={'csrf':self.token('/moderation'),'action':'restore','reason':'Test restoration'})
        self.assertEqual(self.client.get(f'/posts/{pid}').status_code,200)

    def test_validation_and_csrf(self):
        self.register()
        self.assertEqual(self.client.post('/create',data={'title':'bad'}).status_code,400)
        fake=self.client.post('/avatar',data={'csrf':self.token('/settings'),'avatar':(io.BytesIO(b'not an image'),'fake.png')},content_type='multipart/form-data',follow_redirects=True)
        self.assertIn(b'could not be decoded safely',fake.data)
        self.assertEqual(self.client.get('/moderation').status_code,403)

    def test_private_draft_preview_page_and_notifications(self):
        self.register()
        draft=self.client.post('/create',data={'csrf':self.token('/create'),'intent':'draft','title':'A private idea','body':'Short note'},follow_redirects=True)
        self.assertIn(b'A private idea',draft.data)
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            pid=db.execute("SELECT id FROM posts WHERE status='draft'").fetchone()['id']
            tag=db.execute("SELECT id FROM tags WHERE slug='questions'").fetchone()['id']
        self.assertNotIn(b'A private idea',self.client.get('/').data)
        self.assertIn(b'Publish draft',self.client.get(f'/posts/{pid}/edit').data)
        self.client.post('/logout',data={'csrf':self.token()})
        self.assertEqual(self.client.get(f'/posts/{pid}').status_code,302)
        self.client.post('/login',data={'csrf':self.token('/login'),'username':'alice','password':'this is a strong password'})
        published=self.client.post(f'/posts/{pid}/edit',data={'csrf':self.token(f'/posts/{pid}/edit'),'intent':'publish','type':'question','title':'A published general question','body':'How can I ask a useful general community question?','tags':str(tag)},follow_redirects=True)
        self.assertIn(b'A published general question',published.data)
        self.client.post('/logout',data={'csrf':self.token()})
        self.register('bob')
        self.client.post(f'/posts/{pid}/comment',data={'csrf':self.token(f'/posts/{pid}'),'body':'A test reply for the author.'})
        self.client.post('/logout',data={'csrf':self.token()})
        self.client.post('/login',data={'csrf':self.token('/login'),'username':'alice','password':'this is a strong password'})
        self.assertIn(b'bob commented',self.client.get('/notifications').data)

    def test_remembered_and_browser_only_sessions(self):
        self.register()
        self.client.post('/tutorial/finish',data={'csrf':self.token()})
        self.client.post('/logout',data={'csrf':self.token()})
        remembered=self.client.post('/login',data={'csrf':self.token('/login'),'username':'alice','password':'this is a strong password','remember':'yes'})
        self.assertEqual(remembered.status_code,302)
        self.assertIn('Expires=',remembered.headers['Set-Cookie'])
        home=self.client.get('/')
        self.assertEqual(home.status_code,200)
        self.assertIn(b'data-first-visit="false"',home.data)
        self.client.post('/logout',data={'csrf':self.token()})
        browser_only=self.client.post('/login',data={'csrf':self.token('/login'),'username':'alice','password':'this is a strong password'})
        self.assertEqual(browser_only.status_code,302)
        self.assertNotIn('Expires=',browser_only.headers['Set-Cookie'])

    def test_combined_profile_save_keeps_avatar_and_rejects_bad_image(self):
        self.register()
        r=self.client.post('/settings',data={'csrf':self.token('/settings'),'bio':'A short bio','avatar':(image_file(),'avatar.png')},content_type='multipart/form-data',follow_redirects=True)
        self.assertIn(b'A short bio',r.data)
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            avatar=db.execute("SELECT avatar FROM users WHERE username='alice'").fetchone()['avatar']
        self.assertIn(f'/media/{avatar}'.encode(),self.client.get('/members/alice').data)
        r=self.client.post('/settings',data={'csrf':self.token('/settings'),'bio':'A revised bio'},follow_redirects=True)
        self.assertIn(b'A revised bio',r.data)
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            row=db.execute("SELECT bio,avatar FROM users WHERE username='alice'").fetchone()
            self.assertEqual(row['avatar'],avatar)
            self.assertEqual(row['bio'],'A revised bio')
        bad=self.client.post('/settings',data={'csrf':self.token('/settings'),'bio':'Unsaved bio','avatar':(io.BytesIO(b'bad'),'bad.png')},content_type='multipart/form-data')
        self.assertEqual(bad.status_code,422)
        self.assertIn(b'avatar-error',bad.data)
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            self.assertEqual(db.execute("SELECT bio,avatar FROM users WHERE username='alice'").fetchone()['avatar'],avatar)
            self.assertEqual(db.execute("SELECT bio FROM users WHERE username='alice'").fetchone()['bio'],'A revised bio')

    def test_inline_post_validation_word_limit_and_slur_blocking(self):
        self.app.config['BLOCKED_SLURS']={'testslur'}
        self.register()
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            tag=db.execute("SELECT id FROM tags WHERE slug='stories'").fetchone()['id']
        token=self.token('/create')
        first=self.client.post('/create',data={'csrf':token,'intent':'publish','type':'question','title':'re','body':'This is my latest body text.'})
        self.assertEqual(first.status_code,422)
        self.assertIn(b'Title must be 3',first.data)
        self.assertIn(b'Choose at least one available topic.',first.data)
        second=self.client.post('/create',data={'csrf':token,'intent':'publish','type':'question','title':'retatrutide','body':'This is my latest body text.'})
        self.assertEqual(second.status_code,422)
        self.assertIn(b'value="retatrutide"',second.data)
        self.assertIn(b'This is my latest body text.',second.data)
        self.assertIn(b'<option value="question" selected>',second.data)
        three=self.client.post('/create',data={'csrf':token,'intent':'publish','type':'story','title':'abc','body':'A short general story.','tags':str(tag)})
        self.assertEqual(three.status_code,302)
        over_title=self.client.post('/create',data={'csrf':token,'intent':'publish','type':'story','title':'x'*121,'body':'A short general story.','tags':str(tag)},headers={'Accept':'application/json'})
        self.assertEqual(over_title.status_code,422)
        self.assertIn('title',over_title.json['errors'])
        too_long=self.client.post('/create',data={'csrf':token,'intent':'publish','type':'story','title':'A title','body':'word '*1001,'tags':str(tag)},headers={'Accept':'application/json'})
        self.assertEqual(too_long.status_code,422)
        self.assertIn('body',too_long.json['errors'])
        blocked=self.client.post('/create',data={'csrf':token,'intent':'publish','type':'story','title':'A testslur title','body':'A sufficiently long description.','tags':str(tag)},headers={'Accept':'application/json'})
        self.assertEqual(blocked.status_code,422)
        self.assertIn('title',blocked.json['errors'])
        boundary=self.client.post('/create',data={'csrf':token,'intent':'publish','type':'story','title':'A title','body':'word '*1000,'tags':str(tag)})
        self.assertEqual(boundary.status_code,302)
        allowed=self.client.post('/create',data={'csrf':token,'intent':'publish','type':'story','title':'Rough language','body':'This is shit, but not an identity slur.','tags':str(tag)})
        self.assertEqual(allowed.status_code,302)
        pid=int(allowed.headers['Location'].split('/')[-1])
        edited=self.client.post(f'/posts/{pid}/edit',data={'csrf':token,'intent':'publish','type':'question','title':'retatrutide','body':'An updated question with my latest text.'})
        self.assertEqual(edited.status_code,422)
        self.assertIn(b'value="retatrutide"',edited.data)
        self.assertIn(b'An updated question with my latest text.',edited.data)
        self.assertIn(b'Choose at least one available topic.',edited.data)
        false_positive=self.client.post(f'/posts/{pid}/edit',data={'csrf':token,'intent':'publish','type':'question','title':'retatrutide','body':'This testslurring word is not an exact match.','tags':str(tag)})
        self.assertEqual(false_positive.status_code,302)
        comment=self.client.post(f'/posts/{pid}/comment',data={'csrf':token,'body':'testslur'},follow_redirects=True)
        self.assertEqual(comment.status_code,422)
        self.assertIn(b'Remove identity-based slurs',comment.data)
        with closing(connect(self.app.config['DATABASE_PATH'])) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM comments WHERE post_id=?',(pid,)).fetchone()[0],0)

    def test_password_change_invalidates_other_sessions(self):
        self.register()
        other=self.app.test_client()
        login_token=re.search(r'<meta name="csrf-token" content="([^"]+)"',other.get('/login').data.decode()).group(1)
        signed_in=other.post('/login',data={'csrf':login_token,'username':'alice','password':'this is a strong password'})
        self.assertEqual(signed_in.status_code,302)
        self.assertEqual(other.get('/settings').status_code,200)
        invalid=self.client.post('/settings/password',data={'csrf':self.token('/settings'),'current_password':'wrong','new_password':'a different strong password','confirm_password':'a different strong password'})
        self.assertEqual(invalid.status_code,422)
        changed=self.client.post('/settings/password',data={'csrf':self.token('/settings'),'current_password':'this is a strong password','new_password':'a different strong password','confirm_password':'a different strong password'})
        self.assertEqual(changed.status_code,302)
        self.assertEqual(self.client.get('/settings').status_code,200)
        self.assertIn('/login',other.get('/settings').headers['Location'])
        with closing(connect(self.app.config['DATABASE_PATH'])) as conn:
            row=conn.execute("SELECT password_hash,session_version FROM users WHERE username='alice'").fetchone()
            self.assertTrue(row['password_hash'].startswith('scrypt:'))
            self.assertEqual(row['session_version'],1)

    def test_untrusted_host_injection_redirects_and_persistent_limits(self):
        self.assertEqual(self.client.get('/',headers={'Host':'outside.example'}).status_code,400)
        token=self.token('/login')
        injection=self.client.post('/login',data={'csrf':token,'username':"' OR 1=1 --",'password':'anything'})
        self.assertIn(b'Invalid username or password',injection.data)
        self.register()
        self.assertEqual(self.client.get('/search?q=%25').status_code,200)
        self.assertEqual(self.client.get('/search?q=%27%20OR%201%3D1').status_code,200)
        self.client.post('/logout',data={'csrf':self.token()})
        login=self.client.post('/login?next=https://outside.example/',data={'csrf':self.token('/login'),'username':'alice','password':'this is a strong password'})
        self.assertEqual(login.headers['Location'],'/')
        self.client.post('/logout',data={'csrf':self.token()})
        for attempt in range(8):
            response=self.client.post('/login',data={'csrf':self.token('/login'),'username':'missing','password':'wrong'})
            self.assertEqual(response.status_code,200)
        restarted=create_app({'TESTING':True,'SECRET_KEY':'test-key','DATABASE_PATH':self.app.config['DATABASE_PATH'],'UPLOAD_DIR':self.app.config['UPLOAD_DIR']})
        fresh=restarted.test_client()
        html=fresh.get('/login').data.decode()
        fresh_token=re.search(r'<meta name="csrf-token" content="([^"]+)"',html).group(1)
        self.assertEqual(fresh.post('/login',data={'csrf':fresh_token,'username':'missing','password':'wrong'}).status_code,429)


if __name__=='__main__': unittest.main()
