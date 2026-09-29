#!/usr/bin/env bash
# 애니위키 리눅스 서버 켜기·끄기
#
#   bash server/anywiki.sh start            # 켜기 (기본: 0.0.0.0:3000 으로 공개)
#   bash server/anywiki.sh stop | status
#   sudo bash server/anywiki.sh install-service   # systemd 에 등록해 부팅 때 자동 시작
#
# 환경 변수: LISTEN(기본 0.0.0.0:3000)
#            TUNNEL(on|off, 기본 off): 공인 IP·공유기 설정 없이 Cloudflare 임시 주소(https)로 공개. 주소는 status 로 확인
#            UPDATE_NOTICE(on|off, 기본 on): GitHub 에 새 판이 나왔는지 켤 때 알려 주기(알리기만 함)
# 한 번 준 값은 anywiki.conf 에 기억되어 다음에 그냥 start 해도 그대로 쓴다. 바꾸려면 새 값을 주고 start.
#   예) LISTEN=127.0.0.1:3000 bash server/anywiki.sh start   → 다음부터 그냥 start 해도 127.0.0.1:3000
# HTTPS 는 nginx·Caddy 같은 역방향 프록시를 3000번 앞에 두세요.
set -euo pipefail
KIT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KIT"
CONF="$KIT/anywiki.conf"
VARS=(LISTEN TUNNEL UPDATE_NOTICE)
# 기억해 둔 설정 읽기(이번에 직접 준 값이 우선). source 하지 않고 KEY=값 줄만 읽는다
if [ -f "$CONF" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    k=${line%%=*}; v=${line#*=}
    case " ${VARS[*]} " in *" $k "*) ;; *) continue ;; esac
    [ -n "${!k+x}" ] || printf -v "$k" '%s' "$v"
  done < "$CONF"
fi
save_conf() {
  local k tmp="$CONF.tmp"
  : > "$tmp"
  for k in "${VARS[@]}"; do [ -n "${!k+x}" ] && printf '%s=%s\n' "$k" "${!k}" >> "$tmp"; done
  mv -f "$tmp" "$CONF"
}
LISTEN="${LISTEN:-0.0.0.0:3000}"
RUN="$KIT/run"; mkdir -p "$RUN"

running() { [ -f "$RUN/$1.pid" ] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null; }
launch() { # 이름 로그 명령...
  local name=$1 log=$2; shift 2
  running "$name" && return
  nohup "$@" >>"$RUN/$log" 2>&1 & echo $! >"$RUN/$name.pid"
}
tunnel_url() { grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$RUN/tunnel.log" 2>/dev/null | tail -n 1 || true; }

case "${1:-}" in
  start)
    [ -f wiki/data.db ] || { echo "아직 설치되지 않았습니다: bash server/install.sh"; exit 1; }
    save_conf || echo "설정을 anywiki.conf 에 기억하지 못했습니다(권한 확인)"
    (cd wiki && launch engine server.log ./main.bin 3001 --localhost)
    export PYTHONUTF8=1
    launch proxy proxy.log python3 scripts/offline_proxy.py assets --listen "$LISTEN" \
      --upstream 127.0.0.1:3001 --wiki-db wiki/data.db
    if [ "${TUNNEL:-off}" = on ]; then
      if CF=$(python3 scripts/cloudflared.py); then
        running tunnel || : > "$RUN/tunnel.log"
        launch tunnel tunnel.log "$CF" tunnel --no-autoupdate --url "http://${LISTEN/0.0.0.0/127.0.0.1}"
        echo "Cloudflare 임시 주소를 만드는 중입니다. 잠시 뒤 status 로 확인하세요(켤 때마다 주소가 바뀝니다)."
      else
        echo "터널 프로그램을 받지 못해 임시 주소 공개는 건너뜁니다."
      fi
    fi
    echo "켰습니다: http://$LISTEN (엔진 준비에 잠깐 걸릴 수 있습니다) · 임시 주소 공개: ${TUNNEL:-off}"
    [ "${UPDATE_NOTICE:-on}" = on ] && python3 scripts/update_check.py --quiet || true   # 새 판이 있을 때만 한 줄
    ;;
  stop)
    for n in tunnel proxy engine; do
      running "$n" && kill "$(cat "$RUN/$n.pid")" && echo "$n 껐습니다"
      rm -f "$RUN/$n.pid"
    done
    ;;
  status)
    for n in engine proxy tunnel; do
      if running "$n"; then echo "● $n 실행 중"; else echo "○ $n 꺼짐"; fi
    done
    running tunnel && echo "임시 공개 주소: $(tunnel_url)"
    [ "${UPDATE_NOTICE:-on}" = on ] && python3 scripts/update_check.py || true
    ;;
  install-service)
    [ "$(id -u)" = 0 ] || { echo "sudo 로 실행하세요"; exit 1; }
    USER_NAME="${SUDO_USER:-root}"
    save_conf && chown "$USER_NAME" "$CONF"   # 설정은 anywiki.conf 에서 읽으므로 서비스 파일에 박지 않는다
    cat >/etc/systemd/system/anywiki.service <<UNIT
[Unit]
Description=Anywiki (애니위키 키트)
After=network-online.target

[Service]
Type=forking
User=$USER_NAME
ExecStart=/usr/bin/env bash $KIT/server/anywiki.sh start
ExecStop=/usr/bin/env bash $KIT/server/anywiki.sh stop
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload && systemctl enable --now anywiki
    echo "등록했습니다: systemctl status anywiki"
    ;;
  *)
    sed -n '2,13p' "$0"
    ;;
esac
