import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen, Request
from app.config import Settings
from app.database import Store
from app.service import Checker
from app.server import make_handler


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(str(Path(self.tmp.name)/'db.sqlite3'))
        self.config=Settings(radarr_api_key='secret-radarr',opensubtitles_api_key='secret-os',db_path=self.store.path)
        self.checker=Checker(self.config,self.store,radarr=lambda *x:[{'id':1,'title':'Film A','hasFile':False}],search=lambda *x:{'count':1,'results':[], 'method':'imdb'})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.config,self.store,self.checker))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.host=f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def get(self,path):
        with urlopen(self.host+path,timeout=5) as r:return r.read().decode('utf8')

    def post(self,path,data={},headers=None):
        req=Request(self.host+path,json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Requested-With':'SubtitleChecker',**(headers or {})})
        with urlopen(req,timeout=5) as r:return r.status,json.load(r)

    def test_health_and_static(self):
        self.assertTrue(json.loads(self.get('/health'))['ok'])
        self.assertIn('Kontrollera svensk text',self.get('/'))
        self.assertIn('async function refresh()',self.get('/app.js'))

    def test_no_secrets_exposed(self):
        txt=self.get('/api/status')+self.get('/api/movies')
        self.assertNotIn('secret-radarr',txt)
        self.assertNotIn('secret-os',txt)

    def test_sync(self):
        code,data=self.post('/api/sync')
        self.assertEqual(code,202)
        self.thread.join(timeout=0.001) if False else None
        import time
        for _ in range(100):
            if not self.checker.state()['running']:break
            time.sleep(0.005)
        self.assertEqual(self.store.one_movie(1)['title'],'Film A')

    def test_cross_site_and_plain_post_rejected(self):
        with self.assertRaises(HTTPError) as err:
            self.post('/api/sync',{},headers={'Origin':'http://evil.example'})
        self.assertEqual(err.exception.code,403)
        req=Request(self.host+'/api/sync',b'{}',headers={'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as err:
            urlopen(req,timeout=5)
        self.assertEqual(err.exception.code,403)

if __name__=='__main__':unittest.main()
