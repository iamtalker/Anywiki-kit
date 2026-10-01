# README for AI — 애니위키 키트 인수인계 문서

> **이 문서는 AI 작업 세션끼리 이어 달리기를 하기 위한 것이다.**
> 새 세션은 작업을 시작하기 전에 이 문서를 끝까지 읽는다.
> 작업을 마칠 때(커밋·푸시 전)는 맨 아래 「작업 기록」에 새 항목을 **위에 덧붙인다**. 지우지 말고 쌓는다.
> 결정이 바뀌면 옛 내용을 지우지 말고 "(YYYY-MM-DD 바뀜: …)" 로 고쳐 적는다. 이유가 남아야 같은 논의를 되풀이하지 않는다.

## 1. 사용자(저장소 주인)와 일하는 법

- 저장소: `iamtalker/anywiki-kit`. 형제 프로젝트: `iamtalker/yourwiki`(나무위키 전체를 내 위키로). 이 키트는 유어위키 1.2 에서 갈라져 나왔다.
- 주인은 한국어 사용자다. **답은 한국어로 한다.** 개발 용어보다 결과를 본다. 설명은 짧게, 용어는 풀어서.
- 주인은 PC 를 늘 쓰지 못한다(휴대폰으로 지시하는 일이 많다). 그래서 AI 가 끝까지 해 두는 것을 원한다.
- **변경할 때마다 커밋하고 푸시한다.** 병합은 주인이 한다. AI 가 PR 을 병합하지 않는다.
- 주인은 **자기 생각이라고 무비판적으로 받지 말고, 치명적 문제가 있으면 말하라**고 했다.
- 릴리스(GitHub Release)는 주인이 만든다. 판 번호는 `scripts/panel.py` 의 `KIT_VERSION` 과 `CHANGELOG.md`.
  (2026-09-29 바뀜: AI 환경은 태그 푸시·릴리스 API 가 막혀 있어 `.github/workflows/release.yml` 이 대신 만든다. CHANGELOG 를 고쳐 main 에 올리면
  릴리스가 없는 판마다 태그·릴리스가 생긴다. 새 판을 맨 위에 덧붙일 때 바로 아래 판 머리줄에 `(커밋 짧은해시)` 를 적어 둘 것.)

## 2. 원칙

1. **누군가 계속 관리해야 하는 것(서버·계정·유료 서비스)은 기본값이 될 수 없다.** 선택 사항까지만. 주인의 관리가 필요한 서비스도 안 된다.
2. **나무위키 전용 기능은 넣지 않는다**(데이터 받기, 동기화, P2P 는 유어위키 몫). 이 키트는 "빈 위키를 원터치로 띄우고, 다른 엔진·형식으로 옮기는" 범용 키트다.
3. **사용자에게 드러나는 것(공개 주소, IP)은 기본 꺼짐이고, 켜기 전에 무슨 일이 생기는지 알려 준다.**
4. **파이썬 표준 라이브러리만** 쓴다(Windows 임베디드 파이썬에 pip 없이). 외부 바이너리는 `sources.json` 에 해시와 함께.
5. **화면·기록은 한국어**, 비개발자가 읽을 수 있게.
6. **한 번 고른 설정은 재시작 뒤에도 유지**(관리판 `panel.json`, 리눅스 `anywiki.conf`, Docker 는 compose 환경 변수).
7. 내보내기에 **계정·IP·토론 표는 절대 넣지 않는다.**

## 3. 구조

| 포트 | 무엇 | 파일 |
|---|---|---|
| 4100 | 관리판(127.0.0.1 전용, Origin 검사) | `scripts/panel.py` (HTML·JS 가 파일 안 `PAGE` 문자열에 있음) |
| 4000 | 사용자에게 보이는 위키. openNAMU 면 오프라인 자원 치환·색·휴대폰 CSS, 다른 엔진이면 `--pass`(그대로 전달, Host 유지) | `scripts/offline_proxy.py` |
| 4001 | 지금 엔진(`wikis/엔진/`) | `scripts/engines/` |

(2026-09-29 바뀜: 0.1 은 openNAMU 하나였고 `wiki/` 에 있었다. 0.3 부터 엔진 4개, `wikis/엔진이름/`. `kit.migrate()` 가 옛 폴더를 옮긴다.)

