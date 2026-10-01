"""애니위키 내장 마크다운 엔진 (파이썬 표준 라이브러리만 사용).

문서는 wikis/markdown/pages/<제목>.md 파일로 두고(Obsidian 같은 편집기로 폴더째 열 수 있음),
역사·분류·설정은 wikis/markdown/wiki.db(SQLite)에 둔다.

    python mdwiki.py <wikis/markdown 폴더> [--port 4001] [--host 127.0.0.1]

문법: 마크다운(GitHub 방식) + 위키 링크 [[문서|글]], 각주 [^1], 분류는 머리말(categories) 또는 문서 끝 '분류:' 줄.
편집 권한: 설정의 edit = "all"(누구나) 또는 "admin"(관리자만, 기본). 관리자 비밀번호는 설치할 때 정한다.
"""
import argparse
import hashlib
import hmac
import html
import http.server
import json
import os
import random
import re
import secrets
import socketserver
import sqlite3
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wikiconv  # noqa: E402
from wikiconv.markdown import md_name  # noqa: E402

LOCK = threading.Lock()
E = html.escape


# ================================================================ 저장소
class Store:
    def __init__(self, root):
        self.root = root
        self.pages_dir = os.path.join(root, "pages")
        os.makedirs(self.pages_dir, exist_ok=True)
        self.db_path = os.path.join(root, "wiki.db")
        db = self.db()
        db.executescript("""
            create table if not exists page (title text primary key, file text, modified text, author text);
            create table if not exists rev (id integer primary key autoincrement, title text, text text,
                                            date text, author text, summary text);
            create index if not exists rev_title on rev(title, id);
            create index if not exists rev_date on rev(date);
            create table if not exists cat (title text, cat text, primary key (title, cat));
            create table if not exists conf (k text primary key, v text);
        """)
        db.commit()
        db.close()

    def db(self):
        return sqlite3.connect(self.db_path, timeout=30)

    def conf(self, k, default=""):
        db = self.db()
        try:
            r = db.execute("select v from conf where k = ?", (k,)).fetchone()
            return r[0] if r else default
        finally:
            db.close()

    def set_conf(self, k, v):
        with LOCK:
            db = self.db()
            db.execute("insert or replace into conf values (?, ?)", (k, str(v)))
            db.commit()
            db.close()

    def path(self, title):
        return os.path.join(self.pages_dir, md_name(title))

    def get(self, title):
        db = self.db()
        try:
            r = db.execute("select file, modified, author from page where title = ?", (title,)).fetchone()
        finally:
            db.close()
        if not r:
            return None
        try:
            with open(os.path.join(self.pages_dir, r[0]), encoding="utf-8") as f:
                return f.read(), r[1], r[2]
        except OSError:
            return None

    def exists(self, title):
        db = self.db()
        try:
            return db.execute("select 1 from page where title = ?", (title,)).fetchone() is not None
        finally:
            db.close()

    def titles(self):
        db = self.db()
        try:
            return [t for (t,) in db.execute("select title from page order by title")]
        finally:
            db.close()

    def put(self, title, text, author="", summary="", date=None):
        """새 판으로 저장. 바뀐 게 없으면 False."""
        title = title.strip()
        if not title:
            raise ValueError("제목이 비었습니다")
        text = text.replace("\r\n", "\n")
        with LOCK:
            cur = self.get(title)
            if cur and cur[0] == text:
                return False
            when = date or time.strftime("%Y-%m-%d %H:%M:%S")
            name = md_name(title)
            tmp = os.path.join(self.pages_dir, name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, os.path.join(self.pages_dir, name))
            db = self.db()
            db.execute("insert or replace into page values (?, ?, ?, ?)", (title, name, when, author))
            db.execute("insert into rev (title, text, date, author, summary) values (?, ?, ?, ?, ?)",
                       (title, text, when, author, summary))
            db.execute("delete from cat where title = ?", (title,))
            try:
                cats = wikiconv.parse(text, "markdown", title).cats
            except Exception:
                cats = []
            db.executemany("insert or ignore into cat values (?, ?)", [(title, c) for c in cats])
            db.commit()
            db.close()
            return True

    def delete(self, title, author=""):
        with LOCK:
            db = self.db()
            r = db.execute("select file from page where title = ?", (title,)).fetchone()
            if r:
                try:
                    os.remove(os.path.join(self.pages_dir, r[0]))
                except OSError:
                    pass
                db.execute("delete from page where title = ?", (title,))
                db.execute("delete from cat where title = ?", (title,))
                db.execute("insert into rev (title, text, date, author, summary) values (?, '', ?, ?, '삭제')",
                           (title, time.strftime("%Y-%m-%d %H:%M:%S"), author))
                db.commit()
            db.close()
            return bool(r)

    def scan_files(self):
        """폴더에 직접 넣거나 고친 .md 파일을 알아차려 목록·역사에 넣는다(Obsidian 등으로 고친 경우)."""
        from wikiconv.markdown import md_title
        db = self.db()
        known = dict(db.execute("select file, title from page").fetchall())
        db.close()
        for name in os.listdir(self.pages_dir):
            if not name.lower().endswith(".md"):
                continue
            path = os.path.join(self.pages_dir, name)
            try:
                text = open(path, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            title = known.get(name) or md_title(name)
            cur = self.get(title)
            if not cur or cur[0] != text.replace("\r\n", "\n"):
                self.put(title, text, "파일에서", "폴더의 파일이 바뀜",
                         time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path))))


