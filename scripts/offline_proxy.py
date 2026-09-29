"""오프라인 중계 서버: 브라우저 ↔ (이 프로그램) ↔ openNAMU

openNAMU 는 CDN 주소와 외부 삽입(유튜브 등)을 프로그램 안에 고정해 두어서,
문서를 열 때마다 보는 사람의 IP 가 여러 외부 서비스로 전달된다.
이 중계 서버는 openNAMU 가 보낸 HTML 을 고쳐서
  1) CDN 파일은 설치 때 받아 둔 로컬 사본(/_kit/cdn/...)에서 불러오게 하고
  2) 영상·SNS 삽입(iframe)은 눌러야 열리는 링크로 바꾸고
  3) 모든 페이지에 붙는 트위터 스크립트는 뺀다.
  4) 아이콘은 iconify 서버에서 받지 않고, 동봉한 icons.json 으로 SVG 를 직접 그려 넣는다.
  5) 관리판에서 고른 머리글 색, 휴대폰 화면 다듬기, 검색창 제목 자동완성, 아무 문서나 보기 단추를 붙인다.
DB 의 문서 원문은 건드리지 않는다.

사용: python offline_proxy.py <assets 폴더> [--listen 127.0.0.1:3000] [--upstream 127.0.0.1:3001] [--wiki-db wikis/opennamu/data.db] [--pass]
"""
import argparse
import html
import http.client
import http.server
import json
import mimetypes
import os
import re
import socketserver
import sqlite3
import urllib.parse

CDN_HOSTS = ("cdn.jsdelivr.net", "cdnjs.cloudflare.com", "code.iconify.design")
CDN_RE = re.compile(r"https://(%s)/([^\"'\s)]+)" % "|".join(re.escape(h) for h in CDN_HOSTS))
DROP_SCRIPT_RE = re.compile(
    r"<script\b[^>]*\bsrc=[\"']https://(?:platform\.twitter\.com/widgets\.js|code\.iconify\.design/[^\"']+)"
    r"[\"'][^>]*>\s*</script>", re.I)
ICON_RE = re.compile(r'<span class="iconify" data-icon="ic:([\w-]+)"[^>]*>\s*</span>')
ICONS = {}
IFRAME_RE = re.compile(r"<iframe\b[^>]*?\bsrc=[\"']([^\"']+)[\"'][^>]*>.*?</iframe>", re.I | re.S)

# 삽입 주소 → (보여줄 이름, 원래 페이지 주소)
WATCH_RULES = [
    (re.compile(r"https://www\.youtube(?:-nocookie)?\.com/embed/([\w-]+)"), "유튜브",
     "https://www.youtube.com/watch?v={0}"),
    (re.compile(r"https://embed\.nicovideo\.jp/watch/(\w+)"), "니코니코 동화",
     "https://www.nicovideo.jp/watch/{0}"),
    (re.compile(r"https://player\.vimeo\.com/video/(\d+)"), "비메오", "https://vimeo.com/{0}"),
    (re.compile(r"https://tv\.kakao\.com/embed/player/cliplink/(\d+)"), "카카오TV",
     "https://tv.kakao.com/v/{0}"),
    (re.compile(r"https://tv\.naver\.com/embed/(\d+)"), "네이버TV", "https://tv.naver.com/v/{0}"),
]


def unembed(m):
    src = html.unescape(m.group(1))
    if src.startswith("/") or src.startswith("http://127.0.0.1") or src.startswith("http://localhost"):
        return m.group(0)
    for rule, name, fmt in WATCH_RULES:
        r = rule.match(src)
        if r:
            return link(fmt.format(*r.groups()), f"▶ {name}에서 보기")
    for key in ("twitframe.com/show?url=", "facebook.com/plugins/post.php?href="):
        if key in src:
            return link(urllib.parse.unquote(src.split(key, 1)[1].split("&")[0]), "▶ 원본 게시물 보기")
    host = urllib.parse.urlsplit(src).netloc or "외부"
    return link(src, f"▶ 외부 콘텐츠 열기 ({host})")


