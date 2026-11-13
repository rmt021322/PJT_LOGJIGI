import copy
import json
import logging
import requests
import re
import secrets
import threading
import time
from contextlib import closing
from urllib.parse import urlsplit, parse_qs
from .crawler import crawl_public_pages, crawl_post_contents
from .insights import summarize


def normalize_blog_id(value):
    if not isinstance(value,str):
        raise ValueError('네이버 블로그 ID를 입력해 주세요.')
    value=value.strip()
    if value.startswith(('https://','http://')):
        parsed=urlsplit(value)
        if parsed.hostname not in ('blog.naver.com','m.blog.naver.com') or parsed.username or parsed.password:
            raise ValueError('네이버 블로그 주소 또는 ID를 입력해 주세요.')
        value=parse_qs(parsed.query).get('blogId',[parsed.path.strip('/').split('/')[0]])[0]
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',value):
        raise ValueError('블로그 ID는 영문·숫자·밑줄·하이픈으로 입력해 주세요.')
    return value


class BlogSession:
    def __init__(self,blog_id):
        self.token=secrets.token_urlsafe(24);self.blog_id=blog_id
        self.created=time.monotonic();self.touched=self.created
        self.lock=threading.RLock();self.ready=threading.Event();self.cancel=threading.Event()
        self.status='loading';self.phase='listing';self.message='공개글 목록을 읽고 있어요.'
        self.posts=[];self.checked=0;self.failed=0;self.warnings=[];self.list_complete=False
        self.insights=summarize([],include_keywords=False);self.revision=0
        self.error_code=None;self.keyword_error=None
    def snapshot(self):
        with self.lock:
            return copy.deepcopy(dict(blog_id=self.blog_id,status=self.status,phase=self.phase,
                message=self.message,total=len(self.posts),checked=self.checked,failed=self.failed,
                warnings=self.warnings,insights=self.insights,revision=self.revision,
                list_complete=self.list_complete,error_code=self.error_code,keyword_error=self.keyword_error))
    def documents(self):
        with self.lock:return copy.deepcopy(self.posts)


