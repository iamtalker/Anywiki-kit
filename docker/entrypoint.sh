#!/usr/bin/env bash
# 컨테이너 시작: 처음이면 설치(엔진 받기, 해시 검증, 빈 위키 만들기) → 위키 엔진·중계 서버 실행
set -euo pipefail
cd /kit

# 위키 색 (중계 서버가 panel.json 의 color 를 읽는다)
if [[ "$COLOR" =~ ^#[0-9a-fA-F]{6}$ ]]; then echo "{\"color\": \"$COLOR\"}" > panel.json; fi

if [ ! -f wiki/data.db ] || [ ! -x wiki/main.bin ]; then
  echo "== 처음 실행: 위키 엔진을 받고 빈 위키를 만듭니다 (몇 분)"
  bash server/install.sh
fi

[ "${UPDATE_NOTICE:-on}" = on ] && python3 scripts/update_check.py --quiet || true   # 새 판이 있을 때만 한 줄

(cd wiki && ./main.bin 3001 --localhost) &
echo "== 애니위키: http://<서버 주소>:${LISTEN##*:}"
exec python3 scripts/offline_proxy.py assets --listen "$LISTEN" --upstream 127.0.0.1:3001 --wiki-db wiki/data.db
