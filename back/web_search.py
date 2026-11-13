"""향후 웹 검색 연결용 어댑터. 현재 app.py와 화면에서는 호출하지 않습니다."""
import os
import re
import ipaddress
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlsplit, parse_qs, urljoin
import requests
from bs4 import BeautifulSoup


class SearchUnavailable(ValueError):
    pass


def safe_link(url):
    if not isinstance(url,str):return None
    try:
        parsed=urlsplit(url)
        if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:return None
        if parsed.hostname in ('localhost','localhost.localdomain') or parsed.hostname.endswith('.local'):return None
        try:
            if not ipaddress.ip_address(parsed.hostname).is_global:return None
        except ValueError:pass
        return url
    except ValueError:return None


def google_link(query, now=None):
    now=now or datetime.now(timezone.utc)
    start=(now-timedelta(days=7)).date().isoformat()
    end=(now+timedelta(days=1)).date().isoformat()
    return 'https://www.google.com/search?'+urlencode(dict(q=f'{query} after:{start} before:{end}',tbs='qdr:w',hl='ko'))


def get_bytes(url, params=None):
    with requests.get(url,params=params,timeout=(8,18),stream=True,allow_redirects=False,
                      headers={'User-Agent':'LogKeeper/0.5 public-search-assistant'}) as response:
        response.raise_for_status()
        if response.status_code!=200:raise SearchUnavailable('검색 응답을 읽을 수 없어요.')
        chunks=[];size=0
        for chunk in response.iter_content(65536):
            size+=len(chunk)
            if size>3_000_000:raise SearchUnavailable('검색 응답이 너무 커요.')
            chunks.append(chunk)
        return b''.join(chunks)


def parse_google_html(content):
    soup=BeautifulSoup(content,'html.parser')
    text=soup.get_text(' ',strip=True)
    if soup.select('form[action*="/sorry/"]') or 'unusual traffic' in text.lower():
        raise SearchUnavailable('Google이 자동 수집을 제한했어요.')
    results=[];seen=set()
    for heading in soup.select('h3'):
        anchor=heading.find_parent('a',href=True)
        if anchor is None:
            parent=heading.parent
            anchor=parent.find('a',href=True) if parent else None
        if anchor is None:continue
        url=anchor['href']
        if url.startswith('/url?'):url=parse_qs(urlsplit(url).query).get('q',parse_qs(urlsplit(url).query).get('url',['']))[0]
        url=safe_link(url)
        if not url or url in seen or urlsplit(url).hostname in ('www.google.com','google.com'):continue
        title=heading.get_text(' ',strip=True)
        container=heading.find_parent(['div','section'])
        snippet=container.get_text(' ',strip=True) if container else ''
        results.append(dict(title=title,url=url,content=snippet[:400],published_at=None,source='Google 웹',date_verified=False))
        seen.add(url)
    if not results:raise SearchUnavailable('Google 일반 검색 결과를 읽지 못했어요.')
    return results[:8]


def parse_news_xml(content, now=None):
    now=now or datetime.now(timezone.utc);start=now-timedelta(days=7)
    root=ET.fromstring(content);results=[];seen=set()
    for item in root.findall('./channel/item'):
        try:published=parsedate_to_datetime(item.findtext('pubDate','')).astimezone(timezone.utc)
        except (ValueError,TypeError,OverflowError):continue
        url=safe_link(item.findtext('link',''))
        if not url or url in seen or not start<=published<=now:continue
        title=item.findtext('title','').strip()
        if not title:continue
        source=item.findtext('source','')
        results.append(dict(title=title,url=url,
            content=BeautifulSoup(item.findtext('description',''),'html.parser').get_text(' ',strip=True)[:400],
            published_at=published.isoformat(),source=source or 'Google 뉴스',date_verified=True))
        seen.add(url)
    return sorted(results,key=lambda item:item['published_at'],reverse=True)[:8]


def serpapi_search(query):
    key=os.environ.get('SERPAPI_API_KEY','').strip()
    if not key:return None
    payload=get_bytes('https://serpapi.com/search.json',dict(engine='google',q=query,tbs='qdr:w',hl='ko',gl='kr',api_key=key))
    import json
    data=json.loads(payload)
    if data.get('error'):raise SearchUnavailable('설정한 검색 API가 응답하지 않았어요.')
    results=[];seen=set()
    for item in data.get('organic_results',[]):
        url=safe_link(item.get('link'))
        if url and url not in seen and item.get('title'):
            results.append(dict(title=item['title'],url=url,content=item.get('snippet',''),
                                published_at=item.get('date'),source='Google 웹 · SerpApi',date_verified=False))
            seen.add(url)
    return results[:8]


def search_recent_web(query,now=None):
    now=now or datetime.now(timezone.utc)
    result=dict(query=query,google_url=google_link(query,now),window_start=(now-timedelta(days=7)).isoformat(),
                window_end=now.isoformat(),posts=[],provider=None,warning=None,
                date_note='Google의 최근 7일 필터를 적용했습니다. 웹 결과의 게시일을 별도로 검증한 것은 아닙니다.')
    try:
        api=serpapi_search(query)
        if api is not None:
            result.update(posts=api,provider='google_api')
            return result
        content=get_bytes('https://www.google.com/search',dict(q=query,tbs='qdr:w',hl='ko',num=10))
        result.update(posts=parse_google_html(content),provider='google_web')
        return result
    except Exception:
        result['warning']='Google 일반 웹 결과 수집이 제한되어 Google 뉴스의 최근 7일 자료를 대신 확인했어요. 일반 웹은 아래 Google 링크에서 확인할 수 있어요.'
    try:
        content=get_bytes('https://news.google.com/rss/search',dict(q=query+' when:7d',hl='ko',gl='KR',ceid='KR:ko'))
        result.update(posts=parse_news_xml(content,now),provider='google_news',
                      date_note='Google 뉴스가 제공한 게시 시각이 최근 7일 이내인 자료만 표시합니다.')
    except Exception:
        result['warning']='Google 검색 결과를 가져오지 못했어요. 아래 링크로 최근 7일 검색을 직접 열어주세요.'
        result['provider']='unavailable'
    return result
