#!/usr/bin/env bash
# 애니위키 키트 리눅스 설치: 위키 엔진(openNAMU) 받기 → 빈 위키 만들기 → 첫 화면
#
#   bash server/install.sh
#
# 필요한 것: python3(3.8+), curl, sha256sum
# 이미 끝난 단계는 건너뛰므로, 중간에 끊겨도 다시 실행하면 이어서 진행합니다.
set -euo pipefail

KIT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KIT"
step() { printf '\n== %s\n' "$*"; }
die() { echo "오류: $*" >&2; exit 1; }

step "1/3 필요한 프로그램 확인"
for c in python3 curl sha256sum; do
  command -v "$c" >/dev/null || die "$c 이 없습니다. 예) sudo apt install python3 curl coreutils"
done
case "$(uname -m)" in
  x86_64|amd64) ARCH=amd64; ENGINE_SHA=d82832ab3d9dda4ff3cde6a0a6ff3740dfd340ba2a8cb44f9da723b7afd91570 ;;
  aarch64|arm64) ARCH=arm64; ENGINE_SHA=3562bce94fe39f30d5b7688fba467baa4d2acd52b0ae437477275b6784e5c1c5 ;;
  *) die "지원하지 않는 CPU 입니다: $(uname -m)" ;;
esac
echo "  완료 (CPU $ARCH)"

step "2/3 위키 엔진(openNAMU) 받기"
mkdir -p wiki
ENGINE_URL="https://github.com/openNAMU/openNAMU/releases/download/v4.3.6-beta.2/main.$ARCH.bin"
if ! echo "$ENGINE_SHA  wiki/main.bin" | sha256sum -c --status 2>/dev/null; then
  curl -fL -o wiki/main.bin "$ENGINE_URL"
  echo "$ENGINE_SHA  wiki/main.bin" | sha256sum -c --status || die "엔진 파일 해시가 맞지 않습니다"
fi
chmod +x wiki/main.bin
echo "  완료"

step "3/3 빈 위키 만들기"
if [ ! -f wiki/data.db ]; then
  (cd wiki && timeout 60 ./main.bin 3001 --localhost >/dev/null 2>&1 || true)
  [ -f wiki/data.db ] || die "openNAMU 가 DB 를 만들지 못했습니다(3001번 포트를 확인하세요)"
fi
PYTHONUTF8=1 python3 scripts/add_frontpage.py wiki

cat <<'MSG'

설치 완료.
  켜기:        bash server/anywiki.sh start
  상태·끄기:   bash server/anywiki.sh status | stop
  부팅 시 자동 시작(systemd): sudo bash server/anywiki.sh install-service
MSG
