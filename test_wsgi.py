import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from app import app


class WsgiTests(unittest.TestCase):
    def test_browser_journey_through_flask(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server,'DB',Path(directory)/'test.sqlite3'):
            server.initialize()
            client=app.test_client()
            self.assertEqual(client.get('/').status_code,200)
            self.assertEqual(client.head('/').status_code,200)
            self.assertEqual(client.get('/api/health').json['database'],'sqlite')
            result=client.post('/api/register',json={'name':'WSGI fan','password':'test-password-123'})
            self.assertEqual(result.status_code,200)
            self.assertIsNotNone(client.get('/api/state').json['user'])
            self.assertEqual(client.post('/api/concert-log',json={'artist':'Artist','venue':'Venue','city':'City','date':'2020-01-01'}).status_code,200)
            self.assertEqual(len(client.get('/api/state').json['concert_history']),1)
            with patch.object(server,'hosted',return_value=True):
                result=client.post('/api/feed-post',json={'photo':'data:image/png;base64,YWJj'})
                self.assertEqual(result.status_code,200)
                post=client.get('/api/photo-post/'+result.json['id']).json
                image=client.get(post['photo'])
                self.assertEqual(image.data,b'abc')
                self.assertEqual(image.headers['Cache-Control'],'no-store')
                self.assertEqual(image.headers['Content-Type'],'image/png')
                client.post('/api/privacy',json={'visibility':'private'})
                self.assertEqual(app.test_client().get(post['photo']).status_code,404)
            self.assertEqual(client.get('/api/state').headers['X-Content-Type-Options'],'nosniff')


if __name__=='__main__':
    unittest.main()
