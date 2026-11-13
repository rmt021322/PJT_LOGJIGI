import json
import threading
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from app import app
from back.sessions import BlogSession,SessionStore,normalize_blog_id
from back.insights import summarize
from back.relevance import recommend
from back.web_search import search_recent_web,parse_news_xml,parse_google_html,safe_link


def post(n,title='학은제 수강신청',body='학은제 수강신청 절차를 정리했습니다.',views=None,order=0):
    return dict(title=title,url=f'https://blog.naver.com/testblog/{n}',content=body,views=views,published_at='2026. 11. 10.',source_order=order)


def session(posts=None):
    item=BlogSession('testblog');item.posts=posts if posts is not None else [post(1)]
    item.checked=len(item.posts);item.status='ready';item.list_complete=True;item.ready.set();item.insights=summarize(item.posts)
    return item


class AppWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.client=app.test_client();self.item=session()
        self.mock=patch('app.store.get',side_effect=lambda token:self.item if token==self.item.token else None)
        self.mock.start();self.addCleanup(self.mock.stop)
    def search(self,text):
        response=self.client.post('/api/search',json={'text':text,'token':self.item.token})
        self.assertEqual(response.status_code,200)
        return [json.loads(line) for line in response.data.decode().splitlines()]
    def test_chat_uses_selected_blog_and_verifies_results(self):
        self.item.posts=[post(1),post(2,'후쿠오카 여행','여행 일정과 맛집을 기록합니다. '*100+'학은제 이야기는 다음에.')]
        events=self.search('학은제')
        self.assertEqual(len(events[-1]['posts']),1)
        self.assertIn('/testblog/1',events[-1]['posts'][0]['url'])
        for event in events:
            with self.client.get(event['image']) as asset:self.assertEqual(asset.status_code,200)
    def test_no_forced_three_and_no_results(self):
        self.assertEqual(len(self.search('학은제')[-1]['posts']),1)
        self.assertEqual(self.search('없음키워드')[-1]['posts'],[])
    def test_form_and_navigation_views(self):
        page=self.client.get('/').data.decode()
        for name in ['connectForm','blogForm','webForm','insightPanel','choiceView']:
            self.assertIn(f'id="{name}"',page)
        self.assertNotIn('example_blogID',page)
    def test_validation_and_expiry(self):
        self.assertEqual(self.client.post('/api/search',json={'text':'학은제'}).status_code,404)
        self.assertEqual(self.client.post('/api/search',json={'text':' ','token':self.item.token}).status_code,400)
        self.assertEqual(self.client.post('/api/search',json={'text':'x'*201,'token':self.item.token}).status_code,400)
        self.assertEqual(self.client.get('/api/blogs/missing').status_code,404)
    def test_web_preparation_does_not_wait_or_make_external_requests(self):
        self.item.ready.clear();self.item.status='loading'
        with patch('requests.get') as fetch:
            response=self.client.post('/api/web-search',json={'text':'게임 업데이트','token':self.item.token})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['status'],'preparing')
        self.assertEqual(response.json['posts'],[]);fetch.assert_not_called()
    def test_search_does_not_fetch_blog_again(self):
        with patch('back.sessions.crawl_public_pages') as listing,patch('back.sessions.crawl_post_contents') as bodies:
            self.search('학은제');self.search('수강신청');self.client.get('/api/blogs/'+self.item.token)
        listing.assert_not_called();bodies.assert_not_called()
    def test_invalid_blog_id(self):
        for value in ['https://example.com/blog','a/b','<script>',None]:
            self.assertEqual(self.client.post('/api/blogs',json={'blog_id':value}).status_code,400)


