from .keyword import contains_term


def search_posts(posts, keyword, field='title'):
    terms = keyword.casefold().split()
    if field not in ('title', 'content'):
        raise ValueError('검색 위치가 올바르지 않습니다.')
    return [dict(post, match_in=field) for post in posts
            if any(contains_term(post.get(field, ''), term) for term in terms)]


def excerpt(content, keyword, length=180):
    """키워드 주변 맥락 제시"""
    folded = content.casefold()
    positions = [folded.find(term) for term in keyword.casefold().split() if term in folded]
    start = max(0, min(positions, default=0) - 45)
    text = content[start:start + length]
    return ('…' if start else '') + text + ('…' if start + length < len(content) else '')