def link(url, text):
    return (f'<a class="kit-embed-link" href="{html.escape(url)}" target="_blank" '
            f'rel="noopener noreferrer">{html.escape(text)}</a>')


def icon_svg(m):
    icon = ICONS.get("icons", {}).get(m.group(1))
    if not icon:
        return ""
    w = icon.get("width", ICONS.get("width", 24))
    h = icon.get("height", ICONS.get("height", 24))
    return (f'<svg class="iconify" width="1em" height="1em" viewBox="0 0 {w} {h}" '
            f'style="vertical-align:-0.125em" aria-hidden="true">{icon["body"]}</svg>')


def rewrite_html(body):
    body = DROP_SCRIPT_RE.sub("", body)
    body = ICON_RE.sub(icon_svg, body)
    body = IFRAME_RE.sub(unembed, body)
    body = CDN_RE.sub(lambda m: f"/_kit/cdn/{m.group(1)}/{m.group(2)}", body)
    return body


# 위키 색: 관리판에서 고른 색(panel.json 의 "color")을 상단 머리글에만 입힌다. 파일이 바뀌면 곧바로 반영.
PANEL_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel.json")
DEFAULT_COLOR = "#3b5bdb"
_theme = {"mtime": None, "css": ""}


def darker(hex_color, f=0.88):
    h = hex_color.lstrip("#")
    return "#%02x%02x%02x" % tuple(int(int(h[i:i + 2], 16) * f) for i in (0, 2, 4))


def theme_css():
    try:
        mtime = os.path.getmtime(PANEL_JSON)
    except OSError:
        mtime = 0
    if mtime != _theme["mtime"]:
        color = DEFAULT_COLOR
        try:
            c = json.load(open(PANEL_JSON, encoding="utf-8")).get("color", DEFAULT_COLOR)
            if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
                color = c
        except (OSError, ValueError):
            pass
        _theme["css"] = ("<style>"
                         f"header#main{{background-color:{color}!important}}"
                         "header#main a,header#main a#logo{color:#fff!important}"
                         f"header#main a:hover,header a#logo:hover,.top_cel a:hover{{background-color:{darker(color)}!important}}"
                         "header#section{background-color:#fff}"
                         ".top_cel_in{background:#fff!important;border:1px solid #ddd;box-shadow:0 4px 12px rgba(0,0,0,.12)}"
                         ".top_cel_in a{color:#222!important}.top_cel_in a:hover{background-color:#eef!important}"
                         f"#nav_bar{{background-color:{color}!important}}#nav_bar a{{color:#fff!important}}"
                         f"button.search_button,button.search_button:hover{{background:{color}!important;color:#fff!important}}"
                         f"button.search_button:hover{{background:{darker(color)}!important}}"
                         f".kit-random{{background:{color}!important}}.kit-random:hover{{background:{darker(color)}!important}}"
                         f"#nav_bar a:hover{{background-color:{darker(color)}!important}}"
                         + MOBILE_CSS + "</style>")
        _theme["mtime"] = mtime
    return _theme["css"]


# 휴대폰(좁은 화면): 검색줄을 한 줄로, 넓은 표는 옆으로 밀어 보기
MOBILE_CSS = (
    ".table_safe{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}"
    "@media (max-width:720px){"
    "form.only_mobile{display:flex!important;align-items:center;gap:4px;flex-wrap:nowrap;padding:4px 8px;box-sizing:border-box}"
    "form.only_mobile input.search{flex:1 1 auto;min-width:0;width:auto!important;margin:0!important}"
    "form.only_mobile .search_button,form.only_mobile .kit-random{flex:0 0 auto;margin:0!important}"
    ".table_safe td,.table_safe th{word-break:keep-all;min-width:3.5em}"
    "}")

