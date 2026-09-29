"""엔진·옮기기 시험(인터넷 없이): 마크다운 엔진에 문서를 넣고, 네 형식으로 내보냈다 다시 가져와 같아지는지.
DokuWiki 는 받아 둔 파일이 있을 때만(ANYWIKI_DOKU_LAYER=받아 둔 .tgz), MediaWiki 는 이 시험에서 다루지 않는다."""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.environ.pop("ENGINE", None)
import engines  # noqa: E402
import transfer  # noqa: E402
import wikiconv  # noqa: E402
from engines.base import Page  # noqa: E402

DOCS = {
    "대문": "# 환영\n\n**굵게** 와 [[다른 문서]] 링크.\n\n- 하나\n- 둘\n",
    "다른 문서": "| 가 | 나 |\n|---|---|\n| 1 | 2 |\n\n각주[^1]\n\n[^1]: 설명\n",
    "분류:예시": "예시 분류.\n",
}
fails = 0


def check(cond, msg):
    global fails
    if not cond:
        fails += 1
        print("실패:", msg)


def make_root():
    root = tempfile.mkdtemp(prefix="awtest-")
    shutil.copy(os.path.join(ROOT, "sources.json"), root)
    return root


root = make_root()
try:
    e = engines.get("markdown", root)
    e.install(lambda m: None)
    check(e.installed(), "마크다운 엔진 설치")
    for t, x in DOCS.items():
        check(e.put(Page(t, x, "2026-09-01 10:00:00", "시험", "처음")), f"넣기 {t}")
    check(not e.put(Page("대문", DOCS["대문"])), "같은 내용은 새 판을 만들지 않음")
    check(e.count() == 3, f"문서 수 {e.count()}")
    check(e.get("대문").text == DOCS["대문"], "읽기")
    check([p.title for p in e.changes_since("2026-08-31 00:00:00")] != [], "changes_since")
    check({p["id"] for p in e.plugins() if p["on"]} == {"katex", "highlight"}, "마크다운 기본 플러그인")
    e.set_plugin("katex", False)
    check(not next(p for p in e.plugins() if p["id"] == "katex")["on"], "마크다운 플러그인 끄기")

    for fmt in transfer.FORMATS:
        out = os.path.join(root, "export", f"t-{fmt}{transfer.EXT[fmt]}")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        pages, resolve = transfer.engine_pages(e)
        n = transfer.WRITERS[fmt](transfer.translate(pages, "markdown", fmt, resolve), out)
        check(n == 3, f"{fmt} 내보내기 수 {n}")
        check(transfer.detect(out) == fmt, f"{fmt} 형식 알아보기: {transfer.detect(out)}")
        # 새 위키에 가져오기
        r2 = make_root()
        try:
            e2 = engines.get("markdown", r2)
            e2.install(lambda m: None)
            open(os.path.join(r2, "panel.json"), "w").write('{"engine": "markdown"}')
            transfer.import_file(r2, out)
            check(e2.count() == 3, f"{fmt} 가져오기 수 {e2.count()}")
            got = getattr(transfer, "read_" + fmt)(out)
            got = got[0] if fmt == "dokuwiki" else list(got)
            if got:
                check(len(got) == 3, f"{fmt} 읽기 수 {len(got)}")
                titles = {p.title for p in got}
                check(titles == set(DOCS), f"{fmt} 제목 {titles}")
                for p in got:
                    back = wikiconv.convert(p.text, transfer.SYNTAX[fmt], "markdown", p.title)
                    for w in ("굵게", "환영", "설명", "하나"):
                        if w in DOCS.get(p.title, ""):
                            check(w in back, f"{fmt} 에서 '{w}' 잃음: {back!r}")
        finally:
            shutil.rmtree(r2, ignore_errors=True)

    # 엔진 바꾸기: 마크다운 → DokuWiki
    doku = os.environ.get("ANYWIKI_DOKU_LAYER")
    if doku and shutil.which("php"):
        os.makedirs(os.path.join(root, "tools"), exist_ok=True)
        shutil.copy(doku, os.path.join(root, "tools", os.path.basename(doku)))
        import json
        json.dump({"engine": "markdown"}, open(os.path.join(root, "panel.json"), "w"))
        n = transfer.switch(root, "dokuwiki", lambda m: None)
        d = engines.get("dokuwiki", root)
        check(n == 3 and d.count() == 4, f"(설치 때 넣은 start + 3) DokuWiki 로 바꾸기 {n} {d.count()}")
        check("굵게" in d.get("대문").text, "DokuWiki 본문")
        # 플러그인: 동봉 플러그인 끄고 켜기, 꼭 필요한 것은 못 끔, 가짜 저장소에서 찾아 설치
        check(d.set_plugin("styling", False) and not next(p for p in d.plugins() if p["id"] == "styling")["on"], "끄기")
        d.set_plugin("styling", True)
        try:
            d.set_plugin("acl", False)
            check(False, "acl 을 끌 수 있으면 안 됨")
        except ValueError:
            pass
        import io
        import json as _json
        import threading
        import zipfile
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("dokuwiki-plugin-hello-master/plugin.info.txt", "base hello\nname Hello\ndesc 인사\n")
            z.writestr("dokuwiki-plugin-hello-master/syntax.php", "<?php\n")
        evil = io.BytesIO()
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("../../escape.txt", "x")
        files = {"/hello.zip": buf.getvalue(), "/evil.zip": evil.getvalue()}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.startswith("/api.php"):
                    port = self.server.server_address[1]
                    body = _json.dumps([
                        {"plugin": "hello", "name": "Hello", "description": "인사", "downloadurl": f"http://127.0.0.1:{port}/hello.zip"},
                        {"plugin": "evil", "name": "Evil", "downloadurl": f"http://127.0.0.1:{port}/evil.zip"},
                        {"plugin": "bad", "name": "Bad", "securityissue": "XSS", "downloadurl": f"http://127.0.0.1:{port}/hello.zip"},
                    ]).encode()
                else:
                    body = files.get(self.path, b"")
                self.send_response(200 if body else 404)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        os.environ["ANYWIKI_DOKU_REPO"] = f"http://127.0.0.1:{srv.server_address[1]}/api.php"
        found = d.search_plugins("hello")
        check(any(x["id"] == "hello" for x in found), f"찾기 {found}")
        d.install_plugin("hello", lambda m: None)
        check(any(p["id"] == "hello" for p in d.plugins()), "설치한 플러그인이 목록에")
        for bad, why in (("evil", "위험한 경로"), ("bad", "보안 문제")):
            try:
                d.install_plugin(bad, lambda m: None)
                check(False, f"{bad} 가 설치되면 안 됨")
            except ValueError as ex:
                check(why in str(ex), f"{bad}: {ex}")
        check(not os.path.exists(os.path.join(d.dir, "lib", "escape.txt")), "압축 밖으로 풀림")
        srv.shutdown()
    else:
        print("(DokuWiki 바꾸기 시험은 건너뜀: ANYWIKI_DOKU_LAYER 와 php 필요)")
finally:
    shutil.rmtree(root, ignore_errors=True)

print("엔진 시험 통과" if not fails else f"엔진 시험 {fails}개 실패")
sys.exit(1 if fails else 0)
