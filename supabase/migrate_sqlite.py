"""One-time, all-or-nothing transfer of the local forum into private Supabase Postgres.

Run only after a verified SQLite+uploads backup. The target must be empty.
No passwords, image bytes, or member data are written to logs.
"""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    'users', 'tags', 'user_onboarding', 'user_appearance', 'posts', 'post_tags',
    'media', 'comments', 'votes', 'reports', 'moderation_actions', 'follows',
    'user_follows', 'saves', 'notifications', 'rate_limits',
)
TIMESTAMP_COLUMNS = {'created_at', 'updated_at', 'read_at', 'dismissed_at'}
IDENTITY_TABLES = {'users', 'tags', 'posts', 'media', 'comments', 'reports',
                   'moderation_actions', 'notifications'}


def migrate():
    load_dotenv(ROOT / '.env')
    source_path = ROOT / 'instance' / 'forum.sqlite3'
    source = sqlite3.connect(f'file:{source_path.as_posix()}?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    target = psycopg.connect(os.environ['DATABASE_URL'], autocommit=True,
                             connect_timeout=8, sslmode='require',
                             options='-c search_path=forum,public')
    counts = {}
    try:
        with target.transaction():
            with target.cursor() as cursor:
                for table in TABLES:
                    cursor.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table)))
                    if cursor.fetchone()[0]:
                        raise RuntimeError('Target forum is not empty; migration stopped.')
                cursor.execute('SELECT count(*) FROM media_bytes')
                if cursor.fetchone()[0]:
                    raise RuntimeError('Target images are not empty; migration stopped.')

                for table in TABLES:
                    rows = source.execute(f'SELECT * FROM {table}').fetchall()
                    counts[table] = len(rows)
                    if not rows:
                        continue
                    columns = rows[0].keys()
                    statement = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                        sql.Identifier(table),
                        sql.SQL(',').join(map(sql.Identifier, columns)),
                        sql.SQL(',').join(sql.Placeholder() for _ in columns),
                    )
                    prepared = []
                    for row in rows:
                        values = []
                        for column in columns:
                            value = row[column]
                            if value is not None and column in TIMESTAMP_COLUMNS:
                                value = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
                            values.append(value)
                        prepared.append(values)
                    cursor.executemany(statement, prepared)

                for row in source.execute('SELECT id,filename FROM media'):
                    image = ROOT / 'instance' / 'uploads' / row['filename']
                    if not image.is_file():
                        raise RuntimeError('A referenced image is missing; migration rolled back.')
                    cursor.execute('INSERT INTO media_bytes(media_id,content) VALUES(%s,%s)',
                                   (row['id'], image.read_bytes()))
                counts['media_bytes'] = counts['media']

                for table in IDENTITY_TABLES:
                    cursor.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s,'id'), COALESCE(MAX(id),1), MAX(id) IS NOT NULL) FROM {}").format(sql.Identifier(table)),
                                   (f'forum.{table}',))

                for table, expected in counts.items():
                    cursor.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table)))
                    if cursor.fetchone()[0] != expected:
                        raise RuntimeError('Transfer count mismatch; migration rolled back.')
    finally:
        target.close()
        source.close()
    print('Migrated and verified table counts:', counts)


if __name__ == '__main__':
    migrate()