LAYOUT_JS = """<script>(function(){
/* 목록·도구·사용자 메뉴를 오른쪽에서 왼쪽 로고 옆으로 옮긴다. 검색창은 오른쪽에 둔다. */
var left=document.querySelector('header#main #left'),cels=document.querySelectorAll('header#main #right > .top_cel');
if(!left||!cels.length)return;left.style.display='inline-flex';left.style.alignItems='center';left.style.gap='4px';
cels.forEach(function(c){left.appendChild(c)})})();
(function(){/* 검색 단추: 검색은 돋보기, 바로 가기는 오른쪽 화살표, 순서는 돋보기 → 화살표 */
var arrow='<svg width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4 11h12.17l-5.59-5.59L12 4l8 8-8 8-1.41-1.41L16.17 13H4z"/></svg>';
var lens='<svg width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14"/></svg>';
document.querySelectorAll('button.search_button#goto').forEach(function(g){g.innerHTML=arrow;g.title='바로 가기';
var sb=g.parentNode.querySelector('button.search_button#search');if(sb){sb.innerHTML=lens;sb.title='검색';g.parentNode.insertBefore(sb,g)}})})();</script>"""

SUGGEST_JS = """<script>(function(){
var inputs=document.querySelectorAll('input[type=search],input[name=search]');if(!inputs.length)return;
var dl=document.createElement('datalist');dl.id='kit-suggest';document.body.appendChild(dl);var timer,last='';
inputs.forEach(function(inp){
var f=inp.form||inp.parentElement;if(f&&!f.querySelector('.kit-random')){var a=document.createElement('a');
a.href='/random';a.className='kit-random';a.title='아무 문서나 보기';a.innerHTML='<svg viewBox="0 0 24 24" style="width:100%;height:100%" aria-hidden="true"><path fill="currentColor" d="M10.59 9.17 5.41 4 4 5.41l5.17 5.17zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4zm.33 9.41-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04z"/></svg>';a.style.cssText='display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;width:32px;height:32px;padding:3px;border-radius:6px;color:#fff;text-decoration:none;vertical-align:middle;margin-right:4px';inp.parentNode.insertBefore(a,inp)}
inp.setAttribute('list','kit-suggest');inp.setAttribute('autocomplete','off');
inp.addEventListener('input',function(){var q=inp.value.trim();clearTimeout(timer);if(!q||q===last)return;
timer=setTimeout(function(){last=q;fetch('/_kit/suggest?q='+encodeURIComponent(q)).then(function(r){return r.json()})
.then(function(list){dl.innerHTML='';list.forEach(function(t){var o=document.createElement('option');o.value=t;dl.appendChild(o)})})
.catch(function(){})},200)})})})();</script>"""


