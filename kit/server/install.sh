#!/usr/bin/env bash
# 애니위키 키트 리눅스 설치: 위키 엔진(openNAMU)을 받아 빈 위키와 첫 화면까지 만든다
#
#   bash server/install.sh
#
# 필요한 것: python3(3.8+).
# 이미 끝난 단계는 건너뛰므로, 중간에 끊겨도 다시 실행하면 이어서 진행합니다.
set -euo pipefail
KIT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KIT"

# 위키 데이터(wikis)는 kit 밖(최상위)에 둔다. 아래 스크립트는 kit 기준 상대 경로 wikis/ 를 쓰므로 kit/wikis 를 그곳으로 이어 준다.
# (kit/wikis 가 이미 폴더이면 — 도커 볼륨 — 그대로 쓴다)
TOP="$(cd "$KIT/.." && pwd)"
if [ ! -e "$KIT/wikis" ]; then mkdir -p "${ANYWIKI_DATA_DIR:-$TOP/wikis}"; ln -s "${ANYWIKI_DATA_DIR:-$TOP/wikis}" "$KIT/wikis"; fi
command -v python3 >/dev/null || { echo "python3 이 없습니다. 예) sudo apt install python3" >&2; exit 1; }
export PYTHONUTF8=1
python3 scripts/kit.py install
if [ -f anywiki.conf ]; then sed -i '/^ENGINE=/d' anywiki.conf; fi   # 예전 판이 기억한 엔진 설정은 지운다

cat <<'MSG'

설치 완료.
  켜기:        bash server/anywiki.sh start
  상태·끄기:   bash server/anywiki.sh status | stop
  부팅 시 자동 시작(systemd): sudo bash server/anywiki.sh install-service
MSG
