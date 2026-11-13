import unittest
from back.insights import _noun_terms, interest_keywords, summarize


def post(index,title,content=''):
    return dict(title=title,content=content,url=f'https://blog.naver.com/testblog/{index}',views=None,source_order=index)


class InterestTagsTests(unittest.TestCase):
    def test_particles_are_excluded_without_truncating_nouns(self):
        terms=_noun_terms('게임에서는 공략을 읽어요. 사과와 고양이는 어린이에게 좋은 친구예요.')
        for word in ('게임','공략','사과','고양이','어린이'):
            self.assertIn(word,terms)
        for word in ('에서는','을','와','는','에게','게임에서는','공략을','고양이는'):
            self.assertNotIn(word,terms)
    def test_particle_variants_share_one_tag_and_document_count(self):
        tags=interest_keywords([post(0,'게임에서는 공략을 봅니다.'),post(1,'게임으로 공략은 즐거워요.')])
        game=[item for item in tags if item['keyword']=='게임']
        self.assertEqual(len(game),1)
        self.assertEqual(game[0]['post_count'],2)
    def test_limit_is_five_even_if_caller_requests_more(self):
        titles=['게임 공략','여행 일정','수영 연습','파이썬 개발','인공지능 학습','자료구조 알고리즘','음악 감상','뜨개 인형']
        posts=[post(i,title,title) for i,title in enumerate(titles)]
        self.assertEqual(len(interest_keywords(posts,limit=20)),5)
        self.assertLessEqual(len(summarize(posts)['keywords']),5)
    def test_newly_read_bodies_update_the_tags(self):
        posts=[post(0,'첫 번째 기록'),post(1,'두 번째 기록')]
        before={item['keyword'] for item in interest_keywords(posts)}
        for item in posts:item['content']='자료구조를 배우며 자료구조의 원리를 정리합니다.'
        after={item['keyword'] for item in interest_keywords(posts)}
        self.assertNotIn('자료구조',before)
        self.assertIn('자료구조',after)
    def test_empty_and_smaller_requested_limit(self):
        self.assertEqual(interest_keywords([]),[])
        self.assertEqual(interest_keywords([post(0,'게임 공략')],0),[])
        self.assertLessEqual(len(interest_keywords([post(0,'게임 공략')],1)),1)
    def test_app_brand(self):
        from app import app
        html=app.test_client().get('/').data.decode()
        self.assertIn('LOGJIGI',html)
        self.assertNotIn('WithLog',html)

if __name__=='__main__':unittest.main()
