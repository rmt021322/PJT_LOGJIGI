# 로그지기 LOGJIGI
<img width="453" height="439" alt="HOME" src="https://github.com/user-attachments/assets/aa34c523-9964-4a21-ad99-03965fd23551" />

로그인 없이 네이버 블로그 ID만 입력하면 공개글을 검색하고 최근 관심 키워드를 확인할 수 있는 Flask 기반 개인 프로젝트입니다.  
현재는 로컬 환경에서 실행하는 프로토타입이며, 외부 웹 검색 기능은 준비 중입니다.  

## 실행 화면
### 1. 기본 화면
<img width="450" height="430" alt="HOME" src="https://github.com/user-attachments/assets/17f94771-c383-4a03-9d8b-e1d99289e125" />

### 2. 검색 매체 선택
<img width="450" height="430" alt="choice" src="https://github.com/user-attachments/assets/fdcce62f-c3e3-4f26-b349-284873d3bfdf" />

### 3. 블로그 검색과 결과
<img width="450" height="430" alt="blogsearch" src="https://github.com/user-attachments/assets/386f9762-77c3-4583-9767-cb623fb38e1c" />
<img width="450" height="430" alt="blogsearch_result" src="https://github.com/user-attachments/assets/49ff33fd-75f2-4aaf-ab7e-1a48d4f6c298" />

### 4. 웹 검색 화면(사용 불가)
<img width="450" height="430" alt="websearch" src="https://github.com/user-attachments/assets/70be5098-57e7-487b-bee8-c7137f20a020" />

※ 위 실행 화면은 제작자 본인의 네이버 블로그 공개글을 활용한 시연입니다.

## 제작 역할

### 직접 기획·설계한 부분
- 웹 화면 구성과 사용자 흐름 설계
- 게시글 추천과 인기글 표시 기준 기획 
검색어와 제목·본문의 키워드 일치를 기준으로 관련 글을 최대 3개 추천합니다.
블로그 노트에서는 최근 분석한 글 중 공개된 누적 조회수를 기준으로 인기글을 최대 3개 표시하며, 조회수를 확인할 수 없으면 최근 공개글을 보여줍니다.
- 캐릭터 콘셉트와 상태별 동작 설정  
 <img width="444" height="235" alt="캐릭터 초안" src="https://github.com/user-attachments/assets/d284ef8d-bca1-4737-9d42-b18e1dcaa1fd" />  

직접 그린 초안을 바탕으로 캐릭터의 색상과 상태별 동작을 정했습니다.  
- 실행 결과 확인과 개선사항 제시  

### GPT를 활용한 부분
- 캐릭터 일러스트 제작  
<img width="640" height="360" alt="일러스트" src="https://github.com/user-attachments/assets/3c4e1d61-8f4a-4076-965e-ba2461e9e2c6" />  

위 설정을 GPT에 전달해 상태별 이미지를 제작하고, 원하는 이미지가 나올 때까지 수정 요청했습니다.  
- 화면과 검색 기능을 연결하는 MVP 코드 구현  
- 블로그 공개글 크롤링 코드 작성  

## 버전 구분
- `basic`: 초기 화면 구상안
- `prototype`: 현재 기능을 시연하는 프로토타입

## 직접 실행해보기
아래 실행 방법은 Windows의 Git Bash 기준입니다. Python 3.9 이상과 Git Bash가 설치되어 있어야 하며, 인터넷 연결이 필요합니다.

### 1. 프로젝트 다운로드
1. 이 저장소에서 `prototype` 브랜치를 선택합니다.
2. 초록색 `Code` 버튼에서 `Download ZIP`을 클릭합니다.
3. 다운로드한 ZIP 파일의 압축을 풉니다.

### 2. 프로젝트 폴더에서 터미널 열기
압축을 푼 폴더 중 **`app.py`와 `requirements.txt`가 있는 폴더**에서 Git Bash를 엽니다.

### 3. 실행 환경 준비
아래 명령어를 한 줄씩 입력합니다. 처음 실행할 때만 진행하면 됩니다.

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
```

### 4. 로그지기 실행
```bash
python app.py
```

브라우저가 자동으로 열립니다.
열리지 않으면 http://127.0.0.1:5000 에 접속해 주세요.

화면에 네이버 블로그 ID를 입력하면 사용할 수 있습니다.
첫 분석은 게시글 수와 인터넷 환경에 따라 시간이 걸릴 수 있습니다.

### 5. 종료하기
사용하는 동안 터미널 창을 유지해 주세요.
종료하려면 터미널에서 `Ctrl+C`를 누릅니다.

### 다음에 다시 실행할 때
프로젝트 폴더에서 Git Bash를 열고 아래 명령어만 입력합니다.

```bash
source .venv/Scripts/activate
python app.py
```

※ 현재는 내 컴퓨터에서 실행하는 프로토타입입니다.
외부 웹 검색 기능은 준비 중입니다.