- **공용 언어 통역기** `scripts/wikiconv/`: 형식마다 Reader(글 → 공통 구조 `Doc`)·Writer(공통 구조 → 글). `tree.py` 에 블록·인라인 노드 정의와
  `InlineScanner`·`build_lists`·`tidy`. 형식: namumark · mediawiki · dokuwiki · markdown · awm(확장 마크다운, 공통 구조의 글 형태) + `html_writer`.
  `wikiconv.convert(글, 원래형식, 새형식, 제목)`. 옮길 수 없는 것은 `raw` 노드(원문 보존). 파일 이름을 `ast.py` 로 하면 표준 라이브러리와 부딪힌다(`tree.py`).
- **엔진** `scripts/engines/`: 공통 틀 `base.Engine`(installed·install·command·spawn·ready·pages·get·put·put_many·changes_since·count·info·admin_password,
  `write_while_running`). `opennamu.py`(SQLite 직접, 켜져 있으면 쓰지 않음) · `markdown.py`(`scripts/mdwiki.py` 내장 서버의 Store) ·
  `dokuwiki.py`(파일, fnencode=utf-8, `anywiki_titles.json` 에 ID→제목, 첫 줄 H1, 딸려 온 `wiki:`·`playground:` 설명서는 안 고쳤으면 문서로 안 침) ·
  `mediawiki.py`(SQLite 직접 읽기, 쓰기는 공식 `maintenance/run.php edit|importDump`) · `php.py`(PHP 찾기·Windows 휴대용 PHP·`php -S` 명령).
- **받기** `scripts/fetch.py`: `download(url,dest,sha256)`, `docker_layer(repo,digest,…)`(Docker Hub 레지스트리에서 익명 토큰으로 층 하나를 받아 digest 확인 후 풂).
- **옮기기** `scripts/transfer.py export|import|switch <root> <형식|파일|엔진>`: 네 형식 파일 읽기·쓰기, `translate()`, 엔진 바꾸기(다 옮긴 뒤에만 설정의 엔진을 바꿈).
  openNAMU→openNAMU 는 역사까지 `wiki_pack.py` 로. `wiki_pack` 의 메타 표 이름 `yourwiki_pack` 은 유어위키와 파일을 주고받으려고 그대로 둔다.
- **명령줄** `scripts/kit.py install [엔진] | run-engine | engine [엔진] | info`. 지금 엔진 = 환경 변수 `ENGINE` > `panel.json` 의 `engine` > opennamu.
- 설치·켜기: Windows `애니위키.bat` → `panel_launch.ps1`(없으면 `install.ps1` 로 파이썬만) → `panel.py`(엔진 설치는 관리판이 `kit.py install`).
  리눅스 `server/install.sh [엔진]`, `server/anywiki.sh start|stop|status|switch|export|import|install-service`(프로세스 묶음으로 띄우고 묶음째 끔).
  Docker `docker/entrypoint.sh`(`ENGINE` 이 `wikis/.engine` 과 다르면 switch).
- 공개: `scripts/cloudflared.py`(빠른 터널). 새 판 알림: `scripts/update_check.py`(GitHub 최신 릴리스, 알리기만, 404=릴리스 없음).
- 플러그인: `Engine.plugins()/set_plugin()/search_plugins()/install_plugin()`, `plugin_search`·`plugin_note`. 관리판 `/api/plugins`(GET)·`/api/plugin`·
  `/api/plugin_search`·`/api/plugin_install`(→ `kit.py plugin install`, plugin.log). DokuWiki 저장소 주소는 `sources.json` 의 `plugin_repos`,
  시험 때는 `ANYWIKI_DOKU_REPO`(이때만 http 허용). 진짜 저장소(dokuwiki.org)는 이 환경에서 막혀 있어 API 모양(`fmt=json`, `q`, `ext[]`)은 문서 기준이다(주인 PC 에서 확인 필요).
