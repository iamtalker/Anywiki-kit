# 애니위키 키트 (Anywiki-kit)

누구나 자기 컴퓨터나 서버에 **나만의 위키**를 원터치로 띄울 수 있게 해 주는 도구입니다.
위키 엔진은 [openNAMU](https://github.com/openNAMU/openNAMU)(나무마크 문법)이고, 관리판에서 켜기·끄기, 인터넷 공개,
다른 위키(MediaWiki·DokuWiki·Markdown)로 내보내기, openNAMU 형식 가져오기를 합니다.
**누구의 서버도 필요 없습니다.** 키트는 공식 배포처에서 프로그램을 받아 해시로 검증할 뿐, 제작자는 서버를 운영하지 않습니다.

> [유어위키](https://github.com/iamtalker/yourwiki)(나무위키 전체를 내 위키로)에서 나무위키 전용 기능(데이터·동기화·P2P)을 뺀 범용판입니다.

## 사용법 (Windows)

1. 이 폴더를 원하는 곳에 둡니다.
2. **`애니위키.bat`** 을 더블클릭하면 브라우저에 **관리판**이 열립니다(처음엔 파이썬을 먼저 받습니다, 약 20MB).
3. 관리판의 **설치 → [설치]** 를 누릅니다. 위키 엔진을 받고 빈 위키와 첫 화면을 만듭니다(몇 분).
4. **[켜기]** → "위키 준비됨"이 뜨면 **[위키 열기]**.
5. 끌 때는 **[끄기]** 를 누른 뒤 관리판 창을 닫으세요. 그냥 닫았더라도 다음에 관리판을 열 때 남은 프로그램을 정리합니다.

- 처음 가입한 사람이 관리자가 됩니다. 공개하기 전에 먼저 가입하고, 관리자 설정에서 편집 권한과 위키 이름을 정하세요.
- 관리판에서 고른 설정(색, 공개 등)은 재시작해도 그대로입니다(`panel.json`). 위키를 켜 둔 채 끝냈으면 다음에 관리판을 열 때 다시 켜집니다.
- 관리판은 기능별 칸으로 접혀 있고, 제목을 누르면 펼쳐집니다.

설치 후에는 인터넷 없이도 동작하고, 문서를 볼 때 외부 서비스에 접속하지 않습니다.
openNAMU 가 원래 CDN 에서 불러오던 파일을 중계 서버(`scripts/offline_proxy.py`)가 동봉 파일(`assets/`)로 바꾸고,
영상·SNS 삽입은 "▶ ○○에서 보기" 링크로 바꿉니다(누를 때만 외부로 연결). 문서 원문은 바뀌지 않습니다.
중계 서버는 머리글 색, 휴대폰 화면 다듬기, 검색창 제목 자동완성, 아무 문서나 보기 단추도 붙입니다.

## 무엇을 받아 오나

| 항목 | 출처 | 검증 |
|---|---|---|
| openNAMU (위키 엔진, BSD-3) | github.com/openNAMU | SHA-256 |
| 파이썬 임베디드판 (Windows) | python.org | SHA-256 |
| cloudflared ([공개하기]를 쓸 때만) | github.com/cloudflare | SHA-256 |

받을 곳과 해시는 `sources.json` 에 있습니다. 동봉한 것: `assets/`(KaTeX·highlight.js 등 MIT/BSD, Material Icons Apache-2.0).

## 인터넷에 공개하려면

- **간단히**: 관리판의 **인터넷에 공개 → [공개하기]**. 공유기 설정 없이 Cloudflare 임시 주소(https)가 생깁니다. 켤 때마다 주소가 바뀌고,
  [공개 끄기]를 누르기 전까지는 위키를 켤 때마다 다시 공개됩니다.
- **직접**: `panel.json` 의 `listen` 을 `0.0.0.0:3000` 으로 바꾸거나 아래처럼 리눅스·Docker 로 서버에 올립니다.

공개하는 순간 **그 사이트의 운영 책임은 공개한 사람에게** 있습니다(권리 침해·게시중단 요청 대응 등).

## 내보내기 · 가져오기

관리판의 **내보내기**에서 위키를 파일로 만들어 `export/` 폴더에 저장합니다.

- **openNAMU**: `anywiki-opennamu.db` — openNAMU 의 `data.db` 와 같은 SQLite. 문서 표(data·history·data_set·back)만 담고
  사용자 계정·접속 기록·토론은 넣지 않습니다. 백업이나 다른 애니위키로 옮길 때 쓰고, 새 openNAMU 의 `data.db` 로 그대로 써도 됩니다.
- **MediaWiki**: `anywiki-mediawiki.xml.gz` → `php maintenance/run.php importDump --report 파일`.
- **DokuWiki**: `anywiki-dokuwiki.zip` → DokuWiki 폴더에 `data/` 를 덮어 풀고 `php bin/indexer.php`.
- **Markdown**: `anywiki-markdown.zip` → 문서마다 `.md` 하나. Obsidian 같은 편집기에서 폴더째 엽니다.
- 표·목록·각주·접기·틀 등 흔한 문법을 옮기고, 이미지와 `#!html` 은 옮기지 않습니다. 틀 문법은 엔진마다 달라 일부는 손으로 고쳐야 할 수 있습니다.

**가져오기 (openNAMU 형식)**: 받은 파일(애니위키·유어위키가 내보낸 것이나 다른 openNAMU 의 `data.db`)을 `import/` 폴더에 넣고,
위키를 끈 뒤 관리판의 **가져오기**에서 고릅니다. 문서마다 내 쪽보다 새 판만 역사 뒤에 이어 붙이고, 내 쪽이 같거나 더 새로우면 건너뜁니다
(지우기는 옮기지 않음). 가져온 판의 역사 요약에는 `[가져옴 파일이름]` 이 붙습니다. 파일 내용은 검증하지 않으니 믿을 수 있는 파일만 넣으세요.

명령줄: `python scripts/wiki_pack.py export wiki`, `python scripts/wiki_pack.py import wiki 파일.db`,
`python scripts/convert_wiki.py wiki --to mediawiki|dokuwiki|markdown [--out 파일] [--jobs CPU수]`.

## 리눅스 서버에 설치하기

윈도우에서 **`서버설치가이드.bat`** 을 누르면 이 안내를 보기 좋게 정리한 페이지가 열립니다. 필요한 것: python3(3.8 이상), curl.

```bash
git clone https://github.com/iamtalker/anywiki-kit && cd anywiki-kit
bash server/install.sh                  # 엔진 받기·해시 검증·빈 위키 만들기 (몇 분)
bash server/anywiki.sh start            # 켜기 (0.0.0.0:3000)
bash server/anywiki.sh status           # 상태
sudo bash server/anywiki.sh install-service   # 부팅 때 자동 시작(systemd)
```

- 환경 변수: `LISTEN`(기본 `0.0.0.0:3000`), `TUNNEL=on`(Cloudflare 임시 주소로 공개, 주소는 `status`), `UPDATE_NOTICE=off`.
  한 번 준 값은 `anywiki.conf` 에 기억되어 다음부터 그냥 `start` 해도 그대로입니다(systemd 서비스도 이 파일을 따름).
- HTTPS 는 nginx·Caddy 같은 역방향 프록시를 3000번 앞에 두면 됩니다.

## Docker

```bash
git clone https://github.com/iamtalker/anywiki-kit && cd anywiki-kit
docker compose up -d        # 처음엔 엔진 받기로 몇 분
```

`PORT`(바깥 포트, 기본 3000), `COLOR`(머리글 색), `UPDATE_NOTICE` 로 설정합니다. 위키는 `./anywiki-data/wiki` 에 저장됩니다.

## 새 판 알림

관리판은 12시간에 한 번 GitHub(`iamtalker/anywiki-kit`)의 **최신 릴리스**를 확인해 새 판이 나오면 알려 줍니다.
**알리기만 하고 스스로 설치하지 않습니다.** 보내는 정보는 없고, 관리판의 '새 판 알림'에서 끌 수 있습니다.

## 라이선스

키트 코드는 MIT(`LICENSE`). 위키 문서의 저작권과 라이선스는 위키 운영자가 정합니다. 자세한 출처는 `NOTICE.md`.

## 변경 기록

[CHANGELOG.md](CHANGELOG.md)
