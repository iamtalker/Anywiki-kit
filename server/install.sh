#!/usr/bin/env bash
# 애니위키 키트 리눅스 설치: 고른 위키 엔진을 받아 빈 위키와 첫 화면까지 만든다
#
#   bash server/install.sh [엔진]      # 엔진: opennamu(기본) · markdown · dokuwiki · mediawiki
#
# 필요한 것: python3(3.8+). DokuWiki·MediaWiki 는 PHP 8.1+ 와 확장 몇 개가 더 필요하다(없으면 설치 명령을 알려 줌).
# 이미 끝난 단계는 건너뛰므로, 중간에 끊겨도 다시 실행하면 이어서 진행합니다.
set -euo pipefail
KIT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KIT"
command -v python3 >/dev/null || { echo "python3 이 없습니다. 예) sudo apt install python3" >&2; exit 1; }
export PYTHONUTF8=1
ENGINE="${1:-${ENGINE:-$(python3 scripts/kit.py engine)}}"
python3 scripts/kit.py install "$ENGINE"
python3 scripts/kit.py engine "$ENGINE" >/dev/null   # 지금 엔진으로 정해 둔다
if [ -f anywiki.conf ]; then sed -i '/^ENGINE=/d' anywiki.conf; fi   # 예전에 기억한 엔진은 지운다(위 설정을 따름)

cat <<'MSG'

설치 완료.
  켜기:        bash server/anywiki.sh start
  상태·끄기:   bash server/anywiki.sh status | stop
  엔진 바꾸기: bash server/anywiki.sh switch dokuwiki      (문서를 통역해 옮김)
  부팅 시 자동 시작(systemd): sudo bash server/anywiki.sh install-service
MSG
