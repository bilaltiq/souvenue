"""Regression coverage for the deployment boundaries (no external services)."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from database import postgres_sql, Row, row_factory
from test_app import Response


class DeploymentTests(unittest.TestCase):
    def test_page_navigation_without_public_files_in_function_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'templates').mkdir()
            shell = (server.ROOT/'templates'/'index.html').read_bytes()
            (root/'templates'/'index.html').write_bytes(shell)
            with patch.object(server, 'ROOT', root), patch.object(server, 'hosted', return_value=True):
                for path in ('/', '/artists', '/artist/olivia-rodrigo', '/event/example', '/feed', '/friends', '/communities', '/community/example', '/leaderboards', '/profile', '/log', '/concerts'):
                    with self.subTest(path=path):
                        response = Response('GET', path)
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers['Content-Type'], 'text/html')
                        self.assertEqual(response.data, shell)
                self.assertEqual(Response('GET', '/studio').status, 404)

    def test_sql_translation_preserves_literals_and_parameters(self):
        query = "SELECT user,created FROM posts WHERE user=? AND body='user? REAL' ORDER BY name COLLATE NOCASE"
        self.assertEqual(postgres_sql(query), 'SELECT "user",created FROM posts WHERE "user"=%s AND body=\'user? REAL\' ORDER BY LOWER(name)')
        self.assertIn('DOUBLE PRECISION', postgres_sql('CREATE TABLE example(created REAL)'))
        self.assertIn('ON CONFLICT DO NOTHING', postgres_sql('INSERT OR IGNORE INTO attendance(user,event) VALUES(?,?)'))
        self.assertIn("metadata::jsonb->>'source'", postgres_sql("SELECT json_extract(metadata,'$.source') FROM events"))
        self.assertEqual(Row({'id': 'a', 'name': 'b'})[1], 'b')
        self.assertEqual(row_factory(type('Cursor', (), {'description': None})())([]), {})

    def test_vercel_never_uses_ephemeral_sqlite(self):
        with patch.dict(os.environ, {'VERCEL': '1', 'DATABASE_URL': ''}):
            with self.assertRaisesRegex(RuntimeError, 'DATABASE_URL'):
                server.db()

    def test_https_sessions_origins_and_demo_controls(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server, 'DB', Path(directory)/'test.sqlite3'):
            server.initialize()
            with patch.object(server, 'hosted', return_value=True):
                self.assertFalse(server.demo_checkins_enabled())
                result = Response('POST', '/api/register', {'name':'Beta fan','password':'test-password-123'})
                cookie = result.headers['Set-Cookie'].split(';')[0]
                self.assertIn('; Secure', result.headers['Set-Cookie'])
                self.assertEqual(Response('POST','/api/checkin',{'event':'noah-kahan'},cookie).status,403)
                self.assertEqual(Response('POST','/api/event',{'id':'noah-kahan'},cookie).status,403)
                self.assertEqual(Response('GET','/studio').status,404)
                handler = object.__new__(server.Handler)
                handler.path='/api/privacy'; raw=json.dumps({'visibility':'private'}).encode()
                handler.headers={'Host':'souvenue.test','Origin':'https://souvenue.test','Cookie':cookie,'Content-Length':str(len(raw))}
                handler.rfile=io.BytesIO(raw);handler.wfile=io.BytesIO()
                status=[];handler.send_response=status.append;handler.send_header=lambda *args:None;handler.end_headers=lambda:None
                handler.do_POST();self.assertEqual(status,[200])
                handler.headers['Origin']='https://evil.test';status.clear();handler.do_POST();self.assertEqual(status,[403])

    def test_hosted_media_respects_private_profiles(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server, 'DB', Path(directory)/'test.sqlite3'):
            server.initialize()
            result=Response('POST','/api/register',{'name':'Photo owner','password':'test-password-123'})
            cookie=result.headers['Set-Cookie'].split(';')[0]
            pid=Response('POST','/api/feed-post',{'photo':'data:image/png;base64,YWJj'},cookie).data['id']
            with patch.object(server,'hosted',return_value=True):
                post=Response('GET','/api/photo-post/'+pid).data
                self.assertEqual(post['photo'],'/api/media/feed/'+pid+'/0')
                self.assertNotIn('data:image',json.dumps(post))
                Response('POST','/api/privacy',{'visibility':'private'},cookie)
                self.assertEqual(Response('GET','/api/media/feed/'+pid+'/0').status,404)


if __name__=='__main__':
    unittest.main()
