#!/usr/bin/env bash
# 컨테이너 시작: 처음이면 openNAMU 를 받아 설치하고 켠다
set -euo pipefail
cd /kit
ENGINE=opennamu
export ENGINE

# 0.1 의 볼륨(/kit/wiki)을 그대로 붙여 두었으면 옮겨 온다
if [ -f wiki/data.db ] && [ ! -e wikis/opennamu/data.db ]; then
  echo "== 예전 위키(/kit/wiki)를 wikis/opennamu 로 복사합니다"
  mkdir -p wikis/opennamu && cp -a wiki/. wikis/opennamu/
fi

# 위키 색(중계 서버가 panel.json 의 color 를 읽는다)
if [[ "${COLOR:-}" =~ ^#[0-9a-fA-F]{6}$ ]]; then echo "{\"color\": \"$COLOR\"}" > panel.json; fi

if ! python3 -c "import sys; sys.path.insert(0,'scripts'); import engines; sys.exit(0 if engines.get('opennamu','.').installed() else 1)"; then
  echo "== 처음 실행: openNAMU 를 받고 빈 위키를 만듭니다 (몇 분)"
  python3 scripts/kit.py install
fi
python3 scripts/kit.py info | grep -E '"(docs|admin)"' || true

[ "${UPDATE_NOTICE:-on}" = on ] && python3 scripts/update_check.py --quiet || true   # 새 판이 있을 때만 한 줄

python3 scripts/kit.py run-engine &
echo "== 애니위키: http://<서버 주소>:${LISTEN##*:}"
exec python3 scripts/offline_proxy.py assets --listen "$LISTEN" --upstream 127.0.0.1:4001 --wiki-db wikis/opennamu/data.db
