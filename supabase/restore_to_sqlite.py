"""One-time copy from private Supabase forum schema back into local SQLite."""
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from db import init_db, check_db
TABLES = ('users','tags','user_onboarding','user_appearance','posts','post_tags',
          'media','comments','votes','reports','moderation_actions','follows',
          'user_follows','saves','notifications','rate_limits')

def restore():
    load_dotenv(ROOT/'.env')
    source_path=ROOT/'instance/forum.sqlite3'
    target_path=ROOT/'instance/forum-return.sqlite3'
    if target_path.exists(): raise RuntimeError('Temporary restore file already exists')
    original=sqlite3.connect(source_path)
    original.row_factory=sqlite3.Row
    cloud=psycopg.connect(os.environ['DATABASE_URL'],connect_timeout=8,
                          sslmode='require',options='-c search_path=forum,public')
    init_db(target_path)
    local=sqlite3.connect(target_path)
    counts={}
    try:
        local.execute('PRAGMA foreign_keys=ON')
        with local:
            # Fresh initialization only inserts the approved topic labels.
            local.execute('DELETE FROM tags')
            for table in TABLES:
                result=cloud.execute('SELECT * FROM '+table)
                columns=[item.name for item in result.description]
                rows=result.fetchall()
                counts[table]=len(rows)
                if not rows: continue
                placeholders=','.join('?' for _ in columns)
                statement='INSERT INTO '+table+' ('+','.join(columns)+') VALUES ('+placeholders+')'
                converted=[]
                for row in rows:
                    converted.append(tuple(value.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                                           if isinstance(value,datetime) else value for value in row))
                local.executemany(statement,converted)
            # Keep a vote present only in the old local copy; cloud values win on conflicts.
            for row in original.execute('SELECT * FROM votes'):
                local.execute('INSERT OR IGNORE INTO votes(user_id,target_type,target_id,value) VALUES(?,?,?,?)',tuple(row))
            for media_id,filename,content in cloud.execute('SELECT m.id,m.filename,b.content FROM media m JOIN media_bytes b ON b.media_id=m.id'):
                if Path(filename).name!=filename or not filename.endswith('.jpg'):
                    raise RuntimeError('Unsafe image filename in remote database')
                image=ROOT/'instance/uploads'/filename
                if image.exists() and image.read_bytes()!=content:
                    raise RuntimeError('Local and remote image bytes disagree')
                if not image.exists(): image.write_bytes(content)
            if local.execute('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('Restored database has broken references')
        if check_db(target_path)!='ok': raise RuntimeError('SQLite integrity check failed')
        for table,expected in counts.items():
            count=local.execute('SELECT count(*) FROM '+table).fetchone()[0]
            if count!=expected+(1 if table=='votes' else 0):
                raise RuntimeError('Table count mismatch: '+table)
    finally:
        original.close(); local.close(); cloud.close()
    print('Prepared verified SQLite copy:',counts,'plus one local-only vote')

if __name__=='__main__': restore()
