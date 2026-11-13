import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from back.crawler import crawl_public_pages, decode_listing, CollectionIncomplete
from back.main import pipeline
from app import app

class CrawlerTests(unittest.TestCase):
    def setUp(self):
        def bodies(posts, *a, **kw):
            for i, post in enumerate(posts):
                yield dict(post=post,error=None,checked=i+1,total=len(posts))
        mock=patch('back.main.crawl_post_contents',side_effect=bodies)
        mock.start();self.addCleanup(mock.stop)
    def item(self,n):
        return dict(logNo=str(n),title='수영+%EC%97%B0%EC%8A%B5',openType='2')
    def response(self,items,total):
        r=MagicMock(status_code=200)
        r.text=json.dumps(dict(resultCode='S',postList=items,totalCount=str(total)))
        r.content=r.text.encode()
        return r
    def test_pages_include_older_titles_and_deduplicate(self):
        with patch('back.crawler.requests.Session') as factory,patch('time.sleep'):
            session=factory.return_value.__enter__.return_value
            session.get.side_effect=[self.response([self.item(3),self.item(2)],4),self.response([self.item(2),self.item(1)],4)]
            batches=list(crawl_public_pages('rmt021322'))
        self.assertEqual([p['url'].split('/')[-1] for b in batches for p in b['posts']],['3','2','1'])
        self.assertTrue(batches[-1]['complete'])
        self.assertEqual(session.get.call_args_list[1].kwargs['params']['currentPage'],2)
        self.assertEqual(batches[0]['posts'][0]['title'],'수영 연습')
    def test_private_entries_excluded(self):
        item=self.item(1);item['openType']='1'
        posts,total,raw=decode_listing(dict(resultCode='S',postList=[item],totalCount='1'),'rmt021322')
        self.assertEqual(posts,[]);self.assertEqual(raw,1)
    def test_limit_reports_incomplete(self):
        with patch('back.crawler.requests.Session') as factory:
            factory.return_value.__enter__.return_value.get.return_value=self.response([self.item(3)],2)
            iterator=crawl_public_pages('rmt021322',max_pages=1)
            next(iterator)
            with self.assertRaises(CollectionIncomplete):next(iterator)
    def test_partial_result_is_labelled(self):
        config=json.loads(Path('config.json').read_text())
        def interrupted(*args,**kwargs):
            yield dict(posts=[dict(title='수영',url='https://blog.naver.com/rmt021322/1',content='',views=0)],scanned=1,total=3,page=1)
            raise CollectionIncomplete('timeout')
        with patch('back.main.crawl_public_pages',side_effect=interrupted):
            final=list(pipeline('수영',config))[-1]
        self.assertTrue(final['partial']);self.assertTrue(final['warning']);self.assertEqual(len(final['posts']),1)
    def test_live_endpoint_and_total_failure(self):
        from back.sessions import BlogSession
        item=BlogSession('rmt021322');item.status='error';item.message='연결 실패';item.ready.set()
        with patch('app.store.get',return_value=item):
            response=app.test_client().post('/api/search',json={'text':'수영','token':item.token})
            final=json.loads(response.data.decode().splitlines()[-1])
        self.assertEqual(final['stage'],'error');self.assertEqual(final['posts'],[])
    def test_empty_public_blog(self):
        with patch('back.crawler.requests.Session') as factory:
            factory.return_value.__enter__.return_value.get.return_value=self.response([],0)
            self.assertTrue(list(crawl_public_pages('rmt021322'))[-1]['complete'])
    def test_legacy_escaped_apostrophe(self):
        r=self.response([self.item(1)],1)
        r.text=r.text[:-1]+',"pagingHtml":"'+chr(92)+"'"+'"}'
        with patch('back.crawler.requests.Session') as factory:
            factory.return_value.__enter__.return_value.get.return_value=r
            self.assertTrue(list(crawl_public_pages('rmt021322'))[-1]['complete'])
