import re
from bs4 import BeautifulSoup


class PostContentUnavailable(ValueError):
    pass


def parse_post(html):
    """게시글 본문 읽기"""
    soup = BeautifulSoup(html, 'html.parser')
    body = soup.select_one('.se-main-container, #postViewArea, .post-view')
    if body is None:
        raise PostContentUnavailable('공개 본문을 읽을 수 없어요.')
    for element in body.select('script, style, noscript, iframe, .se-title-text, .post_tag'):
        element.decompose()
    text = re.sub(r'[\s\u200b\ufeff]+', ' ', body.get_text(' ', strip=True)).strip()
    if not text:
        raise PostContentUnavailable('검색할 본문 텍스트가 없어요.')
    return text
