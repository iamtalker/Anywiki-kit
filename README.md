# 애니위키 키트 (Anywiki-kit)

누구나 자기 컴퓨터나 서버에 **나만의 위키(openNAMU)** 를 원터치로 띄울 수 있게 해 주는 도구입니다.
관리판에서 설치·켜기·끄기·인터넷 임시 공개를 하고, 위키 문서를 **openNAMU · MediaWiki · DokuWiki · Markdown** 형식으로
**내보내고 가져올 수 있습니다**(문서를 새 형식의 문법으로 자동 통역).
**누구의 서버도 필요 없습니다.** 키트는 공식 배포처에서 프로그램을 받아 해시로 검증할 뿐, 제작자는 서버를 운영하지 않습니다.

> [유어위키](https://github.com/iamtalker/yourwiki)(나무위키 전체를 내 위키로)에서 나무위키 전용 기능(데이터·동기화·P2P)을 뺀 범용판입니다.
> 유어위키와 **같은 컴퓨터에서 함께 켤 수 있도록** 주소(포트)를 달리 씁니다: 관리판 `4100`, 위키 `4000`(유어위키는 `3100`·`3000`).

## 사용법 (Windows)

1. 이 폴더를 원하는 곳에 둡니다.
2. **`애니위키.bat`** 을 더블클릭하면 브라우저에 **관리판**(`http://127.0.0.1:4100`)이 열립니다(처음엔 파이썬을 먼저 받습니다, 약 20MB).
3. 관리판의 **설치** 칸에서 **[설치]** 를 누릅니다(몇 분).
4. **[켜기]** → "위키 준비됨"이 뜨면 **[위키 열기]**(`http://127.0.0.1:4000`).
5. 끌 때는 **[끄기]** 를 누른 뒤 관리판 창을 닫으세요. 그냥 닫았더라도 다음에 관리판을 열 때 남은 프로그램을 정리합니다.

- 관리판에서 고른 설정(색, 공개 등)은 재시작해도 그대로입니다(`panel.json`). 위키를 켜 둔 채 끝냈으면 다음에 관리판을 열 때 다시 켜집니다.
- openNAMU 는 위키에서 **처음 가입한 사람이 관리자**가 됩니다. 공개하기 전에 관리자 설정에서 편집 권한을 정하세요.

설치 후에는 인터넷 없이도 동작합니다. openNAMU 는 원래 CDN 에서 불러오던 파일을 중계 서버(`scripts/offline_proxy.py`)가
동봉 파일(`assets/`)로 바꾸고, 머리글 색·휴대폰 화면·검색 자동완성도 붙입니다.

## 무엇을 받아 오나

| 항목 | 출처 | 검증 |
|---|---|---|
| openNAMU (BSD-3) | github.com/openNAMU | SHA-256 |
| 파이썬 임베디드판 (Windows) | python.org | SHA-256 |
| cloudflared ([공개하기]를 쓸 때만) | github.com/cloudflare | SHA-256 |

받을 곳과 해시는 `sources.json` 에 있습니다. 동봉한 것: `assets/`(KaTeX·highlight.js 등 MIT/BSD, Material Icons Apache-2.0).

## 내보내기 · 가져오기와 통역기

관리판의 **내보내기**에서 위키의 모든 문서를 고른 형식으로 통역해 `export/` 폴더에 저장합니다.

- **openNAMU**: `anywiki-opennamu.db` — openNAMU 의 `data.db` 와 같은 SQLite(문서 표만, 계정·접속 기록·토론 없음). 역사까지 담깁니다.
- **MediaWiki**: `anywiki-mediawiki.xml.gz` → `php maintenance/run.php importDump 파일`.
- **DokuWiki**: `anywiki-dokuwiki.zip` → DokuWiki 폴더에 `data/` 를 덮어 풀고 `php bin/indexer.php`.
- **Markdown**: `anywiki-markdown.zip` → 문서마다 `.md` 하나.

**가져오기**: openNAMU(`.db`) · MediaWiki(`.xml`, `.xml.gz`) · DokuWiki(`.zip`) · Markdown(`.zip`, `.md`) 파일을 `import/` 폴더에 넣고
관리판의 **가져오기**에서 고릅니다. 나무마크로 통역해 넣고, 같은 문서가 내 쪽에 더 새로 있으면 건너뜁니다.
가져온 판의 역사 요약에는 `[가져옴 파일이름]` 이 붙습니다. 위키를 끈 상태에서만 가져옵니다. 파일 내용은 검증하지 않으니 믿을 수 있는 파일만 넣으세요.

속으로는 모든 문법을 한 번 **공용 언어(AWM, 확장 마크다운)** 로 읽은 뒤 새 문법으로 씁니다(`scripts/wikiconv/`).

- 제목·문단·굵게/기울임/밑줄/취소선·링크·목록·표(합친 칸 포함)·각주·목차·분류·넘겨주기·코드·수식·접기·틀 호출을 옮깁니다.
- 옮길 수 없는 문법(엔진 전용 HTML 등)은 글자만 남기거나 원문 보존 블록으로 감쌉니다. 틀(템플릿)의 **내용**은 엔진마다 달라 손으로 고쳐야 할 수 있습니다.
- 실제 위키 문서 2만여 개로 시험해, DokuWiki·MediaWiki 로 옮겼을 때 문서의 98% 가 낱말의 90% 이상을 그대로 지녔습니다. 이미지 파일은 옮기지 않습니다.

명령줄: `python scripts/transfer.py export . markdown`, `python scripts/transfer.py import . 파일`.
통역기만 쓰려면 파이썬에서 `wikiconv.convert(글, "namumark", "mediawiki")`(형식: namumark · mediawiki · dokuwiki · markdown · awm).

## 인터넷에 공개하려면

- **간단히**: 관리판의 **인터넷에 공개 → [공개하기]**. 공유기 설정 없이 Cloudflare 임시 주소(https)가 생깁니다. 켤 때마다 주소가 바뀌고,
  [공개 끄기]를 누르기 전까지는 위키를 켤 때마다 다시 공개됩니다.
- **직접**: `panel.json` 의 `listen` 을 `0.0.0.0:4000` 으로 바꾸거나 아래처럼 리눅스·Docker 로 서버에 올립니다.

공개하는 순간 **그 사이트의 운영 책임은 공개한 사람에게** 있습니다(권리 침해·게시중단 요청 대응 등).

## 리눅스 서버에 설치하기

윈도우에서 **`서버설치가이드.bat`** 을 누르면 이 안내를 보기 좋게 정리한 페이지가 열립니다.
필요한 것: python3(3.8 이상).

```bash
git clone https://github.com/iamtalker/anywiki-kit && cd anywiki-kit
bash server/install.sh                  # openNAMU 받기
bash server/anywiki.sh start            # 켜기 (0.0.0.0:4000)
bash server/anywiki.sh status           # 상태·문서 수
bash server/anywiki.sh export markdown  # export/ 에 내보내기
bash server/anywiki.sh import 파일      # 가져오기(위키를 끈 상태에서)
sudo bash server/anywiki.sh install-service   # 부팅 때 자동 시작(systemd)
```

- 환경 변수: `LISTEN`(기본 `0.0.0.0:4000`), `TUNNEL=on`(Cloudflare 임시 주소로 공개, 주소는 `status`), `UPDATE_NOTICE=off`.
  한 번 준 값은 `anywiki.conf` 에 기억되어 다음부터 그냥 `start` 해도 그대로입니다(systemd 서비스도 이 파일을 따름).
- HTTPS 는 nginx·Caddy 같은 역방향 프록시를 4000번 앞에 두면 됩니다.

## Docker

```bash
git clone https://github.com/iamtalker/anywiki-kit && cd anywiki-kit
docker compose up -d        # 처음엔 openNAMU 받기로 몇 분
```

`PORT`(바깥 포트, 기본 4000), `COLOR`(머리글 색), `UPDATE_NOTICE` 로 설정합니다. 위키는 `./anywiki-data/wikis` 에 저장됩니다.
관리자는 위키에서 처음 가입한 사람입니다.

## 새 판 알림

관리판은 12시간에 한 번 GitHub(`iamtalker/anywiki-kit`)의 **최신 릴리스**를 확인해 새 판이 나오면 알려 줍니다.
**알리기만 하고 스스로 설치하지 않습니다.** 보내는 정보는 없고, 관리판의 '새 판 알림'에서 끌 수 있습니다.

## 이전 판(0.5 이하)에서 올릴 때

0.6 부터 위키 엔진은 openNAMU 하나입니다(Markdown·DokuWiki·MediaWiki 엔진과 공동위키, 플러그인 칸은 뺐습니다).
openNAMU 를 쓰던 위키는 `wikis/opennamu/` 가 그대로라 새 판을 덮어 풀면 됩니다. 다른 엔진을 쓰던 위키는 **0.5.1 에서 openNAMU 로 바꾼 뒤** 올리거나,
0.5.1 의 관리판에서 내보내기(openNAMU 형식)한 파일을 새 판에서 **가져오기** 하세요. 0.5.1 은 [릴리스 v0.5.1](https://github.com/iamtalker/Anywiki-kit/releases/tag/v0.5.1) 에 있습니다.
포트는 0.5.1 부터 4100(관리판)·4000(위키)입니다.

## 폴더

- `wikis/opennamu/` — openNAMU 프로그램과 위키 데이터. 0.1 의 `wiki/` 는 처음 켤 때 여기로 옮겨집니다.
- `export/`, `import/` — 내보낸 파일, 가져올 파일. `tools/` — 받은 도구(파이썬 등).
- 요구 명세: [docs/SPEC.md](docs/SPEC.md)

## 라이선스

키트 코드는 MIT(`LICENSE`). 위키 문서의 저작권과 라이선스는 위키 운영자가 정합니다. 자세한 출처는 `NOTICE.md`.

## 변경 기록

[CHANGELOG.md](CHANGELOG.md)