- 공동위키 `scripts/cowiki.py <root> run|id|name|add|remove|list|sync`: 창구 HTTP(127.0.0.1:4002, `/cowiki/hello`, `/cowiki/changes?since=`),
  저장소 `wikis/_cowiki/cowiki.db`(members·journal(문서마다 마지막 판의 AWM)·applied(받아 넣은 판의 해시 — 다시 퍼뜨리지 않기)·meta).
  요청 서명 = `canonical({from,to,t,path})`, 응답 서명 = 본문 전체(`to`·`since` 포함). 엔진이 바뀌면 그때부터의 편집만 나눈다.
  관리판은 `cowiki` + `cowiki_tunnel`(4002 전용 cloudflared) 프로세스, 설정 `cowiki_on`. DHT 는 `dht.py`(salt `anywiki-cowiki`), 시험은 `tests/fake_dht.py`.
- 요구 명세: `docs/SPEC.md`(주인이 요구한 것 목록 + 구현 결정). 요구가 늘면 여기에 먼저 적는다.

## 4. 시험하는 법

- `python3 tests/run_all.py`: `test_cowiki.py`(두 위키 서로 등록·한쪽만 등록 거절·주고받기·되퍼뜨리지 않기·마지막 판·미래 시각·위조·가짜 DHT, `ANYWIKI_DOKU_LAYER` 가 있으면 B 는 DokuWiki), `test_pack.py`(openNAMU 형식 내보내기·가져오기), `test_wikiconv.py`(형식별 왕복·까다로운 글자),
  `test_engines.py`(마크다운 엔진, 4형식 내보내기→가져오기; `ANYWIKI_DOKU_LAYER=받아둔.tgz` 와 php 가 있으면 DokuWiki 바꾸기까지).
- `python3 -m pyflakes scripts/*.py scripts/engines/*.py scripts/wikiconv/*.py tests/*.py`, `bash -n server/*.sh docker/entrypoint.sh`.
- 실제 동작: 임시 폴더에 `scripts assets server docker sources.json` 을 복사하고, 받아 둔 층 파일(`tools/sha256_….tgz`)도 복사해 두면 다시 받지 않는다.
  `python3 scripts/panel.py --no-browser` → `curl -XPOST -H Origin:http://127.0.0.1:4100 127.0.0.1:4100/api/install?engine=markdown` → `/api/start` → 4000 번 확인.
  관리판 화면은 playwright(`/opt/pw-browsers/chromium`)로 찍는다.
- Windows(PowerShell·임베디드 파이썬·휴대용 PHP)는 이 환경에서 시험할 수 없다. 주인 PC 에서 확인해야 한다.

## 5. 환경에서 알게 된 것

