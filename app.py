import json
import logging
from pathlib import Path
from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from back.sessions import SessionStore
from back.relevance import recommend,query_groups

app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=8192
CONFIG_PATH=Path(__file__).with_name('config.json')

def config():return json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
store=SessionStore(config)

def error(message,status=400):return jsonify(error=message),status

def payload():
    data=request.get_json(silent=True)
    return data if isinstance(data,dict) else {}

def event(stage,message=None,**extra):
    state=config()['states'][stage]
    return dict(stage=stage,image='/static/character/'+state['image'],message=message or state['message'],**extra)

@app.get('/')
def home():return render_template('index.html')

@app.post('/api/blogs')
def create_blog():
    try:item=store.create(payload().get('blog_id'))
    except ValueError as exc:return error(str(exc))
    return jsonify(token=item.token,blog_id=item.blog_id),201

@app.get('/api/blogs/<token>')
def blog_status(token):
    item=store.get(token)
    if item is None:return error('블로그 연결이 만료됐어요. ID를 다시 입력해 주세요.',404)
    return jsonify(item.snapshot())

@app.delete('/api/blogs/<token>')
def delete_blog(token):
    store.delete(token)
    return '',204

@app.post('/api/search')
def search():
    data=payload();text=data.get('text');item=store.get(data.get('token'))
    if item is None:return error('먼저 블로그 ID를 입력해 주세요.',404)
    if not isinstance(text,str) or not 1<=len(text.strip())<=200:return error('검색어를 1~200자로 입력해 주세요.')
    if not query_groups(text):return error('찾고 싶은 주제의 단어를 입력해 주세요.')
    @stream_with_context
    def generate():
        try:
            yield json.dumps(event('checking'),ensure_ascii=False)+'\n'
            while not item.ready.wait(.8):
                if item.cancel.is_set():
                    yield json.dumps(event('error','블로그 연결이 변경됐어요.',posts=[]),ensure_ascii=False)+'\n';return
                status=item.snapshot()
                yield json.dumps(event('body',status['message']),ensure_ascii=False)+'\n'
            status=item.snapshot()
            if status['status']=='error':
                yield json.dumps(event('error',status['message'],posts=[]),ensure_ascii=False)+'\n';return
            yield json.dumps(event('searching','제목에서 먼저 찾고 본문 근거도 확인할게요.'),ensure_ascii=False)+'\n'
            posts=recommend(item.documents(),text,3,config().get('keyword_map'))
            yield json.dumps(event('ranking','관련 없는 글을 제외하고 순서를 정하고 있어요.'),ensure_ascii=False)+'\n'
            message='관련 글을 최대 3개 골랐어요.' if posts else '키워드와 맞는 글을 찾지 못했어요. 다른 단어로 물어봐 주세요.'
            yield json.dumps(event('done' if posts else 'empty',message,posts=posts,
                warning=' '.join(status['warnings']) or None,scanned=status['total'],body_checked=status['checked'],
                body_total=status['total'],partial=bool(status['warnings'])),ensure_ascii=False)+'\n'
        except Exception:
            logging.exception('Blog search failed')
            yield json.dumps(event('error','검색 중 문제가 생겼어요. 다시 시도해 주세요.',posts=[]),ensure_ascii=False)+'\n'
    return Response(generate(),mimetype='application/x-ndjson',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

@app.post('/api/web-search')
def web_search():
    # Preparation screen only: no Google, news or paid API request is made.
    return jsonify(status='preparing',message='웹 검색은 준비 중이에요. 현재는 블로그 글 검색을 이용해 주세요.',posts=[])

@app.after_request
def no_cache(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response

if __name__=='__main__':
    import os,threading,webbrowser
    if os.environ.get('LOGKEEPER_OPEN_BROWSER','1')=='1':
        threading.Timer(1.2,lambda:webbrowser.open('http://127.0.0.1:5000')).start()
    app.run(host='127.0.0.1',port=5000,debug=False,threaded=True)
