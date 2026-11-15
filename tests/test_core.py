import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.error import HTTPError
from app.config import Settings
from app.database import Store
from app.providers import canonical_search_params, normalize_imdb, normalize_subtitle, opensubtitles_search, ProviderError
from app.service import Checker


class ProviderTests(unittest.TestCase):
    def test_imdb_format(self):
        self.assertEqual(normalize_imdb('tt0133093'),'133093')
        self.assertEqual(normalize_imdb('000123'), '123')
        self.assertIsNone(normalize_imdb('bad/thing'))

    def test_search_prefers_imdb(self):
        self.assertEqual(canonical_search_params({'imdb_id':'tt0012345', 'title':'Example','year':1945},'sv'),{'imdb_id':'12345','languages':'sv'})

    def test_fallback_title_year(self):
        self.assertEqual(canonical_search_params({'title':'House Of Fear','year':1945},'en'),{'languages':'en','query':'house of fear','year':'1945'})

    def test_provider_results(self):
        example={'data':[{'id':'a','attributes':{'language':'sv','release':'X.BluRay','download_count':8,'files':[{'file_id':9}], 'url':'https://www.opensubtitles.com/en/subtitles/xxx'}}], 'total_count':7}
        with patch('app.providers.request_json',return_value=example) as req:
            got=opensubtitles_search('fake',{'title':'X','imdb_id':'tt0987654'},'sv')
            url=req.call_args.args[0]
            self.assertIn('imdb_id=987654',url)
            self.assertIn('languages=sv',url)
            self.assertEqual(got['count'],7)
            self.assertEqual(got['results'][0]['file_id'],9)
            self.assertEqual(got['method'],'imdb')

    def test_invalid_response_is_error_not_zero(self):
        with patch('app.providers.request_json',return_value={'other': []}):
            with self.assertRaises(ProviderError):
                opensubtitles_search('fake',{'title':'X'},'sv')

    def test_headers_are_set(self):
        with patch('app.providers.request_json',return_value={'data':[]} ) as req:
            opensubtitles_search('k',{'title':'X'},'en')
            self.assertEqual(req.call_args.args[1]['Api-Key'],'k')
            self.assertIn('User-Agent',req.call_args.args[1])

    def test_missing_key_fails_explicitly(self):
        with self.assertRaises(ProviderError):opensubtitles_search('',{'title':'X'},'en')


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.store=Store(str(Path(self.folder.name)/'test.sqlite3'))
        self.movie={'id':42,'title':'Example','year':1945,'imdbId':'tt0012345','monitored':True,'hasFile':False}

    def tearDown(self):self.folder.cleanup()

    def test_sync_and_keep_result(self):
        self.store.sync_movies([self.movie])
        self.assertEqual(len(self.store.all_movies()),1)
        self.store.result(42,{'count':1,'results':[]},{'count':3,'results':[]},'imdb')
        self.store.sync_movies([self.movie])
        self.assertEqual(self.store.one_movie(42)['sv_count'],1)
        self.assertIsNotNone(self.store.one_movie(42)['checked_at'])

    def test_metadata_change_invalidates(self):
        self.store.sync_movies([self.movie])
        self.store.result(42,{'count':1,'results':[]},{'count':0,'results':[]},'imdb')
        self.store.sync_movies([{**self.movie,'imdbId':'tt0009999'}])
        self.assertIsNone(self.store.one_movie(42)['checked_at'])
        self.assertIsNone(self.store.one_movie(42)['sv_count'])

    def test_missing_filter(self):
        self.store.sync_movies([self.movie,{**self.movie,'id':43,'hasFile':True}])
        self.assertEqual([m['id'] for m in self.store.all_movies()], [42])

    def test_remove_deleted_movies(self):
        self.store.sync_movies([self.movie])
        self.store.sync_movies([])
        self.assertEqual(self.store.all_movies(),[])

    def test_provider_error_not_no_subtitles(self):
        self.store.sync_movies([self.movie])
        self.store.error(42,'HTTP 429')
        self.assertIsNone(self.store.one_movie(42)['sv_count'])
        self.assertIsNone(self.store.one_movie(42)['checked_at'])
        self.assertEqual(self.store.one_movie(42)['error'],'HTTP 429')

    def test_checker_local_flow_and_cache(self):
        self.store.sync_movies([self.movie])
        calls=[]
        def search(key,movie,lang):
            calls.append(lang)
            return {'count':2 if lang=='sv' else 1,'results':[{'release':'X'}], 'method':'imdb'}
        config=Settings(radarr_api_key='x',opensubtitles_api_key='k',db_path=self.store.path,request_delay_ms=0,check_releases=False)
        chk=Checker(config,self.store,search=search)
        chk._scan()
        self.assertEqual(calls,['sv','en'])
        self.assertEqual(self.store.one_movie(42)['sv_count'],2)
        chk._scan()
        self.assertEqual(len(calls),2)
        chk._scan(force=True)
        self.assertEqual(len(calls),4)

    def test_checker_does_not_replace_good_result_on_failed_refresh(self):
        self.store.sync_movies([self.movie])
        self.store.result(42,{'count':1,'results':[]},{'count':1,'results':[]},'imdb')
        def fail(key,movie,lang): raise ProviderError('API down')
        chk=Checker(Settings(opensubtitles_api_key='fake',request_delay_ms=0,check_releases=False),self.store,search=fail)
        chk._scan(force=True)
        self.assertEqual(self.store.one_movie(42)['sv_count'],1)
        self.assertEqual(self.store.one_movie(42)['error'],'API down')


if __name__=='__main__':unittest.main()
