import json
import unittest
from pathlib import Path
from unittest.mock import patch
from back.main import pipeline
from back.keyword import extract_keyword,contains_term
from back.crawler import crawl_post_contents

class SearchScopeTests(unittest.TestCase):
    def test_synonyms_keep_original_and_other_topics(self):
        result=extract_keyword('배영과 행렬',{'수영':['배영','자유형']})
        self.assertIn('행렬',result.split());self.assertIn('배영과',result.split())
        self.assertIn('배영',result.split());self.assertIn('수영',result.split())
    def test_conversational_particles(self):
        self.assertEqual(extract_keyword('공동인증서에 관한 글 알려줘'),'공동인증서')
    def test_short_english_keyword_is_not_inside_another_word(self):
        self.assertFalse(contains_term('daily records','AI'))
        self.assertTrue(contains_term('AI 개발','ai'))
    def test_default_body_collection_has_no_200_post_cutoff(self):
        posts=[dict(title='기록',url=str(i),content='') for i in range(205)]
        with patch('back.crawler._fetch_post_content',side_effect=lambda p,*args:p):
            results=list(crawl_post_contents(posts,'rmt021322'))
        self.assertEqual(max(event['checked'] for event in results),205)
    def test_late_body_match_can_replace_early_matches(self):
        config=json.loads(Path('config.json').read_text())
        items=[dict(title='기록',url=f'https://blog.naver.com/rmt021322/{i}',content='',views=0) for i in range(5)]
        def bodies(posts,*args,**kwargs):
            for index,post in enumerate(posts):
                content='행렬 파이썬' if index==4 else '행렬'
                yield dict(post=dict(post,content=content),error=None,checked=index+1,total=len(posts))
        with patch('back.main.crawl_public_pages',return_value=[dict(posts=items,scanned=5,total=5,page=1)]),patch('back.main.crawl_post_contents',side_effect=bodies):
            final=list(pipeline('행렬 파이썬',config))[-1]
        self.assertEqual(final['body_checked'],5)
        self.assertEqual(final['posts'][0]['url'],items[-1]['url'])
        self.assertEqual(len(final['posts']),3);self.assertTrue(final['body_complete'])

if __name__=='__main__':unittest.main()
