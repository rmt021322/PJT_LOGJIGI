from contextlib import closing
from .keyword import extract_keyword
from .crawler import crawl_public_pages, crawl_post_contents
from .search import search_posts
from .ranking import rank_posts
from .output import output_posts


def pipeline(text, config):
    def event(stage, message=None, **extra):
        state = config['states'][stage]
        return dict(stage=stage, image='/static/character/' + state['image'],
                    message=message or state['message'], **extra)
    yield event('checking')
    keyword = extract_keyword(text, config.get('keyword_map'))
    if not keyword:
        yield event('empty', '검색할 단어를 입력해 주세요.', posts=[])
        return
    yield event('blog')
    posts = []
    warnings = []
    try:
        for batch in crawl_public_pages(config.get('blog_id', ''),
                max_pages=config.get('live_max_pages', 200),
                timeout_seconds=config.get('live_timeout_seconds', 120)):
            posts.extend(batch['posts'])
            yield event('blog', f"공개글 제목 {batch['scanned']}개를 확인했어요.",
                        scanned=batch['scanned'], total=batch['total'], page=batch['page'])
    except Exception:
        if not posts:
            raise
        warnings.append('글 목록 일부를 확인하지 못했어요.')
    if not posts:
        yield event('empty', '접근할 수 있는 공개글을 찾지 못했어요.', posts=[])
        return
    for index, post in enumerate(posts):
        post['source_order'] = index
    limit = config.get('limit', 3)
    yield event('searching', '먼저 제목에서 관련 글을 찾고 있어요.')
    title_matches = search_posts(posts, keyword, field='title')
    title_urls = {post['url'] for post in title_matches}
    candidates = {post['url']: dict(post) for post in title_matches}
    body_checked = 0
    failed = 0
    body_match_count = 0
    yield event('body', f'제목 검색을 마쳤어요. 공개글 {len(posts)}개의 본문을 확인할게요.')
    try:
        with closing(crawl_post_contents(posts, config.get('blog_id', ''),
                max_posts=config.get('body_max_posts', 0),
                timeout_seconds=config.get('body_timeout_seconds', 0),
                workers=config.get('body_workers', 3))) as bodies:
            for batch in bodies:
                body_checked = batch['checked']
                if batch['error']:
                    failed += 1
                elif batch['post']:
                    post = batch['post']
                    if post['url'] in title_urls:
                        candidates[post['url']] = dict(post, match_in='title')
                    elif search_posts([post], keyword, field='content'):
                        candidates[post['url']] = dict(post, match_in='content')
                        body_match_count += 1
                yield event('body', f'본문 {body_checked}/{len(posts)}개를 확인하고 있어요.',
                            body_checked=body_checked, body_total=len(posts))
    except Exception:
        warnings.append('일부 본문만 확인했어요.')
    if body_checked < len(posts) and '일부 본문만 확인했어요.' not in warnings:
        warnings.append('일부 본문만 확인했어요.')
    if failed:
        warnings.append(f'본문 {failed}개를 읽지 못했어요.')
    yield event('ranking')
    ranked = rank_posts(list(candidates.values()), keyword, limit)
    output = output_posts(ranked, keyword)
    message = ('제목에서 찾은 글부터 추천해 드려요.' if output
               else '확인한 제목과 본문에서 관련 글을 찾지 못했어요.')
    warning = ' '.join(warnings) or None
    if warning:
        message = '일부 글만 확인했어요. 확인한 범위에서 추천해 드려요.' if output else '일부 글을 확인하지 못해 관련 글이 없는지 확정할 수 없어요.'
    yield event('done' if output else 'empty', message, posts=output, keyword=keyword,
                partial=bool(warnings), scanned=len(posts), warning=warning,
                body_checked=body_checked, title_matches=len(title_matches),
                body_matches=body_match_count, body_total=len(posts),
                body_complete=body_checked == len(posts) and failed == 0)