def add_suggest(body):
    """모든 페이지에 색·휴대폰 CSS 를 넣고, 검색창에 제목 자동완성과 아무 문서나 보기 단추를 붙인다."""
    body = body.replace("</head>", theme_css() + "</head>", 1)
    return body.replace("</body>", LAYOUT_JS + SUGGEST_JS + "</body>", 1)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream = ("127.0.0.1", 3001)
    cdn_dir = ""
    wiki_db = ""
    passthrough = False  # PHP 엔진(DokuWiki·MediaWiki)·내장 마크다운 엔진: 고치지 않고 그대로 넘긴다

    def _send_bytes(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _suggest(self):
        """검색창 자동완성: 입력한 글자로 시작하는 문서 제목 10개(제목 색인으로 바로 찾음)."""
        q = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("q") or [""])[0].strip()
        out = []
        if q:
            try:
                db = sqlite3.connect(f"file:{os.path.abspath(self.wiki_db)}?mode=ro", uri=True, timeout=5)
                out = [r[0] for r in db.execute(
                    "select title from data where title >= ? and title < ? order by title limit 10",
                    (q, q + "\U0010ffff"))]
                db.close()
            except sqlite3.Error:
                out = []
        out = [("분류:" + t[9:]) if t.startswith("category:") else t for t in out]
        self._send_bytes(json.dumps(out, ensure_ascii=False).encode("utf-8"), "application/json")

    def log_message(self, *args):
        pass

    def _serve_cdn(self):
        rel = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path[len("/_kit/cdn/"):])
        path = os.path.normpath(os.path.join(self.cdn_dir, rel))
        if not path.startswith(os.path.normpath(self.cdn_dir)) or not os.path.isfile(path):
            self.send_error(404)
            return
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def _proxy(self):
        if self.path.startswith("/_kit/cdn/") and not self.passthrough:
            return self._serve_cdn()
        if self.path.startswith("/_kit/suggest") and self.wiki_db and not self.passthrough:
            return self._suggest()
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0:
            self.send_error(400)
            return
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "accept-encoding", "connection")}
        if self.passthrough:  # 엔진이 공개 주소를 알도록 원래 주소를 그대로
            headers["Host"] = self.headers.get("Host", "%s:%d" % self.upstream)
            headers.setdefault("X-Forwarded-For", self.client_address[0])
        else:
            headers["Host"] = "%s:%d" % self.upstream
        headers["Accept-Encoding"] = "identity"
        conn = http.client.HTTPConnection(*self.upstream, timeout=300)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
        except OSError:
            # 상태 줄에는 한글을 넣을 수 없다(latin-1). 안내는 본문으로 보낸다.
            page = ('<meta charset="utf-8"><meta http-equiv="refresh" content="10">'
                    '<div style="font-size:16px;padding:24px;line-height:1.7">'
                    '위키 엔진이 아직 준비 중입니다.<br>문서가 많으면 켜는 데 몇 분 걸릴 수 있습니다.<br>'
                    '10초마다 자동으로 다시 시도합니다.</div>').encode("utf-8")
            self.send_response(503, "Service Unavailable")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        finally:
            conn.close()
        ctype = resp.getheader("Content-Type", "")
        if "text/html" in ctype and not self.passthrough:
            data = add_suggest(rewrite_html(data.decode("utf-8", "replace"))).encode("utf-8")
        self.send_response(resp.status, resp.reason)
        for k, v in resp.getheaders():
            kl = k.lower()
            if kl in ("content-length", "transfer-encoding", "connection", "content-encoding"):
                continue
            if kl == "location" and not self.passthrough:
                v = v.replace("%s:%d" % self.upstream, self.headers.get("Host", ""))
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    do_GET = do_POST = do_HEAD = do_PUT = do_DELETE = do_PATCH = _proxy


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("assets_dir")
    ap.add_argument("--listen", default="127.0.0.1:3000")
    ap.add_argument("--upstream", default="127.0.0.1:3001")
    ap.add_argument("--wiki-db", default="", help="openNAMU 위키 DB(wikis/opennamu/data.db). 주면 검색창에 제목 자동완성이 생긴다")
    ap.add_argument("--pass", dest="passthrough", action="store_true",
                    help="고치지 않고 그대로 넘긴다(openNAMU 가 아닌 엔진)")
    args = ap.parse_args()
    Handler.passthrough = args.passthrough
    host, port = args.listen.rsplit(":", 1)
    uhost, uport = args.upstream.rsplit(":", 1)
    Handler.upstream = (uhost, int(uport))
    Handler.wiki_db = args.wiki_db
    Handler.cdn_dir = os.path.join(os.path.abspath(args.assets_dir), "cdn")
    with open(os.path.join(args.assets_dir, "icons.json"), encoding="utf-8") as f:
        ICONS.update(json.load(f))
    print(f"중계 서버: http://{host}:{port}  →  위키 엔진 {uhost}:{uport}{' (그대로 넘김)' if args.passthrough else ''}",
          flush=True)
    Server((host, int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()
