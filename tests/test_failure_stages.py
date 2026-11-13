"""Reproduce collection vs keyword failures locally without contacting a blog."""
import threading
import unittest
from unittest.mock import patch
import requests
from back.sessions import BlogSession,SessionStore
from back.insights import summarize as real_summarize


def posts():
    return [dict(title='자료구조 공부',url='https://blog.naver.com/testblog/1',content='',views=None)]


def bodies(items,*args,**kwargs):
    for index,item in enumerate(items):
        yield dict(post=dict(item,content='자료구조를 공부합니다.'),error=None,checked=index+1,total=len(items))


class FailureStageTests(unittest.TestCase):
    def test_keyword_dependency_failure_does_not_hide_the_list(self):
        item=BlogSession('testblog');manager=SessionStore(lambda:{})
        def missing_model(items,recent_limit=12,include_keywords=True):
            if items and include_keywords:raise ModuleNotFoundError('No module named kiwipiepy')
            return real_summarize(items,recent_limit,include_keywords=False)
        with patch('back.sessions.crawl_public_pages',return_value=[dict(posts=posts(),complete=True)]),patch('back.sessions.crawl_post_contents',side_effect=bodies),patch('back.sessions.summarize',side_effect=missing_model),self.assertLogs(level='ERROR'):
            manager._load(item)
        status=item.snapshot()
        self.assertEqual(status['status'],'partial')
        self.assertEqual(status['keyword_error'],'KEYWORD_DEPENDENCY')
        self.assertEqual(status['total'],1);self.assertEqual(status['checked'],1)
        self.assertEqual(len(status['insights']['recent_posts']),1)
        self.assertIsNone(status['error_code']);self.assertTrue(item.ready.is_set())
    def test_listing_timeout_has_its_own_error_code(self):
        item=BlogSession('testblog');manager=SessionStore(lambda:{})
        with patch('back.sessions.crawl_public_pages',side_effect=requests.Timeout()),patch('back.sessions.crawl_post_contents') as fetch,self.assertLogs(level='ERROR'):
            manager._load(item)
        status=item.snapshot();self.assertEqual(status['error_code'],'LIST_TIMEOUT')
        self.assertEqual(status['phase'],'error');self.assertEqual(status['status'],'error')
        fetch.assert_not_called();self.assertTrue(item.ready.is_set())
    def test_config_failure_signals_completion_instead_of_waiting_forever(self):
        item=BlogSession('testblog')
        def broken():raise ValueError('invalid config')
        manager=SessionStore(broken)
        with self.assertLogs(level='ERROR'):manager._load(item)
        self.assertTrue(item.ready.is_set());self.assertEqual(item.snapshot()['error_code'],'CONFIG_FAILED')
    def test_status_is_readable_while_keywords_are_being_analyzed(self):
        item=BlogSession('testblog');item.posts=posts();manager=SessionStore(lambda:{})
        started=threading.Event();release=threading.Event();snapshot_read=threading.Event()
        def slow(items,recent_limit=12,include_keywords=True):
            if include_keywords:
                started.set();release.wait(3)
            return real_summarize(items,recent_limit,include_keywords=False)
        try:
            with patch('back.sessions.summarize',side_effect=slow):
                worker=threading.Thread(target=manager._refresh_insights,args=(item,12));worker.start()
                self.assertTrue(started.wait(2))
                reader=threading.Thread(target=lambda:(item.snapshot(),snapshot_read.set()));reader.start()
                self.assertTrue(snapshot_read.wait(1),'Keyword analysis must not block the status/list snapshot lock.')
                self.assertEqual(len(item.snapshot()['insights']['recent_posts']),1)
                release.set();worker.join(2);reader.join(2)
        finally:release.set()

if __name__=='__main__':unittest.main()
