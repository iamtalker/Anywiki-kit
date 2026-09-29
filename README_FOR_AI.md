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
| 3100 | 관리판(127.0.0.1 전용) | `scripts/panel.py` (HTML·JS 가 파일 안 `PAGE` 문자열에 있음) |
| 3000 | 사용자에게 보이는 위키(오프라인 자원 치환, 색, 휴대폰 CSS, 검색 자동완성) | `scripts/offline_proxy.py` |
| 3001 | openNAMU 위키 엔진(바이너리, `wiki/`) | 설치가 받아 옴 |

- 설치: Windows `scripts/install.ps1`(파이썬 → openNAMU → 빈 위키 → `add_frontpage.py`), 리눅스 `server/install.sh`, Docker `docker/entrypoint.sh`.
  openNAMU 는 처음 켤 때 `data.db` 를 스스로 만든다.
- 켜기·끄기: Windows 관리판(`애니위키.bat` → `panel_launch.ps1` → `panel.py`), 리눅스 `server/anywiki.sh start|stop|status|install-service`.
- 내보내기: `scripts/convert_wiki.py`(나무마크 → MediaWiki/DokuWiki/Markdown, 멀티프로세스), `scripts/wiki_pack.py`(openNAMU SQLite 내보내기·가져오기).
  `wiki_pack` 의 메타 표 이름 `yourwiki_pack` 은 유어위키와 파일을 주고받으려고 일부러 그대로 둔다.
- 공개: `scripts/cloudflared.py`(빠른 터널). 새 판 알림: `scripts/update_check.py`(GitHub 최신 릴리스, 알리기만).

## 4. 시험하는 법

- `python3 tests/run_all.py` (지금: `test_pack.py` — 내보내기·가져오기·계정 표 제외·문서 수 갱신).
- `python3 -m pyflakes scripts/*.py tests/*.py`, `bash -n server/*.sh docker/entrypoint.sh` 통과.
- 실제 동작: 임시 폴더에 복사해 `bash server/install.sh` → `python3 scripts/panel.py` → `/api/start` → 3000 번 확인.
  관리판 화면은 playwright(`/opt/pw-browsers/chromium`)로 찍는다. 이 클라우드 환경에서는 GitHub 에서 엔진을 받을 수 있다.
- Windows(PowerShell·임베디드 파이썬)는 이 환경에서 시험할 수 없다. 주인 PC 에서 확인해야 한다.

## 5. 환경에서 알게 된 것

- `pkill -f 패턴` 은 그 패턴이 들어간 내 셸까지 죽인다. pid 파일이나 /proc 검사로 끈다.
- 관리판을 고친 뒤 시험할 때 예전 관리판 프로세스가 3100 을 잡고 있지 않은지 확인한다.
- 리눅스에서는 `cleanup_leftovers()` 가 아무것도 안 한다(Windows 전용).
- 나무마크에서 백틱(`)은 문법을 막지 않는다. 문법 예시는 `{{{ }}}` 로 감싼다(첫 화면에서 분류가 실제로 붙던 문제).
- 관리판 요청 처리(do_POST) 안에서 `import re` 같은 지역 import 를 하면 다른 분기에서 NameError. 모듈 맨 위 import 를 쓴다.

## 6. 남은 일 (로드맵) — 끝내면 지우지 말고 [완료] 로 표시

- [ ] 엔진 고르기: DokuWiki·MediaWiki 도 원터치 설치·켜기(휴대용 PHP + MediaWiki 는 SQLite). 주인이 원한 다음 단계.
- [ ] 각 엔진 원래 형식으로 내보내기·가져오기, 그리고 엔진 바꾸기(내보내기 → 변환 → 새 엔진에 넣기, 원본은 백업).
  변환은 pandoc(MediaWiki·DokuWiki·Markdown 끼리)을 쓰고, 나무마크 → 다른 형식은 지금 변환기, 다른 형식 → 나무마크는 새로 만드는 안을 제안해 둠.
  역사는 기본은 최신판만. MediaWiki 틀·파서 함수는 옮기면 일부 깨진다는 것을 관리판에 알린다.
  DokuWiki·MediaWiki 보안판은 "새 판이 있다"고 알리고 사용자가 버튼으로 올리게 한다(원칙 1).
- [ ] Windows 에서 실제 설치·켜기 확인(주인 몫).
- [ ] 첫 릴리스 v0.1(주인 몫).

## 7. 작업 기록 (새 항목을 위에 덧붙인다)

### 2026-09-29 — 첫 판(유어위키 1.2 에서 갈라짐)
- 유어위키에서 가져온 것: 관리판(설정 유지·칸 접기·공개·새 판 알림), 오프라인 중계 서버, 내보내기(4형식), openNAMU 가져오기, 리눅스·Docker 스크립트, 설치 틀.
- 뺀 것: 나무위키 덤프·틀 설치, 갱신기(동기화)·갱신 단추, html2namu, P2P·DHT·직접 연결·중계소, 가져오기 검증(나무위키 대조), 범위 선택('설치한 판 이후'는 덤프 기준이라 의미 없음).
- 바꾼 것: 설치는 파이썬 + openNAMU 만(7zr·aria2 불필요), 첫 화면은 FrontPage 안내 문서, 라이선스 문구는 중립(운영자가 정함),
  내보내기 파일 이름 `anywiki-…`, MediaWiki 사이트 이름은 위키 설정(`other.name`)에서, 리눅스 `anywiki.sh` 에 `TUNNEL=on`,
  문서 수는 `count(*)` 로 세고 가져오기 뒤 `count_all_title` 도 맞춤.
- 고친 버그(유어위키에도 있음): 관리판의 설치 기록과 가져오기 기록이 같은 id(`ilog`)를 써서 서로 덮어씀 → `inslog`·`implog`.
- 확인: 리눅스에서 실제로 설치 → 켜기 → 4형식 내보내기 → 유어위키가 내보낸 파일 가져오기(217개) → 문서 수 218 → 첫 화면 화면 확인.
