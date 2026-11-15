import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.matching import score_pair, compare_releases
from app.providers import radarr_releases, ProviderError
from app.database import Store
from app.service import Checker
from app.config import Settings

A = 'The.House.Of.Fear.1945.1080p.BluRay.x264-GROUP'
B = 'The.House.Of.Fear.1945.2160p.WEB-DL.x265-GROUP'
C = 'The.House.Of.Fear.1945.1080p.BluRay.x264-OTHER'


class MatchTests(unittest.TestCase):
    def test_exact_names_and_extension(self):
        self.assertEqual(score_pair(A, A+'.srt')['status'], 'exact')

    def test_disallow_source_and_resolution_mismatch(self):
        self.assertEqual(score_pair(A, B)['status'], 'none')
        self.assertEqual(score_pair(A, A.replace('BluRay','WEB-DL'))['status'], 'none')
        self.assertEqual(score_pair(A, A.replace('1080p','720p'))['status'], 'none')

    def test_disallow_different_edition(self):
        self.assertEqual(score_pair(A+'.Extended', A)['status'], 'none')

    def test_conflicting_group_does_not_get_probable(self):
        self.assertNotEqual(score_pair(A,C)['status'], 'probable')

    def test_exact_match_and_rejected_dont_count(self):
        releases=[{'title':A,'rejected':False}, {'title':B,'rejected':False}, {'title':C,'rejected':True}]
        subs={'sv':[{'release':A+'.srt','subtitle_id':'abc'}], 'en':[{'release':B+'.srt'}]}
        result=compare_releases(releases,subs)
        self.assertEqual(result['sv_candidates'],1)
        self.assertEqual(result['en_candidates'],1)
        self.assertEqual(result['releases'][0]['matches']['sv']['status'],'exact')

    def test_no_false_positive_from_same_film_title_alone(self):
        self.assertEqual(score_pair('The.House.Of.Fear.1945.1080p.BluRay-GROUP',
                                    'The.House.Of.Fear.1945.720p.WEBRip-OTHER')['status'],'none')

    def test_radarr_releases_read_only_and_sanitized(self):
        fake=[{'title':A,'quality':{'quality':{'name':'Bluray-1080p'}},
               'rejections':['Custom format rejected'],'rejected':True,'downloadUrl':'SECRET',
               'size':1234567,'indexer':'Provider','guid':'SECRET'}]
        with patch('app.providers.request_json',return_value=fake) as req:
            got=radarr_releases('http://radarr:7878','key',42)
        self.assertIn('movieId=42',req.call_args.args[0])
        self.assertNotIn('downloadUrl',str(got))
        self.assertNotIn('guid',str(got))
        self.assertEqual(got['releases'][0]['quality'],'Bluray-1080p')
        self.assertEqual(got['count'],1)

    def test_radarr_release_invalid_movieid(self):
        with self.assertRaises(ProviderError):radarr_releases('http://radarr','x',-1)


class CacheAndMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=str(Path(self.temp.name)/'db.sqlite3')
        self.store=Store(self.db)
        self.movie={'id':42,'title':'The House of Fear','year':1945,'imdbId':'tt0000123','hasFile':False}
        self.store.sync_movies([self.movie])

    def tearDown(self):self.temp.cleanup()

    def test_release_first_then_subtitles(self):
        self.store.releases_result(42,{'count':1,'releases':[{'title':A,'rejected':False}]})
        self.store.result(42,{'count':1,'results':[{'release':A+'.srt'}], 'method':'imdb'},
                             {'count':0,'results':[]},'imdb')
        got=self.store.one_movie(42)
        self.assertEqual(got['release_matches']['sv_candidates'],1)
        self.assertEqual(got['release_matches']['releases'][0]['matches']['sv']['status'],'exact')

    def test_subtitles_first_then_releases(self):
        self.store.result(42,{'count':1,'results':[{'release':A+'.srt'}], 'method':'imdb'},
                             {'count':0,'results':[]},'imdb')
        self.store.releases_result(42,{'count':1,'releases':[{'title':A,'rejected':False}]})
        self.assertEqual(self.store.one_movie(42)['release_matches']['sv_candidates'],1)

    def test_release_error_preserves_known_good(self):
        self.store.releases_result(42,{'count':1,'releases':[{'title':A,'rejected':False}]})
        self.store.releases_error(42,'timeout')
        got=self.store.one_movie(42)
        self.assertEqual(got['release_count'],1)
        self.assertEqual(got['release_error'],'timeout')

    def test_metadata_change_resets_release_match(self):
        self.store.releases_result(42,{'count':1,'releases':[{'title':A,'rejected':False}]})
        self.store.sync_movies([{**self.movie,'imdbId':'tt1234567'}])
        got=self.store.one_movie(42)
        self.assertIsNone(got['release_checked_at'])
        self.assertEqual(got['release_matches'],{})

    def test_migration_from_v1_legacy_database(self):
        path=str(Path(self.temp.name)/'old.sqlite3')
        conn=sqlite3.connect(path)
        conn.execute('''CREATE TABLE movies (id INTEGER PRIMARY KEY, title TEXT NOT NULL,
          year INTEGER, imdb_id TEXT, monitored INTEGER, has_file INTEGER,
          radarr_synced_at TEXT, checked_at TEXT, sv_count INTEGER,
          en_count INTEGER, match_method TEXT, results_json TEXT, error TEXT)''')
        conn.execute("INSERT INTO movies (id,title,has_file) VALUES(123,'Old movie',0)")
        conn.commit();conn.close()
        store=Store(path)
        self.assertEqual(store.one_movie(123)['title'],'Old movie')
        store.releases_result(123,{'count':0,'releases':[]})
        self.assertIsNotNone(store.one_movie(123)['release_checked_at'])

    def test_pipeline_and_cache_without_network(self):
        calls={'subs':0,'releases':0}
        def sub(key,movie,language):
            calls['subs']+=1
            return {'count':1 if language=='sv' else 0,'results':[{'release':A+'.srt'}] if language=='sv' else [],'method':'imdb'}
        def releases(url,key,id):
            calls['releases']+=1
            return {'count':2,'releases':[{'title':A,'rejected':False},{'title':B,'rejected':False}]}
        config=Settings(opensubtitles_api_key='test',radarr_api_key='test',db_path=self.db,
                        request_delay_ms=0,check_releases=True)
        check=Checker(config,self.store,search=sub,releases=releases)
        check._scan()
        self.assertEqual(calls,{'subs':2,'releases':1})
        self.assertEqual(self.store.one_movie(42)['release_matches']['sv_candidates'],1)
        check._scan()
        self.assertEqual(calls,{'subs':2,'releases':1})
        check._scan(force=True)
        self.assertEqual(calls,{'subs':4,'releases':2})

    def test_bulk_release_search_cap_and_single_movie_override(self):
        self.store.sync_movies([self.movie, {**self.movie, 'id':43,'title':'Another movie'}])
        calls=[]
        def release(url,key,id):
            calls.append(id)
            return {'count':0,'releases':[]}
        def sub(key,movie,lang):return {'count':0,'results':[],'method':'imdb'}
        config=Settings(opensubtitles_api_key='key',radarr_api_key='key',
                        max_release_searches=1,check_releases=True,request_delay_ms=0)
        c=Checker(config,self.store,search=sub,releases=release)
        c._scan()
        self.assertEqual(len(calls),1)
        c._scan()
        self.assertEqual(len(calls),2)
        self.assertCountEqual(calls,[42,43])
        c._scan(movie_id=42,force=True)
        self.assertEqual(len(calls),3)


if __name__ == '__main__':unittest.main()
