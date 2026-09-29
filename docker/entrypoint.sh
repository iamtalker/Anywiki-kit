#!/usr/bin/env bash
# 컨테이너 시작: 엔진(ENGINE)이 처음이면 설치하고, 전에 다른 엔진을 쓰고 있었으면 문서를 통역해 옮긴 뒤 켠다
set -euo pipefail
cd /kit
ENGINE="${ENGINE:-opennamu}"
MARK=wikis/.engine   # 지난번에 켠 엔진(볼륨에 남는다)
mkdir -p wikis

# 0.1 의 볼륨(/kit/wiki)을 그대로 붙여 두었으면 옮겨 온다
if [ -f wiki/data.db ] && [ ! -e wikis/opennamu/data.db ]; then
  echo "== 예전 위키(/kit/wiki)를 wikis/opennamu 로 복사합니다"
  mkdir -p wikis/opennamu && cp -a wiki/. wikis/opennamu/
  [ -f "$MARK" ] || echo opennamu > "$MARK"
fi

# 위키 색 (openNAMU 는 중계 서버가 panel.json 의 color 를 읽고, Markdown 엔진은 자기 설정에 둔다)
if [[ "$COLOR" =~ ^#[0-9a-fA-F]{6}$ ]]; then echo "{\"color\": \"$COLOR\", \"engine\": \"$ENGINE\"}" > panel.json; fi

installed() { python3 -c "import sys; sys.path.insert(0,'scripts'); import engines; sys.exit(0 if engines.get('$1','.').installed() else 1)"; }
OLD="$(cat "$MARK" 2>/dev/null || true)"
if [ -n "$OLD" ] && [ "$OLD" != "$ENGINE" ] && installed "$OLD"; then
  echo "== 엔진을 $OLD → $ENGINE 로 바꿉니다: 문서를 통역해 옮깁니다(옛 데이터는 wikis/$OLD 에 남음)"
  ENGINE="$OLD" python3 scripts/transfer.py switch /kit "$ENGINE"
elif ! installed "$ENGINE"; then
  echo "== 처음 실행: $ENGINE 엔진을 받고 빈 위키를 만듭니다 (몇 분)"
  python3 scripts/kit.py install "$ENGINE"
fi
echo "$ENGINE" > "$MARK"
export ENGINE
if [ "$ENGINE" = markdown ]; then
  python3 -c "import sys; sys.path.insert(0,'scripts'); import engines; engines.get('markdown','.').store().set_conf('color', sys.argv[1])" "$COLOR" || true
fi
python3 scripts/kit.py info | grep -E '"(docs|admin)"' || true

[ "${UPDATE_NOTICE:-on}" = on ] && python3 scripts/update_check.py --quiet || true   # 새 판이 있을 때만 한 줄

python3 scripts/kit.py run-engine &
if [ "${COWIKI:-off}" = on ]; then   # 공동위키: 고정 주소(COWIKI_URL, 3002번을 열어 둠)가 없으면 Cloudflare 임시 주소
  if [ -n "${COWIKI_URL:-}" ]; then
    python3 scripts/cowiki.py /kit run --listen 0.0.0.0:3002 --self-url "$COWIKI_URL" &
  else
    python3 scripts/cowiki.py /kit run --tunnel-log /tmp/cowiki-tunnel.log &
    CF=$(python3 scripts/cloudflared.py) && "$CF" tunnel --no-autoupdate --url http://127.0.0.1:3002 > /tmp/cowiki-tunnel.log 2>&1 &
  fi
  echo "== 공동위키 내 ID: $(python3 scripts/cowiki.py /kit id)  (회원 등록: docker compose exec anywiki python3 scripts/cowiki.py /kit add ID 이름)"
fi
echo "== 애니위키($ENGINE): http://<서버 주소>:${LISTEN##*:}"
if [ "$ENGINE" = opennamu ]; then
  exec python3 scripts/offline_proxy.py assets --listen "$LISTEN" --upstream 127.0.0.1:3001 --wiki-db wikis/opennamu/data.db
fi
exec python3 scripts/offline_proxy.py assets --listen "$LISTEN" --upstream 127.0.0.1:3001 --pass
