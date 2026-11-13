from collections import Counter, defaultdict
import threading

MAX_KEYWORDS = 5
_tokenizer = None
_tokenizer_lock = threading.Lock()

STOP = set('그리고 그래서 하지만 오늘 이번 정말 너무 그냥 조금 이제 있는 없는 있어 있다 같다 같이 저는 제가 나는 내가 우리 여러분 이야기 기록 블로그 포스팅 사진 경우 정도 생각 때문에 위해 위한 대해 대한 관한 통해 이렇게 그렇게 저렇게 다음 먼저 다시 바로 하는 하면 해서 했던 했는데 했습니다 됩니다 합니다 있습니다 같습니다 이것 저것 지금 아직 역시 모든 여러 직접 보고 싶은 싶다 입니다 입니다만 하기 되어 되는 않는 없이 하나 두개 합니다만 시작 이후 이전 했어요 있어요 같아요 좋아요 했지만 했던 했던것 되는지'.split())


STOP.update('후기 진짜 요즘 그래도 여기 저기 거기 사실 결국 때문 이거 그거 저거 나중 대충 가장 많이 이런 그런 저런 어떤 같은 같고 같아서 같음 아마 일단 지난 내일 어제 시간 오랜만 오래 원래 무엇 어디 아니 내가하면 있으면 없으면 했으니 때문에 중간 생각보다 오히려 덕분 조금씩 갑자기 처음 오늘도 그렇게까지 해야 할수있다 되니까 살짝 너무나 역시나 아무튼 아무래도 보니까 그러면 그렇지만 그런데 그러니까 그렇고 거예요 거야 하니까 했더니 아니라'.split())


def _noun_terms(text):
    """조사, 어미 제외하고 주제어(명사, 외국어) 남기기."""
    global _tokenizer
    if not text:
        return []
    if _tokenizer is None:
        with _tokenizer_lock:
            if _tokenizer is None:
                from kiwipiepy import Kiwi
                _tokenizer = Kiwi(num_workers=1)
    words = []
    current = ''
    last_end = -1
    for token in _tokenizer.tokenize(text):
        tag = token.tag.split('-')[0]
        is_noun = tag in {'NNG', 'NNP', 'SL'}
        # 인접복합명사 보존하기
        is_suffix = tag == 'XSN' and current and token.start == last_end
        if is_noun or is_suffix:
            if current and token.start == last_end:
                current += token.form
            else:
                if current:
                    words.append(current)
                current = token.form
            last_end = token.start + token.len
        else:
            if current:
                words.append(current)
            current = ''
            last_end = -1
    if current:
        words.append(current)
    result = []
    for word in words:
        if word.isascii() and len(word) <= 4:
            word = word.upper()
        if 2 <= len(word) <= 18 and not word.isdigit() and word.casefold() not in STOP:
            result.append(word)
    return result


def _post_terms(post):
    title = post.get('title', '')
    body = post.get('content', '')[:10000]
    signature = (title, body)
    # 이번 연결에서만 캐시 사용하기
    if post.get('_interest_signature') != signature:
        post['_interest_title_terms'] = _noun_terms(title)
        post['_interest_body_terms'] = _noun_terms(body)
        post['_interest_signature'] = signature
    return post['_interest_title_terms'], post['_interest_body_terms']


def interest_keywords(posts, limit=MAX_KEYWORDS):
    limit = max(0, min(MAX_KEYWORDS, int(limit)))
    scores = Counter()
    evidence = defaultdict(list)
    title_words = set()
    for index, post in enumerate(posts):
        title, body = _post_terms(post)
        title_words.update(title)
        for term in set(title + body):
            weight = (3 if term in title else 1) / (1 + index * .1)
            scores[term] += weight
            evidence[term].append(dict(title=post['title'], url=post['url']))
    # 동점인 경우 용어 기준 정렬 -> 예시 수 기준 정렬 -> 단어 기준 정렬
    def order(word):
        return (-scores[word], -len(evidence[word]), word)
    recurring = [word for word in scores if len(evidence[word]) >= 2]
    chosen = sorted(recurring, key=order)
    if len(chosen) < limit:
        chosen += sorted([word for word in title_words if word not in chosen], key=order)
    return [dict(keyword=word, post_count=len(evidence[word]), examples=evidence[word][:2])
            for word in chosen[:limit]]


def summarize(posts, recent_limit=12, include_keywords=True):
    recent=sorted(posts,key=lambda p:p.get('source_order',0))[:recent_limit]
    measured=[post for post in recent if isinstance(post.get('views'),int)]
    popular=sorted(measured,key=lambda p:p['views'],reverse=True)[:3]
    def public(post):
        return {key:post.get(key) for key in ('title','url','published_at','views')}
    return dict(keywords=interest_keywords(recent) if include_keywords else [],recent_posts=[public(p) for p in recent[:3]],
                popular_posts=[public(p) for p in popular],popular_available=bool(measured),
                popular_basis='최근 분석 글 중 공개된 누적 조회수 기준' if measured else None,
                analyzed_posts=len(recent),body_read=sum(bool(p.get('content')) for p in recent),
                keyword_basis=f'최근 작성글 {len(recent)}개의 제목·읽을 수 있는 본문 기반 추정',
                search_terms_available=False)
