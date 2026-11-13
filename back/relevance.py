import math
from .keyword import contains_term, extract_keyword
from .search import excerpt


def query_groups(text, aliases=None):
    terms = extract_keyword(text).split()
    groups = []
    for term in terms:
        choices = [term]
        for canonical, related in (aliases or {}).items():
            values = [canonical] + related
            if any(term.casefold() == value.casefold() for value in values):
                choices.extend(values)
        groups.append(list(dict.fromkeys(choices)))
    return groups


def verify_post(post, groups):
    if not groups:
        return None
    title, body = post.get('title', ''), post.get('content', '')
    title_hits = [any(contains_term(title, term) for term in group) for group in groups]
    body_hits = [any(contains_term(body, term) for term in group) for group in groups]
    if not all(a or b for a,b in zip(title_hits, body_hits)):
        return None
    in_title = all(title_hits)
    # 본문이 길고 제목에 없는 단어가 2회 미만 등장하면 제외
    counts = [sum(body.casefold().count(term.casefold()) for term in group) for group in groups]
    if not in_title and len(body) > 1200 and any(not hit and count < 2 for hit,count in zip(title_hits, counts)):
        return None
    score = sum(title_hits) * 10 + sum(math.log1p(n) for n in counts)
    score += min(2, sum(counts) * 200 / max(200, len(body)))
    return dict(post, match_in='title' if in_title else 'content', relevance_score=score)


def recommend(posts, text, limit=3, aliases=None):
    groups = query_groups(text, aliases)
    seen, verified = set(), []
    for post in posts:
        if post['url'] in seen:
            continue
        result = verify_post(post, groups)
        if result is not None:
            verified.append(result);seen.add(post['url'])
    verified.sort(key=lambda p:(p['match_in']=='title',p['relevance_score'],-p.get('source_order',0)),reverse=True)
    terms = ' '.join(term for group in groups for term in group)
    return [dict(title=post['title'], url=post['url'], content=excerpt(post.get('content',''),terms),
                 match_in=post['match_in'], evidence='제목 일치' if post['match_in']=='title' else '본문 근거 확인')
            for post in verified[:max(0,min(3,int(limit)))]]
