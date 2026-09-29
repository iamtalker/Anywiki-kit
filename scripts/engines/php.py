"""PHP 실행 환경(DokuWiki·MediaWiki 용).

- 리눅스: 시스템 PHP 를 쓴다(없으면 설치 안내). 예) sudo apt install php-cli php-mbstring php-xml php-intl php-sqlite3 php-gd
- Windows: windows.php.net 공식 휴대용 PHP(zip)를 받는다. 해시는 windows.php.net 의 releases.json 에 적힌 SHA-256 으로 검증.
  tools/php/ 에 풀고 php.ini 에서 필요한 확장을 켠다.
"""
import json
import os
import shutil
import subprocess
import zipfile

NEEDED = {"dokuwiki": ["mbstring", "xml"],
          "mediawiki": ["mbstring", "xml", "intl", "pdo_sqlite", "sqlite3", "fileinfo"]}
WIN_EXT = ["mbstring", "intl", "sqlite3", "pdo_sqlite", "openssl", "fileinfo", "gd", "curl", "zip"]
APT = "sudo apt install php-cli php-mbstring php-xml php-intl php-sqlite3 php-gd php-curl php-zip"


def php_path(root):
    local = os.path.join(root, "tools", "php", "php.exe" if os.name == "nt" else "php")
    if os.path.exists(local):
        return local
    return shutil.which("php") or ""


def modules(php):
    try:
        out = subprocess.run([php, "-m"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {ln.strip().lower() for ln in out.splitlines() if ln.strip() and not ln.startswith("[")}


def ensure(root, engine, log=print):
    """PHP 경로를 돌려준다. 없으면(Windows) 받고, 리눅스는 안내와 함께 오류."""
    php = php_path(root)
    if not php and os.name == "nt":
        php = install_windows(root, log)
    if not php:
        raise RuntimeError("PHP 가 없습니다. 리눅스에서는 이렇게 설치하세요: " + APT)
    miss = [m for m in NEEDED.get(engine, []) if m not in modules(php)]
    if miss:
        raise RuntimeError(f"PHP 확장이 없습니다: {', '.join(miss)}. 리눅스에서는: {APT}")
    return php


def install_windows(root, log=print):
    import fetch
    rel = json.load(fetch._get("https://windows.php.net/downloads/releases/releases.json"))
    ver = sorted((k for k in rel if k.replace(".", "").isdigit()), key=lambda v: [int(x) for x in v.split(".")])[-1]
    item = None
    for k, v in rel[ver].items():
        if isinstance(v, dict) and k.startswith("nts-") and k.endswith("-x64") and "zip" in v:
            item = v["zip"]
            break
    if not item or not item.get("sha256"):
        raise RuntimeError("windows.php.net 에서 PHP 정보를 찾지 못했습니다")
    zpath = os.path.join(root, "tools", item["path"])
    log(f"PHP {rel[ver].get('version', ver)} 받기(Windows 휴대용)")
    fetch.download("https://windows.php.net/downloads/releases/" + item["path"], zpath, item["sha256"], log=log)
    dest = os.path.join(root, "tools", "php")
    shutil.rmtree(dest, ignore_errors=True)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(dest)
    ini = ["extension_dir = \"ext\"", "memory_limit = 512M", "upload_max_filesize = 32M", "post_max_size = 32M",
           "date.timezone = Asia/Seoul"] + [f"extension={e}" for e in WIN_EXT]
    with open(os.path.join(dest, "php.ini"), "w", encoding="utf-8") as f:
        f.write("\n".join(ini) + "\n")
    return os.path.join(dest, "php.exe")


def server_command(php, docroot, port, router=None):
    """PHP 내장 서버로 켜는 명령. 개인·소규모용(동시에 여러 요청은 워커 수만큼)."""
    args = [php, "-S", f"127.0.0.1:{port}", "-t", docroot]
    if router:
        args.append(router)
    env = dict(os.environ, PHP_CLI_SERVER_WORKERS="4")
    return args, docroot, env