class SessionStore:
    def __init__(self,config_provider,ttl=2700,max_sessions=8):
        self.config_provider=config_provider;self.ttl=ttl;self.max_sessions=max_sessions
        self.items={};self.lock=threading.RLock()
    def _prune(self):
        for token,item in list(self.items.items()):
            if time.monotonic()-item.touched>self.ttl:
                self.items.pop(token);item.cancel.set()
    def create(self,blog_id):
        with self.lock:
            self._prune()
            if len(self.items)>=self.max_sessions:
                raise ValueError('분석 중인 블로그가 많아요. 기존 블로그를 닫고 다시 시도해 주세요.')
            item=BlogSession(normalize_blog_id(blog_id));self.items[item.token]=item
        threading.Thread(target=self._load,args=(item,),daemon=True).start()
        return item
    def get(self,token):
        if not isinstance(token,str):return None
        with self.lock:
            self._prune();item=self.items.get(token)
            if item is not None:item.touched=time.monotonic()
            return item
    def delete(self,token):
        with self.lock:item=self.items.pop(token,None)
        if item:item.cancel.set()
        return bool(item)
    def _warn(self,item,message):
        with item.lock:
            if message not in item.warnings:item.warnings.append(message)

    def _refresh_insights(self,item,recent_limit):
        # Publish cheap list metadata first. Keyword extraction must not hide titles
        # or hold the snapshot lock while preparing a language model.
        metadata=summarize(item.posts,recent_limit,include_keywords=False)
        with item.lock:
            previous=item.insights.get('keywords',[])
            item.insights=dict(metadata,keywords=previous)
            item.revision+=1
            disabled=bool(item.keyword_error)
        if disabled:return
        try:
            insights=summarize(item.posts,recent_limit)
        except Exception as exc:
            dependency=isinstance(exc,ImportError)
            code='KEYWORD_DEPENDENCY' if dependency else 'KEYWORD_FAILED'
            message=(f'관심 키워드 분석기를 불러오지 못했어요. 터미널에서 python -m pip install -r requirements.txt를 실행해 주세요. [{code}]'
                     if dependency else f'관심 키워드를 분석하지 못했어요. 읽은 글 목록과 글 검색은 계속 사용할 수 있어요. [{code}]')
            logging.exception('LOGJIGI keyword analysis failed [%s]',code)
            with item.lock:item.keyword_error=code
            self._warn(item,message)
        else:
            with item.lock:item.insights=insights;item.revision+=1

    def _listing_error(self,exc):
        if isinstance(exc,requests.Timeout):
            return 'LIST_TIMEOUT','글 목록 응답을 기다리다 시간이 초과됐어요.'
        if isinstance(exc,requests.HTTPError):
            status=getattr(exc.response,'status_code',None)
            if status in (403,429):return 'LIST_RESTRICTED',f'글 목록 요청이 제한됐어요. (HTTP {status})'
            return 'LIST_HTTP',f'글 목록 서버가 오류를 반환했어요. (HTTP {status or "확인 불가"})'
        if isinstance(exc,json.JSONDecodeError):
            return 'LIST_FORMAT','글 목록 응답을 해석하지 못했어요.'
        return 'LIST_FAILED','공개 글 목록을 가져오지 못했어요. ID와 연결 상태를 확인해 주세요.'

    def _load(self,item):
        stage='config'
        try:
            config=self.config_provider();recent_limit=config.get('insight_recent_posts',12)
            stage='listing'
            try:
                for batch in crawl_public_pages(item.blog_id,config.get('live_max_pages',200),config.get('live_timeout_seconds',120)):
                    if item.cancel.is_set():return
                    with item.lock:
                        item.posts.extend(batch['posts'])
                        for index,post in enumerate(item.posts):post['source_order']=index
                        item.list_complete=batch.get('complete',False)
                        item.message=f"공개글 제목 {len(item.posts)}개를 확인했어요."
                    self._refresh_insights(item,recent_limit)
            except Exception as exc:
                code,message=self._listing_error(exc)
                logging.exception('LOGJIGI listing failed [%s]',code)
                with item.lock:item.error_code=code
                if not item.posts:
                    with item.lock:
                        item.status='error';item.phase='error';item.message=f'{message} [{code}]';item.revision+=1
                    return
                self._warn(item,f'글 목록 일부만 확인했어요. {message} [{code}]')
            if not item.posts:
                with item.lock:
                    item.status='empty';item.phase='complete';item.message='이 방식으로 확인할 수 있는 공개 글 목록이 없어요. ID와 공개 설정을 확인해 주세요.';item.revision+=1
                return
            stage='bodies'
            with item.lock:item.phase='bodies';item.message='본문과 최근 관심 키워드를 확인하고 있어요.'
            positions={post['url']:i for i,post in enumerate(item.posts)}
            try:
                with closing(crawl_post_contents(item.posts,item.blog_id,
                        max_posts=config.get('body_max_posts',0),timeout_seconds=config.get('body_timeout_seconds',0),
                        workers=config.get('body_workers',3))) as stream:
                    for batch in stream:
                        if item.cancel.is_set():return
                        with item.lock:
                            item.checked=batch['checked']
                            if batch['error']:item.failed+=1
                            elif batch['post']:item.posts[positions[batch['post']['url']]]=batch['post']
                            item.message=f'본문 {item.checked}/{len(item.posts)}개를 확인하고 있어요.'
                        self._refresh_insights(item,recent_limit)
            except Exception:
                logging.exception('LOGJIGI body collection failed [BODY_FAILED]')
                with item.lock:item.error_code='BODY_FAILED'
                self._warn(item,'일부 본문만 확인했어요. [BODY_FAILED]')
            if item.checked<len(item.posts):self._warn(item,'일부 본문만 확인했어요.')
            if item.failed:self._warn(item,f'본문 {item.failed}개를 읽지 못했어요.')
            with item.lock:
                item.status='partial' if item.warnings else 'ready';item.phase='complete'
                item.message=('글 목록은 읽었어요. 관심 키워드 분석에는 문제가 있어요.' if item.keyword_error
                              else '확인한 글로 검색할 준비가 됐어요.')
                item.revision+=1
        except Exception:
            code='CONFIG_FAILED' if stage=='config' else 'ANALYSIS_FAILED'
            logging.exception('LOGJIGI session failed [%s]',code)
            with item.lock:
                item.status='error';item.phase='error';item.error_code=code;item.message=f'설정 또는 분석 처리 중 문제가 생겼어요. 터미널의 오류 내용을 확인해 주세요. [{code}]';item.revision+=1
        finally:item.ready.set()
