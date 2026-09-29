"""받기 도우미: 공식 배포처에서 받고 SHA-256 으로 검증한다 (표준 라이브러리만).

- download(url, dest, sha256): 파일 하나
- docker_layer(repo, digest, dest_dir, subdir): Docker Hub 공식 이미지의 층(layer) 하나를 받아(sha256 으로 검증) 원하는 폴더만 푼다.
  DokuWiki·MediaWiki 같은 PHP 프로그램은 운영체제와 상관없는 파일이라, Docker 없이도 이 방법으로 받을 수 있다.
"""
import hashlib
import json
import os
import shutil
import sys
import tarfile
import urllib.request

UA = "Anywiki-kit (+https://github.com/iamtalker/anywiki-kit)"


def _get(url, headers=None, timeout=120):
    return urllib.request.urlopen(urllib.request.Request(url, headers=dict({"User-Agent": UA}, **(headers or {}))),
                                  timeout=timeout)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest, sha256=None, headers=None, log=print):
    """이미 받아 둔 파일이 해시와 맞으면 건너뛴다. 해시가 다르면 지우고 오류."""
    if sha256 and os.path.exists(dest) and sha256_file(dest) == sha256.lower():
        return dest
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    part = dest + ".part"
    log(f"  받는 중: {url}")
    with _get(url, headers) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, step = 0, 0
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            got += len(b)
            if total and got * 10 // total > step:
                step = got * 10 // total
                log(f"  {got * 100 // total}% ({got // (1 << 20)}MB / {total // (1 << 20)}MB)")
    if sha256 and sha256_file(part) != sha256.lower():
        os.remove(part)
        raise RuntimeError(f"해시가 맞지 않습니다: {url}")
    os.replace(part, dest)
    return dest


def docker_layer(repo, digest, cache_dir, dest_dir, subdir, log=print):
    """Docker Hub 이미지 층을 받아 그 안의 subdir(예: var/www/html) 만 dest_dir 에 푼다.
    층 파일 이름이 곧 sha256 이라, 받은 뒤 해시가 맞는지 확인한다."""
    tok = json.load(_get(f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"))["token"]
    blob = os.path.join(cache_dir, digest.replace(":", "_") + ".tgz")
    download(f"https://registry-1.docker.io/v2/{repo}/blobs/{digest}", blob, digest.split(":", 1)[1],
             {"Authorization": "Bearer " + tok}, log)
    log("  푸는 중…")
    prefix = subdir.strip("/") + "/"
    tmp = dest_dir + ".part"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    with tarfile.open(blob, "r:gz") as t:
        for m in t.getmembers():
            name = m.name.lstrip("./")
            if not name.startswith(prefix) or name == prefix:
                continue
            rel = name[len(prefix):]
            if ".." in rel.split("/") or os.path.basename(rel).startswith(".wh."):
                continue
            target = os.path.join(tmp, *rel.split("/"))
            if m.isdir():
                os.makedirs(target, exist_ok=True)
            elif m.isfile():
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with t.extractfile(m) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                if m.mode & 0o111 and os.name != "nt":
                    os.chmod(target, 0o755)
            elif m.issym() and os.name != "nt":
                try:
                    os.symlink(m.linkname, target)
                except OSError:
                    pass
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    os.replace(tmp, dest_dir)
    return dest_dir


def sources(root):
    return json.load(open(os.path.join(root, "sources.json"), encoding="utf-8"))


if __name__ == "__main__":
    print(sha256_file(sys.argv[1]))
