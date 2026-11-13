import json
import re
import requests


class CollectionIncomplete(ValueError):
    """게시글 일부 읽어오기"""


def decode_listing(payload, blog_id):
    """로그인 없이 공개글 읽어오기"""
    from html import unescape
    from urllib.parse import unquote_plus
    if payload.get('resultCode') != 'S' or not isinstance(payload.get('postList'), list):
        raise CollectionIncomplete('공개 글 목록 응답을 읽지 못했어요.')
    try:
        total = int(str(payload['totalCount']).replace(',', ''))
    except (KeyError, TypeError, ValueError):
        raise CollectionIncomplete('전체 글 수를 확인하지 못했어요.')
    posts = []
    for item in payload['postList']:
        log_no = str(item.get('logNo', ''))
        if not log_no.isdigit():
            raise CollectionIncomplete('게시글 주소 형식이 바뀌었어요.')
        # 공개글 읽기
        if (str(item.get('openType', '2')) != '2'
                or str(item.get('isPostNotOpen', '0')) != '0'
                or str(item.get('isPostBlocked', '0')) != '0'):
            continue
        posts.append(dict(title=unescape(unquote_plus(item.get('title', ''))),
                          url=f'https://blog.naver.com/{blog_id}/{log_no}',
                          content='', views=(int(str(item.get('readCount', '')).replace(',', ''))
                              if str(item.get('readCount', '')).replace(',', '').isdigit() else None),
                          published_at=item.get('addDate', '')))
    return posts, total, len(payload['postList'])


def crawl_public_pages(blog_id, max_pages=200, timeout_seconds=120, page_delay=0.3):
    """페이지별로 중복되지 않은 공개글 목록을 순차적으로 읽어오기"""
    import time
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', blog_id):
        raise ValueError('블로그 ID 설정을 확인해 주세요.')
    seen = set()
    raw_count = 0
    started = time.monotonic()
    with requests.Session() as session:
        session.headers.update({'User-Agent': 'LogKeeper/0.2 public-title-search',
                                'Referer': f'https://blog.naver.com/{blog_id}'})
        for page in range(1, max_pages + 1):
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise CollectionIncomplete('검색 시간 제한에 도달했어요.')
            response = session.get('https://blog.naver.com/PostTitleListAsync.naver',
                params=dict(blogId=blog_id, currentPage=page, categoryNo=0,
                            parentCategoryNo=0, countPerPage=30),
                timeout=(min(15, remaining), min(20, remaining)), allow_redirects=False)
            response.raise_for_status()
            if response.status_code != 200 or len(response.content) > 2_000_000:
                raise CollectionIncomplete('공개 글 목록 응답을 확인하지 못했어요.')
            # strict=False handles legacy control characters in title-list JSON.
            text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', response.text)
            payload = json.loads(text, strict=False)
            posts, total, raw_size = decode_listing(payload, blog_id)
            unique = [post for post in posts if post['url'] not in seen]
            seen.update(post['url'] for post in unique)
            raw_count += raw_size
            complete = raw_count >= total
            if raw_size == 0 and not complete:
                raise CollectionIncomplete('남은 글 목록을 불러오지 못했어요.')
            if posts and not unique and not complete:
                raise CollectionIncomplete('같은 글 목록이 반복되어 검색을 중단했어요.')
            yield dict(posts=unique, page=page, scanned=len(seen), total=total, complete=complete)
            if complete:
                return
            if page < max_pages:
                time.sleep(page_delay)
    raise CollectionIncomplete('한 번에 확인할 수 있는 페이지 수에 도달했어요.')



def _fetch_post_content(post, blog_id, remaining=None):
    """One bounded public request; session/response always close in the worker."""
    import time
    from .parser import parse_post
    match = re.fullmatch(r'https://blog\.naver\.com/' + re.escape(blog_id) + r'/(\d+)', post['url'])
    if not match:
        raise ValueError('본문 주소 형식이 올바르지 않아요.')
    started = time.monotonic()
    connect_timeout = min(15, remaining / 2) if remaining is not None else 15
    read_timeout = min(20, remaining / 2) if remaining is not None else 20
    with requests.Session() as session:
        session.headers.update({'User-Agent': 'LogKeeper/0.4 public-blog-search',
                                'Referer': f'https://blog.naver.com/{blog_id}'})
        with session.get('https://blog.naver.com/PostView.naver',
                params=dict(blogId=blog_id, logNo=match.group(1), redirect='Dlog',
                            widgetTypeCall='true', directAccess='false'),
                timeout=(max(.1, connect_timeout), max(.1, read_timeout)),
                allow_redirects=False, stream=True) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError('공개 본문에 접근하지 못했어요.')
            chunks = []
            size = 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 5_000_000 or (remaining is not None and time.monotonic() - started >= remaining):
                    raise ValueError('본문 응답의 크기 또는 시간 제한을 초과했어요.')
                chunks.append(chunk)
            return dict(post, content=parse_post(b''.join(chunks)))


def crawl_post_contents(posts, blog_id, max_posts=0, timeout_seconds=0, workers=3):
    """Search all listed posts by default; limits are optional, never implicit."""
    import time
    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', blog_id):
        raise ValueError('블로그 ID 설정을 확인해 주세요.')
    selected = posts[:max_posts] if max_posts > 0 else posts
    deadline = time.monotonic() + timeout_seconds if timeout_seconds > 0 else None
    iterator = iter(selected)
    pool = ThreadPoolExecutor(max_workers=max(1, min(int(workers), 3)))
    pending = set()
    checked = 0
    def submit_next():
        remaining = deadline - time.monotonic() if deadline else None
        if remaining is not None and remaining <= 0:
            raise CollectionIncomplete('설정한 본문 검색 시간에 도달했어요.')
        try:
            post = next(iterator)
        except StopIteration:
            return
        pending.add(pool.submit(_fetch_post_content, post, blog_id, remaining))
    try:
        for _ in range(max(1, min(int(workers), 3))):
            submit_next()
        while pending:
            if deadline and time.monotonic() >= deadline:
                raise CollectionIncomplete('설정한 본문 검색 시간에 도달했어요.')
            completed, _ = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
            if not completed:
                yield dict(post=None, error=None, checked=checked, total=len(posts))
                continue
            for future in completed:
                pending.remove(future)
                checked += 1
                try:
                    post = future.result()
                    error = None
                except Exception:
                    post = None
                    error = '본문을 확인하지 못한 글이 있어요.'
                yield dict(post=post, error=error, checked=checked, total=len(posts))
                submit_next()
        if max_posts > 0 and len(selected) < len(posts):
            raise CollectionIncomplete('설정한 본문 개수까지만 확인했어요.')
    finally:
        for future in pending:
            future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
