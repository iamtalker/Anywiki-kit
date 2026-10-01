"""받기 도우미: 공식 배포처에서 받고 SHA-256 으로 검증한다 (표준 라이브러리만).

- download(url, dest, sha256): 파일 하나
"""
import hashlib
import json
import os
import sys
import urllib.request

UA = "anywiki-kit (+https://github.com/iamtalker/anywiki-kit)"


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


def sources(root):
    return json.load(open(os.path.join(root, "sources.json"), encoding="utf-8"))


if __name__ == "__main__":
    print(sha256_file(sys.argv[1]))