# ================================================================ 화면
CSS = """
:root{--c:%(color)s}*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;color:#222;background:#fff;line-height:1.65}
header{background:var(--c);color:#fff;padding:8px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
header a{color:#fff;text-decoration:none;font-weight:600}header form{margin-left:auto;display:flex;gap:4px}
header input{padding:6px 8px;border:0;border-radius:4px;min-width:0;width:180px}main{max-width:900px;margin:0 auto;padding:12px 16px 48px}
h1.t{font-size:28px;margin:12px 0 2px}.meta{color:#777;font-size:13px}.tools a{margin-right:12px;font-size:14px}
a{color:#1c63c7}a.new{color:#d33}pre{background:#f6f8fa;padding:10px;overflow:auto}code{background:#f3f3f3;padding:1px 4px;border-radius:3px}
pre code{background:none;padding:0}.table{overflow-x:auto}table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #ccc;padding:4px 8px}
th{background:#f3f3f3}blockquote{border-left:4px solid #ccc;margin:8px 0;padding:2px 12px;color:#555}.toc{background:#f7f7f7;border:1px solid #ddd;padding:8px 16px;display:inline-block}
.toc ul{margin:4px 0;padding-left:18px}.toc .l3{margin-left:12px}.toc .l4{margin-left:24px}.cats{border:1px solid #ddd;padding:6px 10px;margin-top:24px;font-size:14px}
textarea{width:100%;min-height:60vh;font-family:ui-monospace,monospace;font-size:14px}input[type=text],input[type=password]{padding:6px}
.footnotes{font-size:14px;border-top:1px solid #ddd;margin-top:24px;padding-top:6px}.redirect{font-size:18px}
details{border:1px solid #ddd;padding:4px 10px;margin:8px 0}summary{cursor:pointer}.msg{background:#fff4e0;padding:8px 12px;border-radius:6px}
@media (max-width:600px){header input{width:120px}h1.t{font-size:22px}}
"""