- `pkill -f 패턴` 은 그 패턴이 들어간 내 셸까지 죽인다. pid 파일이나 /proc 검사로 끈다.
- 관리판을 고친 뒤 시험할 때 예전 관리판 프로세스가 4100 을 잡고 있지 않은지 확인한다.
- 리눅스에서는 `cleanup_leftovers()` 가 아무것도 안 한다(Windows 전용).
- 나무마크에서 백틱(`)은 문법을 막지 않는다. 문법 예시는 `{{{ }}}` 로 감싼다(첫 화면에서 분류가 실제로 붙던 문제).
- git 태그 푸시는 이 환경의 git 프록시가 끊는다(가지 푸시는 됨). 태그·릴리스는 주인이 만든다.
- `pgrep -f`/`pkill -f` 에 넣은 패턴이 내 명령줄에도 들어 있으면 내 셸이 죽는다(`ps -eo pid,cmd | grep` 로 pid 를 골라 끈다).
- 이 클라우드 환경에서는 dokuwiki.org · releases.wikimedia.org · windows.php.net · extdist.wmflabs.org 가 막혀 있다(다시 시도하지 말 것).
  Docker Hub 레지스트리(registry-1.docker.io, auth.docker.io)와 허용된 GitHub 저장소는 된다. 그래서 엔진 파일은 Docker Hub 이미지 층에서 받는다.
- 시스템 PHP 8.4 가 있다(`php -S`). `PHP_CLI_SERVER_WORKERS=4` 로 일꾼을 띄우므로 끌 때 프로세스 묶음째 꺼야 남지 않는다.
- MediaWiki importDump 는 XML 에 넣을 수 없는 제어 문자가 있으면 멈춘다(`CTRL` 로 지움). DokuWiki 는 URL 인코딩한 한글 파일 이름이 255바이트를 넘는다(fnencode=utf-8 + 긴 ID 는 sha1 꼬리).
- 관리판 요청 처리(do_POST) 안에서 `import re` 같은 지역 import 를 하면 다른 분기에서 NameError. 모듈 맨 위 import 를 쓴다.

## 6. 남은 일 (로드맵) — 끝내면 지우지 말고 [완료] 로 표시

- [완료 0.3] 엔진 고르기: DokuWiki·MediaWiki 도 원터치 설치·켜기(PHP, MediaWiki 는 SQLite). Markdown 내장 엔진도 추가.
- [완료 0.2·0.3] 각 엔진 형식으로 내보내기·가져오기, 엔진 바꾸기. (2026-09-29 바뀜: pandoc 안은 버리고 공용 언어(AWM) 통역기를 직접 만듦 —
  파이썬 표준 라이브러리만 쓰는 원칙 4, 그리고 나무마크를 pandoc 이 모름.)
- [완료 0.4] 엔진별 플러그인: DokuWiki(플러그인 저장소 API + zip 설치, 동봉 플러그인 켜기/끄기), MediaWiki(동봉 확장 켜기/끄기 = `write_extensions` + `update`),
  Markdown 내장(katex·highlight 켜기/끄기), openNAMU(없음). 가짜 저장소 서버로 시험.
- [완료 0.5] 공동위키: 서로 ID 를 등록한 위키끼리 편집 주고받기(유어위키의 Ed25519·DHT·터널 창구 재사용, 문서는 AWM 으로, 엔진이 달라도 됨).
  마지막에 쓴 판이 이김, 남에게서 받은 판은 다시 퍼뜨리지 않음.
- [ ] DokuWiki·MediaWiki 보안판 알림("새 판이 있다", 사용자가 버튼으로 올림 — 원칙 1).
- [ ] Windows 에서 실제 설치·켜기 확인, 특히 휴대용 PHP(주인 몫).
- [ ] GitHub 릴리스 만들기: 태그 v0.2·v0.3 에서(주인 몫).

## 7. 작업 기록 (새 항목을 위에 덧붙인다)

### 2026-10-02 — 0.5.1 (로컬 Windows 세션)
- 주인 요청: 유어위키와 주소(포트)가 같아 같이 못 켜므로 바꿈 → 관리판 4100, 위키 4000, 엔진 4001, 공동위키 4002. (유어위키는 3100·3000·3001·3002)
- 유어위키에서 고친 Windows 경로 버그(`file:` URI)를 여기도 고침. 시험은 `PYTHONUTF8=1 python tests/run_all.py`.
- 주인 말: 도쿠위키·미디어위키까지 다 지원하려던 건 욕심이었던 것 같다 → 유어위키에서 나무위키 동기화만 뺀 수준으로 안정화하는 방향(범위는 주인과 확인 중).

### 2026-09-29 — 릴리스 자동화
- 주인이 "왜 릴리스 못 하나" 물음. 이유: 이 환경의 git 프록시가 태그 푸시를 끊고, GitHub 도구에는 릴리스 만들기가 없으며 gh·API 토큰도 없다.
- 해결: GitHub Actions `release.yml` + `.github/release.py`(CHANGELOG 의 판마다 `gh release create`, 이미 있으면 건너뜀). CHANGELOG 머리줄에 판별 커밋을 적음.
- 릴리스에 받을 파일 `anywiki-kit-판.zip`(git archive, `.gitattributes` 의 export-ignore 로 시험·AI 문서 뺌)과 받는 법을 붙임. 이미 있는 릴리스에도 붙인다.

### 2026-09-29 — 0.5 공동위키
- `cowiki.py`, 관리판 공동위키 칸, 리눅스 `COWIKI`·`COWIKI_URL`·`anywiki.sh cowiki`, Docker `COWIKI`. `dht.py`·`ed25519.py` 유어위키에서 가져옴.
- 확인: `test_cowiki.py`(Markdown↔Markdown, Markdown↔DokuWiki), 리눅스 스크립트로 켠 A(Markdown)와 B(DokuWiki) 사이 실제 주고받기,
  관리판 화면. 이 환경에서는 trycloudflare 가 403, DHT(UDP)가 막혀 있어 실제 인터넷 경로는 확인하지 못했다(주인 PC 에서 확인 필요).
- 주인의 요구 중 치명적일 수 있는 점(주인에게 알림): 회원은 내 위키의 어떤 문서든 덮어쓸 수 있다(마지막 판 우선). 믿는 위키만 등록해야 한다.
  지우기는 옮기지 않으므로 지운 문서가 상대에게서 다시 올 수 있다.

### 2026-09-29 — 0.4 엔진별 플러그인
- DokuWiki(동봉 켜고 끄기 + 저장소 설치), MediaWiki(동봉 확장 34개 켜고 끄기), Markdown(수식·코드 색칠). 관리판 플러그인 칸, `kit.py plugin`, `anywiki.sh plugin`.
- 확인: 관리판 화면(MediaWiki 확장 목록, 한국어 설명), Poem 끄기, 다른 Origin 에서 온 요청 403, 관리판 SIGTERM 때 엔진·중계 서버도 꺼짐.
  가짜 저장소로 DokuWiki 설치·거절 시험.
- 태그 v0.2·v0.3 은 로컬에만 있다(푸시가 막힘). 주인이 GitHub 에서 커밋 7513dc8(0.2)·8dd3516(0.3)·이 커밋(0.4)으로 릴리스를 만들면 된다.

### 2026-09-29 — 0.2 공용 언어 통역기, 0.3 엔진 4개·엔진 바꾸기
- 주인 요구(원문 요약은 `docs/SPEC.md`): 도쿠·미디어·오픈나무·마크다운으로 쓰고 내보내기·가져오기, 키트 안에서 형식 바꾸기, 가운데 공용 언어(확장 마크다운, 보이지 않게),
  엔진별 플러그인, 공동위키(서로 ID 등록), 임시 주소 공개 유지, README·커밋·릴리스로 이력 관리, AI 혼자 구현.
- 0.2: `wikiconv`(AST + AWM). 실제 문서 21,707개를 6형식으로 오가며 낱말 손실을 재고 고침(자세한 목록은 커밋 기록).
- 0.3: `engines/`, `mdwiki.py`, `fetch.py`, `transfer.py`, `kit.py`, 관리판 다시 씀(엔진 칸), 리눅스·Docker 엔진 대응, 시험 `test_engines.py`.
- 확인: 관리판으로 Markdown 설치 → 켜기 → DokuWiki 로 바꾸기 → MediaWiki 로 바꾸기(첫 화면이 '대문'으로), 리눅스 스크립트 Markdown ↔ DokuWiki,
  Docker 시작 스크립트 흉내(ENGINE 을 바꿔 다시 시작하면 옮김). 1,500 문서로 openNAMU → Markdown → DokuWiki → MediaWiki → openNAMU 한 바퀴.
- 결정: 릴리스는 태그만(v0.2 = 통역기 커밋, v0.3 = 이 커밋). GitHub 릴리스 페이지는 주인이 만든다. (2026-09-29 바뀜: 태그 푸시가 막혀 커밋 번호로 적음)

### 2026-09-29 — 첫 판(유어위키 1.2 에서 갈라짐)
- 유어위키에서 가져온 것: 관리판(설정 유지·칸 접기·공개·새 판 알림), 오프라인 중계 서버, 내보내기(4형식), openNAMU 가져오기, 리눅스·Docker 스크립트, 설치 틀.
- 뺀 것: 나무위키 덤프·틀 설치, 갱신기(동기화)·갱신 단추, html2namu, P2P·DHT·직접 연결·중계소, 가져오기 검증(나무위키 대조), 범위 선택('설치한 판 이후'는 덤프 기준이라 의미 없음).
- 바꾼 것: 설치는 파이썬 + openNAMU 만(7zr·aria2 불필요), 첫 화면은 FrontPage 안내 문서, 라이선스 문구는 중립(운영자가 정함),
  내보내기 파일 이름 `anywiki-…`, MediaWiki 사이트 이름은 위키 설정(`other.name`)에서, 리눅스 `anywiki.sh` 에 `TUNNEL=on`,
  문서 수는 `count(*)` 로 세고 가져오기 뒤 `count_all_title` 도 맞춤.
- 고친 버그(유어위키에도 있음): 관리판의 설치 기록과 가져오기 기록이 같은 id(`ilog`)를 써서 서로 덮어씀 → `inslog`·`implog`.
- 확인: 리눅스에서 실제로 설치 → 켜기 → 4형식 내보내기 → 유어위키가 내보낸 파일 가져오기(217개) → 문서 수 218 → 첫 화면 화면 확인.
