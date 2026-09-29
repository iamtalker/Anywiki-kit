# 변경 기록

버전마다 달라진 점을 여기에 적습니다. 새 버전이 위에 옵니다.

## 0.4 — 2026-09-29
**엔진별 플러그인** — 관리판 '플러그인' 칸, 리눅스 `anywiki.sh plugin …`, `kit.py plugin …`.
- DokuWiki: 들어 있는 플러그인 켜고 끄기(`conf/plugins.local.php`, 꼭 필요한 것은 잠김), **플러그인 저장소에서 찾아 설치**
  (보안 문제가 알려진 것·https 가 아닌 주소는 거절, 압축 밖으로 풀리는 경로 거절, 50MB 제한).
- MediaWiki: 함께 들어 있는 확장 34개 켜고 끄기(공식 update 로 DB 맞춤, 실패하면 되돌림). 설명은 확장의 한국어 메시지에서.
- Markdown 내장: 수식(KaTeX)·코드 색칠(highlight.js) 켜고 끄기(새로 설치하면 둘 다 켜짐).
- openNAMU: 키트에서 켜고 끌 플러그인 없음.
- 리눅스에서 관리판을 kill 로 끄면 위키 프로그램도 함께 끔.
- 시험: 가짜 저장소 서버로 찾기·설치·위험한 압축·보안 문제 플러그인 거절.

## 0.3 — 2026-09-29 (커밋 8dd3516)
엔진을 고르고 바꾸는 키트가 됨.
- **엔진 4가지**: openNAMU · Markdown(내장, 새로 만듦) · DokuWiki · MediaWiki. 관리판 '엔진' 칸에서 [설치]·[이 엔진으로 바꾸기].
  - DokuWiki·MediaWiki 는 Docker Hub 공식 이미지의 프로그램 층을 sha256 digest 로 고정해 받는다(Docker 불필요). PHP 내장 서버로 켠다.
  - MediaWiki 는 SQLite 로 공식 설치 스크립트를 돌려 만든다. 임시 공개 주소가 바뀌어도 되게 `$wgServer` 를 요청 주소에서 정한다.
  - 설치 때 관리자 계정(admin)과 비밀번호를 만들어 관리판에 보여 준다. 기본 권한은 누구나 읽기, 로그인한 사람만 편집.
- **엔진 바꾸기**: 모든 문서를 공용 언어를 거쳐 새 엔진 문법으로 통역해 옮긴다. 옛 엔진 데이터는 `wikis/옛엔진/` 에 남는다. 첫 화면 이름도 맞춘다.
- **가져오기 4형식**: openNAMU · MediaWiki · DokuWiki · Markdown 파일을 지금 엔진으로 통역해 넣는다(내 쪽이 더 새로우면 건너뜀).
- 폴더 구조: `wiki/` → `wikis/엔진이름/`(0.1 의 폴더는 처음 켤 때 자동으로 옮김).
- 리눅스: `install.sh [엔진]`, `anywiki.sh switch|export|import`. 끌 때 PHP 일꾼 프로세스까지 끈다.
- Docker: `ENGINE` 환경 변수, 이미지에 PHP 포함, 볼륨 `/kit/wikis`. `ENGINE` 을 바꿔 다시 올리면 문서를 옮긴다.
- 관리판: 다른 사이트에서 온 요청(Origin 이 관리판이 아님)은 거절. 새 판 알림은 릴리스가 아직 없으면 오류 대신 그렇게 알린다.
- 없앤 것: `add_frontpage.py`·`convert_wiki.py`(→ `kit.py`·`transfer.py`·`wikiconv`), Windows `start.ps1`·`stop.ps1`. `install.ps1` 은 파이썬만 받는다.

## 0.2 — 2026-09-29 (커밋 7513dc8)
**공용 언어 통역기** `scripts/wikiconv/`.
- 나무마크 · 위키텍스트(MediaWiki) · 도쿠위키 · 마크다운을 읽어 공통 구조(AST)로, 공통 구조를 다시 각 형식·HTML 로 쓴다(4×4 모든 조합).
- 공통 구조의 글 형태는 **AWM**(확장 마크다운): 머리말(분류·넘겨주기), `[[문서#절|글]]`, `{{틀|인자}}`, 각주, 표 칸 속성, 원문 보존 블록.
- 실제 문서 2만여 개로 시험: DokuWiki·MediaWiki·AWM 은 문서의 98.4% 가 낱말 90% 이상을 지님, 6가지 형식을 오가며 오류 0.

## 0.1 — 2026-09-29 (첫 판, 아직 릴리스 전)
[유어위키](https://github.com/iamtalker/yourwiki) 1.2 에서 갈라져 나옴. 나무위키 전용 기능(데이터 설치, 최신판 동기화, 갱신 단추, P2P 공유, 중계소)을 빼고 범용 위키 키트로 만듦.
- 원터치 설치: openNAMU 엔진을 받아 해시로 검증하고 빈 위키와 첫 화면(FrontPage)을 만듦(Windows 관리판, 리눅스 `server/install.sh`, Docker).
- 관리판: 켜기·끄기, 위키 색, 인터넷에 공개(Cloudflare 임시 주소), 내보내기, 가져오기, 새 판 알림, 설치. 기능별 칸 접기, 설정 유지.
- 내보내기: openNAMU(SQLite, 문서 표만) · MediaWiki · DokuWiki · Markdown. 가져오기: openNAMU 형식(내 쪽보다 새 판만 이어 붙임).
- 오프라인 중계 서버: CDN 자원을 동봉 파일로, 외부 삽입은 링크로, 머리글 색·휴대폰 화면·검색 자동완성·아무 문서나 보기.
- 리눅스: `server/anywiki.sh`(설정은 `anywiki.conf` 에 기억, `TUNNEL=on` 으로 임시 주소 공개).
