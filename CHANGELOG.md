# 변경 기록

버전마다 달라진 점을 여기에 적습니다. 새 버전이 위에 옵니다.

## 0.1 — 2026-09-29 (첫 판, 아직 릴리스 전)
[유어위키](https://github.com/iamtalker/yourwiki) 1.2 에서 갈라져 나옴. 나무위키 전용 기능(데이터 설치, 최신판 동기화, 갱신 단추, P2P 공유, 중계소)을 빼고 범용 위키 키트로 만듦.
- 원터치 설치: openNAMU 엔진을 받아 해시로 검증하고 빈 위키와 첫 화면(FrontPage)을 만듦(Windows 관리판, 리눅스 `server/install.sh`, Docker).
- 관리판: 켜기·끄기, 위키 색, 인터넷에 공개(Cloudflare 임시 주소), 내보내기, 가져오기, 새 판 알림, 설치. 기능별 칸 접기, 설정 유지.
- 내보내기: openNAMU(SQLite, 문서 표만) · MediaWiki · DokuWiki · Markdown. 가져오기: openNAMU 형식(내 쪽보다 새 판만 이어 붙임).
- 오프라인 중계 서버: CDN 자원을 동봉 파일로, 외부 삽입은 링크로, 머리글 색·휴대폰 화면·검색 자동완성·아무 문서나 보기.
- 리눅스: `server/anywiki.sh`(설정은 `anywiki.conf` 에 기억, `TUNNEL=on` 으로 임시 주소 공개).