class SessionsAndInsightsTests(unittest.TestCase):
    def test_id_or_url(self):
        self.assertEqual(normalize_blog_id(' https://blog.naver.com/licoralke/123 '),'licoralke')
        self.assertEqual(normalize_blog_id('https://blog.naver.com/PostView.naver?blogId=testblog&logNo=1'),'testblog')
        self.assertEqual(normalize_blog_id('rmt021322'),'rmt021322')
    def test_background_start_and_isolation(self):
        release=threading.Event()
        manager=SessionStore(lambda:{})
        def loading(item):release.wait(2);item.ready.set()
        try:
            with patch.object(manager,'_load',side_effect=loading):
                first=manager.create('one');second=manager.create('two')
            self.assertFalse(first.ready.is_set());self.assertNotEqual(first.token,second.token)
            first.posts=[post(1,'첫번째 블로그')]
            self.assertEqual(second.snapshot()['total'],0)
            manager.delete(first.token)
            self.assertTrue(first.cancel.is_set());self.assertIsNone(manager.get(first.token))
            self.assertEqual(manager.get(second.token).blog_id,'two')
        finally:release.set()
    def test_expired_session_cancelled(self):
        manager=SessionStore(lambda:{},ttl=1);item=BlogSession('testblog');item.touched-=2;manager.items[item.token]=item
        self.assertIsNone(manager.get(item.token));self.assertTrue(item.cancel.is_set())
        self.assertIsNone(manager.get([]))
    def test_loader_reads_all_and_reuses_recent_insights(self):
        manager=SessionStore(lambda:{'insight_recent_posts':2});item=BlogSession('testblog')
        posts=[post(i,'게임 업데이트',body='',order=i) for i in range(5)]
        def bodies(items,*a,**kw):
            for index,p in enumerate(items):yield dict(post=dict(p,content='게임 업데이트 공략'),error=None,checked=index+1,total=5)
        with patch('back.sessions.crawl_public_pages',return_value=[dict(posts=posts,complete=True)]),patch('back.sessions.crawl_post_contents',side_effect=bodies):
            manager._load(item)
        data=item.snapshot();self.assertEqual(data['checked'],5);self.assertEqual(data['status'],'ready')
        self.assertEqual(data['insights']['analyzed_posts'],2);self.assertEqual(data['insights']['body_read'],2)
    def test_public_popularity_not_invented(self):
        data=summarize([post(1),post(2)])
        self.assertFalse(data['popular_available']);self.assertFalse(data['search_terms_available'])
        self.assertEqual(data['popular_posts'],[])
        measured=summarize([post(1,views=3),post(2,views=10)])
        self.assertEqual(measured['popular_posts'][0]['views'],10)
    def test_recent_keyword_scope(self):
        data=summarize([post(1,'게임 공략',order=0),post(2,'게임 업데이트',order=1),post(3,'오래된 여행',body='옛날주제',order=2)],2)
        keywords=[x['keyword'] for x in data['keywords']]
        self.assertIn('게임',keywords);self.assertNotIn('옛날주제',keywords)
        self.assertEqual(next(x['post_count'] for x in data['keywords'] if x['keyword']=='게임'),2)
    def test_relevance_requires_all_query_topics(self):
        self.assertEqual(recommend([post(1,'학은제','학은제 시작')],'학은제 수강신청'),[])
        self.assertEqual(len(recommend([post(1)],'학은제 수강신청')),1)


class WebSearchTests(unittest.TestCase):
    def setUp(self):self.now=datetime(2026,11,12,0,0,tzinfo=timezone.utc)
    def feed(self):
        from email.utils import format_datetime
        parts=[]
        for n,days in [(1,1),(2,8),(3,-1)]:
            parts.append(f'<item><title>게임 소식 {n}</title><link>https://news.google.com/articles/{n}</link><pubDate>{format_datetime(self.now-timedelta(days=days))}</pubDate><source>뉴스사</source></item>')
        return ('<rss><channel>'+''.join(parts)+'</channel></rss>').encode()
    def test_news_excludes_old_and_future_dates(self):
        results=parse_news_xml(self.feed(),self.now)
        self.assertEqual(len(results),1);self.assertTrue(results[0]['date_verified'])
    def test_google_blocked_news_is_labelled_fallback(self):
        with patch('back.web_search.serpapi_search',return_value=None),patch('back.web_search.get_bytes',side_effect=[ValueError('429'),self.feed()]):
            result=search_recent_web('게임 업데이트',self.now)
        self.assertEqual(result['provider'],'google_news');self.assertTrue(result['warning'])
        self.assertEqual(len(result['posts']),1);self.assertIn('qdr%3Aw',result['google_url'])
    def test_unavailable_has_link_without_fake_results(self):
        with patch('back.web_search.serpapi_search',return_value=None),patch('back.web_search.get_bytes',side_effect=ValueError('offline')):
            result=search_recent_web('게임',self.now)
        self.assertEqual(result['posts'],[]);self.assertEqual(result['provider'],'unavailable');self.assertTrue(result['google_url'])
    def test_google_html_results_are_not_date_verified(self):
        html='<div><a href="https://example.com/article"><h3>게임 업데이트</h3></a><p>새 소식</p></div>'
        result=parse_google_html(html)[0]
        self.assertFalse(result['date_verified']);self.assertEqual(result['url'],'https://example.com/article')
    def test_unsafe_links_excluded(self):
        for link in ['javascript:alert(1)','http://127.0.0.1/a','http://localhost/a','https://user:pass@example.com/a']:
            self.assertIsNone(safe_link(link))

if __name__=='__main__':unittest.main()