def page_html(store, title, body, head_title=None):
    color = store.conf("color", "#3b5bdb")
    name = store.conf("name", "애니위키")
    plugins = json.loads(store.conf("plugins", "[]") or "[]")
    extra = ""
    if "katex" in plugins:
        extra += ('<link rel="stylesheet" href="/_kit/cdn/cdn.jsdelivr.net/npm/katex@0.16.38/dist/katex.min.css">'
                  '<script defer src="/_kit/cdn/cdn.jsdelivr.net/npm/katex@0.16.38/dist/katex.min.js"></script>'
                  '<script defer src="/_kit/cdn/cdn.jsdelivr.net/npm/katex@0.16.38/dist/contrib/auto-render.min.js" '
                  'onload="renderMathInElement(document.body,{delimiters:[{left:\'\\\\[\',right:\'\\\\]\',display:true},'
                  '{left:\'\\\\(\',right:\'\\\\)\',display:false}]})"></script>')
    if "highlight" in plugins:
        extra += ('<link rel="stylesheet" href="/_kit/cdn/cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/default.min.css">'
                  '<script src="/_kit/cdn/cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js"></script>'
                  '<script>document.addEventListener("DOMContentLoaded",function(){hljs.highlightAll()})</script>')
    return (f'<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            f'<title>{E(head_title or title)} - {E(name)}</title><style>{CSS % {"color": E(color)}}</style>{extra}'
            f'<header><a href="/">{E(name)}</a><a href="/recent">최근 바뀜</a><a href="/random">아무 문서</a>'
            f'<a href="/all">모든 문서</a><form action="/search"><input name="q" placeholder="검색" aria-label="검색">'
            f'</form></header><main>{body}</main></html>')


def link_of(t):
    return "/w/" + urllib.parse.quote(t, safe="")


