import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from back.main import pipeline
from back.parser import parse_post, PostContentUnavailable
from back.crawler import crawl_post_contents, CollectionIncomplete
from back.ranking import rank_posts
from back.search import search_posts
from app import app


def post(number, title='기록', content=''):
    return dict(title=title,url=f'https://blog.naver.com/rmt021322/{number}',content=content,views=0)


def bodies(items):
    for index, item in enumerate(items):
        yield dict(post=item,error=None,checked=index + 1,total=len(items))


class BodySearchTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads(Path('config.json').read_text())
    def run_pipeline(self, items, contents):
        listing=[dict(posts=items,scanned=len(items),total=len(items),page=1)]
        lookup={post['url']:post for post in contents}
        all_contents=[lookup.get(item['url'],item) for item in items]
        with patch('back.main.crawl_public_pages',return_value=listing),patch('back.main.crawl_post_contents',return_value=bodies(all_contents)) as fetch:
            events=list(pipeline('수영',self.config))
        return events,fetch
    def test_title_first_then_content_no_duplicates_and_snippet(self):
        items=[post(1,'수영 강습'),post(2),post(3)]
        content='앞부분 '*100+'수영 호흡을 연습했어요.'+' 뒷부분'*100
        events,fetch=self.run_pipeline(items,[post(2,content=content),post(3,content='수영')])
        result=events[-1]
        self.assertEqual([p['url'].split('/')[-1] for p in result['posts']],['1','2','3'])
        self.assertEqual([p['match_in'] for p in result['posts']],['title','content','content'])
        self.assertIn('수영',result['posts'][1]['content'])
        self.assertLess(len(result['posts'][1]['content']),200)
        self.assertEqual([p['url'] for p in fetch.call_args.args[0]],[item['url'] for item in items])
        self.assertIn('body',[e['stage'] for e in events])
    def test_enough_titles_still_fetch_all_bodies(self):
        events,fetch=self.run_pipeline([post(n,'수영') for n in range(4)],[])
        fetch.assert_called_once()
        self.assertEqual(len(fetch.call_args.args[0]),4)
        self.assertEqual(events[-1]['body_checked'],4)
        self.assertEqual(len(events[-1]['posts']),3)
        self.assertTrue(events[-1]['body_complete'])
    def test_body_search_does_not_stop_at_three_and_closes(self):
        closed=[];read=[]
        def stream(*args,**kwargs):
            try:
                for n in range(1,6):
                    read.append(n)
                    yield dict(post=post(n,'수영' if n==1 else '기록',content='수영'),error=None,checked=n,total=5)
            finally:closed.append(True)
        listing=[dict(posts=[post(1,'수영')]+[post(n) for n in range(2,6)],scanned=5,total=5,page=1)]
        with patch('back.main.crawl_public_pages',return_value=listing),patch('back.main.crawl_post_contents',side_effect=stream):
            final=list(pipeline('수영',self.config))[-1]
        self.assertEqual(read,[1,2,3,4,5]);self.assertTrue(closed)
        self.assertEqual(final['body_checked'],5);self.assertEqual(len(final['posts']),3)
        self.assertTrue(final['body_complete']);self.assertFalse(final['partial'])
    def test_body_failure_preserves_title_results_and_warns(self):
        listing=[dict(posts=[post(1,'수영'),post(2)],scanned=2,total=2,page=1)]
        def failure(*a,**kw):
            yield dict(post=None,error='unreadable',checked=1,total=1)
        with patch('back.main.crawl_public_pages',return_value=listing),patch('back.main.crawl_post_contents',side_effect=failure):
            final=list(pipeline('수영',self.config))[-1]
        self.assertEqual(len(final['posts']),1);self.assertTrue(final['partial']);self.assertTrue(final['warning'])
    def test_body_limit_is_not_reported_as_complete_no_results(self):
        listing=[dict(posts=[post(1)],scanned=1,total=1,page=1)]
        with patch('back.main.crawl_public_pages',return_value=listing),patch('back.main.crawl_post_contents',side_effect=CollectionIncomplete('budget')):
            final=list(pipeline('수영',self.config))[-1]
        self.assertEqual(final['stage'],'empty');self.assertTrue(final['partial'])
    def test_body_hit_endpoint(self):
        from back.sessions import BlogSession
        item=BlogSession('rmt021322');item.posts=[post(1,content='수영 연습')]
        item.checked=1;item.status='ready';item.ready.set()
        with patch('app.store.get',return_value=item):
            response=app.test_client().post('/api/search',json={'text':'수영','token':item.token})
            events=[json.loads(line) for line in response.data.decode().splitlines()]
        self.assertEqual(events[-1]['posts'][0]['match_in'],'content')
        self.assertEqual(events[-1]['body_checked'],1)
        for event in events:
            with app.test_client().get(event['image']) as image:self.assertEqual(image.status_code,200)
    def test_parser_ignores_navigation_comments_and_scripts(self):
        html='<nav>수영</nav><div class="se-main-container"><p>자료구조 연습</p><script>수영</script><style>수영</style></div><aside>수영 댓글</aside>'
        text=parse_post(html)
        self.assertEqual(text,'자료구조 연습')
        self.assertFalse(search_posts([post(1,content=text)],'수영',field='content'))
    def test_legacy_and_login_page(self):
        self.assertEqual(parse_post('<div id="postViewArea"><p>옛 글의 본문</p></div>'),'옛 글의 본문')
        with self.assertRaises(PostContentUnavailable):parse_post('<html>로그인 후 수영 글을 보세요.</html>')
    def test_title_match_always_outranks_body_frequency(self):
        items=[dict(post(1,content='수영 '*100),match_in='content'),dict(post(2,'수영'),match_in='title')]
        self.assertEqual(rank_posts(items,'수영')[0]['url'],items[1]['url'])
    def test_streaming_body_fetch_and_restricted_article(self):
        with patch('back.crawler.requests.Session') as factory,patch('time.sleep'):
            session=factory.return_value.__enter__.return_value
            response=session.get.return_value.__enter__.return_value
            response.status_code=200
            response.iter_content.return_value=[b'<div class="se-main-container">hello swimming</div>']
            result=list(crawl_post_contents([post(1)],'rmt021322'))[0]
            self.assertEqual(result['post']['content'],'hello swimming')
            self.assertTrue(session.get.call_args.kwargs['stream'])
            response.iter_content.return_value=[b'<html>login</html>']
            failure=list(crawl_post_contents([post(1)],'rmt021322'))[0]
            self.assertIsNone(failure['post']);self.assertTrue(failure['error'])
    def test_body_budget(self):
        with patch('back.crawler._fetch_post_content',side_effect=lambda item,*a:item):
            with self.assertRaises(CollectionIncomplete):list(crawl_post_contents([post(1),post(2)],'rmt021322',max_posts=1))

if __name__=='__main__':unittest.main()
