import re

_STOPWORDS = {'글', '글들', '게시글', '게시물', '포스팅', '관련', '관한', '대한', '대해',
              '좀', '혹시', '있어', '있나요', '있을까', '있을까요', '알려줘', '알려주세요',
              '찾아줘', '찾아주세요', '추천', '추천해줘', '추천해주세요', '검색', '검색해줘',
              '보고', '싶어', '싶어요', '보여줘', '보여주세요', '해주세요', '해줘', '어떤'}


def contains_term(text, term): 
    text, term = text.casefold(), term.casefold()
    if re.fullmatch(r'[a-z0-9]+', term):
        return re.search(r'(?<![a-z0-9])' + re.escape(term) + r'(?![a-z0-9])', text) is not None
    return term in text


def extract_keyword(text, keyword_map=None):
    terms = []
    for token in re.findall(r'[가-힣a-zA-Z0-9]+', text):
        # 대화체 조사 제거
        for suffix in ('으로', '에서', '관련', '이라는', '에', '은', '는', '을', '를'):
            if token.endswith(suffix) and len(token) - len(suffix) >= 2:
                token = token[:-len(suffix)]
                break
        if token not in _STOPWORDS and token.casefold() not in {t.casefold() for t in terms}:
            terms.append(token)
    # 연관된 단어 그룹 추가
    original = list(terms)
    for keyword, aliases in (keyword_map or {}).items():
        group = [keyword] + aliases
        if any(contains_term(term, alias) for term in original for alias in group):
            for alias in group:
                if alias.casefold() not in {t.casefold() for t in terms}:
                    terms.append(alias)
    return ' '.join(terms)