class Handler(http.server.BaseHTTPRequestHandler):
    store = None
    secret = b""
    assets = ""
    protocol_version = "HTTP/1.1"
    timeout = 60

    def log_message(self, *a):
        pass

    # ---- 도우미
    def send(self, code, body, ctype="text/html; charset=utf-8", headers=()):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def redirect(self, to, headers=()):
        self.send(303, "", headers=[("Location", to)] + list(headers))

    def user(self):
        c = self.headers.get("Cookie", "")
        m = re.search(r"aw_session=([\w.-]+)", c)
        if not m:
            return ""
        name, _, sig = m.group(1).rpartition(".")
        good = hmac.new(self.secret, name.encode(), hashlib.sha256).hexdigest()[:32]
        return "admin" if name == "admin" and hmac.compare_digest(sig, good) else ""

    def can_edit(self):
        return self.store.conf("edit", "admin") == "all" or self.user() == "admin"

    def form(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n < 0 or n > 8 << 20:
            return {}
        return {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"),
                                                             keep_blank_values=True).items()}

    def who(self):
        return self.user() or self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()

    def render(self, title, text):
        doc = wikiconv.parse(text, "markdown", title)
        return wikiconv.html_writer.write(doc, title, link_of, self.store.exists)

    # ---- 경로
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(u.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if path in ("/", ""):
            return self.redirect(link_of(self.store.conf("front", "FrontPage")))
        if path.startswith("/_kit/cdn/"):
            return self.cdn(path)
        if path.startswith("/w/"):
            return self.view(path[3:], q)
        if path.startswith("/edit/"):
            return self.edit_form(path[6:])
        if path.startswith("/history/"):
            return self.history(path[9:])
        if path == "/recent":
            return self.recent()
        if path == "/all":
            return self.all_pages()
        if path == "/random":
            ts = self.store.titles()
            return self.redirect(link_of(random.choice(ts)) if ts else "/")
        if path == "/search":
            return self.search(q.get("q", ""))
        if path == "/login":
            return self.send(200, page_html(self.store, "로그인", '<h1 class="t">관리자 로그인</h1><form method="post">'
                                            '<input type="password" name="pw" placeholder="비밀번호" autofocus> '
                                            '<button>로그인</button></form>'))
        if path == "/logout":
            return self.redirect("/", [("Set-Cookie", "aw_session=; Path=/; Max-Age=0")])
        if path == "/_kit/api/titles":
            return self.send(200, json.dumps(self.store.titles(), ensure_ascii=False), "application/json")
        self.send(404, page_html(self.store, "없음", "<p>없는 주소입니다.</p>"))

    do_HEAD = do_GET

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(u.path)
        f = self.form()
        if path == "/login":
            h = self.store.conf("admin_pw", "")
            salt, _, want = h.partition("$")
            got = hashlib.pbkdf2_hmac("sha256", f.get("pw", "").encode(), bytes.fromhex(salt or "00"), 200000).hex()
            if want and hmac.compare_digest(got, want):
                sig = hmac.new(self.secret, b"admin", hashlib.sha256).hexdigest()[:32]
                return self.redirect("/", [("Set-Cookie", f"aw_session=admin.{sig}; Path=/; HttpOnly; SameSite=Lax")])
            time.sleep(1)
            return self.send(403, page_html(self.store, "로그인", '<p class="msg">비밀번호가 틀렸습니다.</p>'
                                            '<p><a href="/login">다시</a></p>'))
        if path.startswith("/edit/"):
            title = path[6:]
            if not self.can_edit():
                return self.send(403, page_html(self.store, title, '<p class="msg">편집하려면 <a href="/login">관리자 로그인</a>이 '
                                                '필요합니다.</p>'))
            if f.get("delete") == "1":
                self.store.delete(title, self.who())
                return self.redirect("/")
            self.store.put(title, f.get("text", ""), self.who(), f.get("summary", ""))
            return self.redirect(link_of(title))
        self.send(404, "없음", "text/plain; charset=utf-8")

    def cdn(self, path):
        rel = path[len("/_kit/cdn/"):]
        base = os.path.join(self.assets, "cdn")
        full = os.path.normpath(os.path.join(base, rel))
        if not full.startswith(os.path.normpath(base)) or not os.path.isfile(full):
            return self.send(404, "없음", "text/plain; charset=utf-8")
        import mimetypes
        with open(full, "rb") as fh:
            self.send(200, fh.read(), mimetypes.guess_type(full)[0] or "application/octet-stream",
                      [("Cache-Control", "max-age=86400")])

    def view(self, title, q):
        got = self.store.get(title)
        tools = (f'<div class="tools"><a href="/edit/{urllib.parse.quote(title, safe="")}">편집</a>'
                 f'<a href="/history/{urllib.parse.quote(title, safe="")}">역사</a>'
                 + ('<a href="/logout">로그아웃</a>' if self.user() else '<a href="/login">로그인</a>') + "</div>")
        if title.startswith("분류:"):
            db = self.store.db()
            members = [t for (t,) in db.execute("select title from cat where cat = ? order by title", (title[3:],))]
            db.close()
            lst = "<h2>이 분류에 속한 문서</h2><ul>" + "".join(f'<li><a href="{E(link_of(t))}">{E(t)}</a></li>'
                                                          for t in members) + "</ul>" if members else ""
        else:
            lst = ""
        if not got:
            body = (f'<h1 class="t">{E(title)}</h1>{tools}<p>아직 없는 문서입니다. '
                    f'<a href="/edit/{urllib.parse.quote(title, safe="")}">새로 만들기</a></p>{lst}')
            return self.send(404, page_html(self.store, title, body))
        text, modified, author = got
        doc = wikiconv.parse(text, "markdown", title)
        if doc.redirect and q.get("redirect") != "no":
            return self.redirect(link_of(doc.redirect.split("#")[0]))
        content = wikiconv.html_writer.write(doc, title, link_of, self.store.exists)
        body = (f'<h1 class="t">{E(title)}</h1><div class="meta">최근 수정 {E(modified)}</div>{tools}'
                f'<article>{content}</article>{lst}')
        self.send(200, page_html(self.store, title, body))

    def edit_form(self, title):
        if not self.can_edit():
            return self.send(403, page_html(self.store, title, '<p class="msg">편집하려면 <a href="/login">관리자 로그인</a>이 '
                                            '필요합니다.</p>'))
        got = self.store.get(title)
        text = got[0] if got else ""
        body = (f'<h1 class="t">{E(title)} 편집</h1><form method="post">'
                f'<textarea name="text">{E(text)}</textarea><p><input type="text" name="summary" placeholder="편집 요약" '
                f'style="width:60%"> <button>저장</button> <a href="{E(link_of(title))}">취소</a></p>'
                + ('<p><label><input type="checkbox" name="delete" value="1"> 이 문서 삭제</label></p>' if got else "")
                + '</form><p class="meta">문법: 마크다운 + [[문서|글]] 위키 링크, 각주 [^1], '
                  '분류는 문서 끝에 --- 다음 줄 "분류: [이름](<분류：이름.md>)" 또는 머리말 categories.</p>')
        self.send(200, page_html(self.store, title, body, f"{title} 편집"))

    def history(self, title):
        db = self.store.db()
        rows = db.execute("select id, date, author, summary, length(text) from rev where title = ? order by id desc limit 200",
                          (title,)).fetchall()
        db.close()
        items = "".join(f"<li>{E(d)} · {E(a or '')} · {n}자 {('· ' + E(s)) if s else ''}</li>" for _, d, a, s, n in rows)
        self.send(200, page_html(self.store, title, f'<h1 class="t">{E(title)} 역사</h1><ul>{items}</ul>', f"{title} 역사"))

    def recent(self):
        db = self.store.db()
        rows = db.execute("select title, date, author, summary from rev order by id desc limit 100").fetchall()
        db.close()
        items = "".join(f'<li>{E(d)} · <a href="{E(link_of(t))}">{E(t)}</a> · {E(a or "")} {("· " + E(s)) if s else ""}</li>'
                        for t, d, a, s in rows)
        self.send(200, page_html(self.store, "최근 바뀜", f'<h1 class="t">최근 바뀜</h1><ul>{items}</ul>'))

    def all_pages(self):
        items = "".join(f'<li><a href="{E(link_of(t))}">{E(t)}</a></li>' for t in self.store.titles())
        self.send(200, page_html(self.store, "모든 문서", f'<h1 class="t">모든 문서</h1><ul>{items}</ul>'))

    def search(self, q):
        q = q.strip()
        if q and self.store.exists(q):
            return self.redirect(link_of(q))
        hits = []
        if q:
            low = q.lower()
            for t in self.store.titles():
                if low in t.lower():
                    hits.append(t)
            if len(hits) < 50:
                db = self.store.db()
                for (t,) in db.execute("select title from page"):
                    got = self.store.get(t)
                    if got and low in got[0].lower() and t not in hits:
                        hits.append(t)
                    if len(hits) >= 50:
                        break
                db.close()
        items = "".join(f'<li><a href="{E(link_of(t))}">{E(t)}</a></li>' for t in hits)
        make = f'<p><a href="/edit/{urllib.parse.quote(q, safe="")}">「{E(q)}」 문서 만들기</a></p>' if q else ""
        self.send(200, page_html(self.store, "검색", f'<h1 class="t">검색: {E(q)}</h1>{make}<ul>{items}</ul>'))


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def set_password(store, pw):
    salt = secrets.token_bytes(16)
    store.set_conf("admin_pw", salt.hex() + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200000).hex())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--port", type=int, default=4001)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--assets", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"))
    ap.add_argument("--set-password", default="")
    args = ap.parse_args()
    store = Store(args.dir)
    if args.set_password:
        set_password(store, args.set_password)
        print("관리자 비밀번호를 바꿨습니다")
        return
    secret = store.conf("secret")
    if not secret:
        secret = secrets.token_hex(32)
        store.set_conf("secret", secret)
    store.scan_files()
    Handler.store, Handler.secret, Handler.assets = store, bytes.fromhex(secret), args.assets
    print(f"애니위키 마크다운 엔진: http://{args.host}:{args.port}", flush=True)
    Server((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
