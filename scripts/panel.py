"""애니위키 관리판: 설치·켜기·끄기·공개·내보내기·가져오기를 브라우저 화면 하나에서 한다 (파이썬 표준 라이브러리만 사용).

    python panel.py            # http://127.0.0.1:3100 에 관리판을 열고 브라우저를 띄운다

관리판이 위키 엔진(openNAMU, 3001)과 중계 서버(offline_proxy, 3000)를 띄우고 끈다.
"""
import json
import re
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 임베디드 파이썬은 스크립트 폴더를 path에 넣지 않음

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPTS)
WIKI = os.path.join(ROOT, "wiki")
PANEL_PORT = 3100
SETTINGS = os.path.join(ROOT, "panel.json")
WIN = os.name == "nt"
ENGINE = os.path.join(WIKI, "main.amd64.exe" if WIN else "main.bin")
NO_WINDOW = 0x08000000 if WIN else 0  # CREATE_NO_WINDOW

procs = {}
lock = threading.Lock()
_cache = {}


DEFAULTS = {"listen": "127.0.0.1:3000", "color": "#3b5bdb"}


def settings():
    """관리판에서 고른 설정(panel.json). 관리판을 껐다 켜도 그대로 남는다.
    wiki_on·public 은 '켜 둔 상태'도 기억해 두었다가 다음에 관리판을 열면 다시 켠다."""
    for path in (SETTINGS, SETTINGS + ".bak"):  # 본 파일이 깨졌으면 직전 판으로
        try:
            s = json.load(open(path, encoding="utf-8"))
            if isinstance(s, dict):
                return dict(DEFAULTS, **s)
        except Exception:
            pass
    return dict(DEFAULTS)


def save_settings(s):
    """저장 도중 꺼져도 설정이 날아가지 않게: 임시 파일에 다 쓴 뒤 바꿔 끼우고, 직전 판은 .bak 으로 둔다."""
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    if os.path.exists(SETTINGS):
        try:
            shutil.copyfile(SETTINGS, SETTINGS + ".bak")
        except OSError:
            pass
    os.replace(tmp, SETTINGS)


def remember(**kv):
    s = settings()
    s.update(kv)
    save_settings(s)


def alive(name):
    p = procs.get(name)
    return p is not None and p.poll() is None


def spawn(name, args, log, cwd=None):
    out = open(os.path.join(ROOT, log), "a", encoding="utf-8", errors="replace")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    procs[name] = subprocess.Popen(args, cwd=cwd or ROOT, stdout=out, stderr=subprocess.STDOUT,
                                   env=env, creationflags=NO_WINDOW)


def stop(name):
    p = procs.pop(name, None)
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()


def start_proxy():
    stop("proxy")
    args = [sys.executable, os.path.join(SCRIPTS, "offline_proxy.py"), os.path.join(ROOT, "assets"),
            "--listen", settings()["listen"], "--upstream", "127.0.0.1:3001",
            "--wiki-db", os.path.join(WIKI, "data.db")]
    spawn("proxy", args, "proxy.log")


def start_wiki(open_browser=True):
    with lock:
        if not os.path.exists(os.path.join(WIKI, "data.db")):
            return "아직 설치되지 않았습니다"
        if alive("import"):
            return "가져오는 중입니다. 끝난 뒤에 켜세요"
        if not alive("engine"):
            spawn("engine", [ENGINE, "3001", "--localhost"], "server.log", cwd=WIKI)
        if not alive("proxy"):
            start_proxy()

    def open_when_ready():  # 엔진이 준비되면 첫 화면을 브라우저로 열고, 공개를 켜 두었으면 다시 공개한다
        for _ in range(600):
            if port_open(3001):
                if open_browser:
                    webbrowser.open("http://" + settings()["listen"].replace("0.0.0.0", "127.0.0.1") + "/")
                if settings().get("public") and not alive("tunnel"):
                    tunnel(True)
                return
            time.sleep(1)
    threading.Thread(target=open_when_ready, daemon=True).start()
    return "켰습니다. 준비되면 첫 화면이 자동으로 열립니다"


def stop_wiki():
    with lock:
        for n in ("tunnel", "proxy", "engine"):
            stop(n)
    return "껐습니다"


def run_install():
    if alive("install"):
        return "이미 설치 중입니다"
    if not WIN:
        return "리눅스는 README 의 '리눅스 서버에 설치하기'를 따라 주세요(bash server/install.sh)"
    stop_wiki()
    open(os.path.join(ROOT, "install.log"), "w").close()
    spawn("install", ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                      os.path.join(SCRIPTS, "install.ps1")], "install.log")
    return "설치를 시작했습니다"


def tunnel(on):
    if not on:
        stop("tunnel")
        _cache.pop("url", None)
        return "공개를 껐습니다"
    if not alive("proxy"):
        return "먼저 위키를 켜세요"
    if alive("tunnel"):
        return "이미 공개 중입니다"
    try:
        import cloudflared
        exe = cloudflared.ensure()
    except Exception as e:
        return f"터널 프로그램을 받지 못했습니다: {e}"
    open(os.path.join(ROOT, "tunnel.log"), "w").close()
    spawn("tunnel", [exe, "tunnel", "--no-autoupdate", "--url", "http://" + settings()["listen"]], "tunnel.log")
    return "공개를 시작했습니다. 잠시 뒤 공개 주소가 표시됩니다"


EXPORT_DIR = os.path.join(ROOT, "export")


IMPORT_DIR = os.path.join(ROOT, "import")


def import_files():
    """import 폴더에 둔 openNAMU 형식 파일(.db .sqlite .sqlite3)."""
    try:
        return sorted(f for f in os.listdir(IMPORT_DIR) if f.lower().endswith((".db", ".sqlite", ".sqlite3")))
    except OSError:
        return []


def run_import(name):
    if alive("import"):
        return "이미 가져오는 중입니다"
    if not os.path.exists(os.path.join(WIKI, "data.db")):
        return "아직 설치되지 않았습니다"
    if name not in import_files():
        return "import 폴더에서 파일을 고르세요"
    if alive("engine") or alive("export") or alive("install"):
        return "먼저 위키를 끄세요(가져오기는 위키 DB 를 바꾸므로 위키가 꺼져 있을 때만 합니다)"
    open(os.path.join(ROOT, "import.log"), "w").close()
    spawn("import", [sys.executable, os.path.join(SCRIPTS, "wiki_pack.py"), "import", WIKI,
                     os.path.join(IMPORT_DIR, name)], "import.log")
    return "가져오기를 시작했습니다. 끝나면 [켜기]로 위키를 켜세요"


def run_export(target):
    if target not in ("mediawiki", "dokuwiki", "markdown", "opennamu"):
        return "알 수 없는 형식입니다"
    if alive("import"):
        return "가져오는 중입니다. 끝난 뒤에 내보내세요"
    if alive("export"):
        return "이미 내보내는 중입니다"
    if not os.path.exists(os.path.join(WIKI, "data.db")):
        return "아직 설치되지 않았습니다"
    if alive("engine") and not port_open(3001):
        return "위키 엔진이 시작하는 중입니다. 준비된 뒤에 다시 누르세요"
    os.makedirs(EXPORT_DIR, exist_ok=True)
    open(os.path.join(ROOT, "export.log"), "w").close()
    if target == "opennamu":
        spawn("export", [sys.executable, os.path.join(SCRIPTS, "wiki_pack.py"), "export", WIKI], "export.log")
        return "내보내기를 시작했습니다(openNAMU 형식은 변환이 없어 빠릅니다)"
    spawn("export", [sys.executable, os.path.join(SCRIPTS, "convert_wiki.py"), WIKI, "--to", target], "export.log")
    return "내보내기를 시작했습니다. 문서가 많으면 남은 시간이 진행 줄에 표시됩니다"


def tunnel_url():
    import re
    if not alive("tunnel"):
        return ""
    for line in tail("tunnel.log", 200):
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            return m.group(0)
    return ""


KIT_VERSION = "0.1"


def dir_size(path):
    total = 0
    for dp, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return total


def info():
    """키트·엔진 정보(1분 동안 기억해 둠: 색인 폴더 크기 계산이 느릴 수 있어서)."""
    if time.time() - _cache.get("info_at", 0) < 60:
        return _cache["info"]
    src = json.load(open(os.path.join(ROOT, "sources.json"), encoding="utf-8"))
    m = re.search(r"/download/([^/]+)/", src["tools"]["opennamu"]["url"])
    mb = lambda n: round(n / 1e6, 1)  # noqa: E731
    db = os.path.join(WIKI, "data.db")
    out = {"kit": KIT_VERSION, "engine": "openNAMU " + (m.group(1) if m else "?"),
           "db_mb": mb(os.path.getsize(db)) if os.path.exists(db) else 0,
           "index_mb": mb(dir_size(os.path.join(WIKI, "data", "bleve")))}
    _cache["info"], _cache["info_at"] = out, time.time()
    return out


def tail(name, n=12):
    try:
        with open(os.path.join(ROOT, name), encoding="utf-8", errors="replace") as f:
            return f.readlines()[-n:]
    except OSError:
        return []


def port_open(port):
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def status():
    s = settings()
    st = {"installed": os.path.exists(os.path.join(WIKI, "data.db")), "listen": s["listen"],
          "color": s.get("color", "#3b5bdb"),
          "running": {n: alive(n) for n in ("engine", "proxy", "install", "tunnel", "export", "import")}}
    st["ready"] = st["running"]["engine"] and port_open(3001)
    # 위키 엔진이 '켜지는 중'에는 data.db 를 열지 않는다.
    # (엔진이 시작할 때 DB 방식을 바꾸는 동안 다른 연결이 있으면 계속 기다리며 켜지지 않는다)
    # 꺼져 있거나 준비가 끝난 뒤에는 읽는다(준비 뒤에는 1분에 한 번). 마지막으로 읽은 수는 기억해 둔다.
    starting = st["running"]["engine"] and not st["ready"]
    if (st["installed"] and not starting and not st["running"]["install"]
            and (not st["ready"] or time.time() - _cache.get("docs_at", 0) > 60)):
        try:
            db = sqlite3.connect(f"file:{os.path.join(WIKI, 'data.db')}?mode=ro", uri=True, timeout=1)
            r = db.execute("select count(*) from data").fetchone()
            db.close()
            _cache["docs"], _cache["docs_at"] = r[0], time.time()
            if _cache["docs"] is not None and s.get("docs") != _cache["docs"]:
                remember(docs=_cache["docs"])
        except Exception:
            pass
    st["docs"] = _cache.get("docs", s.get("docs"))
    du = shutil.disk_usage(ROOT)
    st["disk_free_gb"] = round(du.free / 1e9, 1)
    st["install_log"] = tail("install.log", 12)
    st["info"] = info()
    st["update"] = dict(_cache.get("update") or {}, on=settings().get("update_notice", True))
    st["import_files"], st["import_dir"] = import_files(), IMPORT_DIR
    st["import_log"] = tail("import.log", 6)
    st["export_log"] = tail("export.log", 6)
    st["export_dir"] = EXPORT_DIR
    st["public_url"] = tunnel_url()
    return st


PAGE = r"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>애니위키 관리판</title><style>
body{font-family:system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#222}
h1{font-size:22px}details.sec{border:1px solid #ddd;border-radius:8px;padding:12px 16px;margin:10px 0}details.sec>summary{cursor:pointer;list-style:none;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}details.sec>summary::-webkit-details-marker{display:none}details.sec>summary::before{content:'▸';color:#888;width:1em}details.sec[open]>summary::before{content:'▾'}details.sec>summary h2{margin:0}details.sec[open]>summary{margin-bottom:10px}.sum{font-size:13px;color:#666}.sum .on{color:#0a0}
h2{font-size:16px;margin:0 0 8px}button{font-size:14px;padding:6px 12px;margin:2px;cursor:pointer}
.on{color:#0a0}.off{color:#999}pre{background:#f6f6f6;padding:8px;font-size:12px;white-space:pre-wrap;max-height:220px;overflow:auto}
.warn{font-size:12px;color:#a60}label{margin-right:12px}
</style><div id="upd" hidden style="background:#fff4e0;border:1px solid #f0c060;border-radius:8px;padding:10px 14px;margin:12px 0"></div>
<h1>애니위키 관리판</h1>
<details class="sec" id="sec-st" data-default="1" open><summary><h2>상태</h2><span class="sum" id="sum-st"></span></summary><div id="st">불러오는 중…</div></details>
<details class="sec" id="sec-wiki" data-default="1" open><summary><h2>위키</h2><span class="sum" id="sum-wiki"></span></summary>
<button onclick="act('start')">켜기</button><button onclick="act('stop')">끄기</button>
<button onclick="openWiki()">위키 열기</button></details>
<details class="sec" id="sec-color" data-default="0"><summary><h2>위키 색</h2><span class="sum" id="sum-color"></span></summary>
<span id="swatch" style="display:inline-block;width:28px;height:28px;border-radius:6px;vertical-align:middle;border:1px solid #ccc"></span>
<select id="preset" onchange="if(this.value)setColor(this.value)">
<option value="">추천 색 고르기…</option>
<option value="#3b5bdb">인디고 블루 (기본)</option><option value="#1c3f94">딥 오션</option><option value="#1971c2">코발트</option>
<option value="#364fc7">로열 블루</option><option value="#5f3dc4">바이올렛</option><option value="#862e9c">자두</option>
<option value="#c2255c">라즈베리</option><option value="#c92a2a">레드</option><option value="#e8590c">오렌지</option>
<option value="#343a40">차콜</option><option value="#212529">블랙</option></select>
<input type="color" id="picker" onchange="setColor(this.value)" title="원하는 색 직접 고르기">
<span style="font-size:13px;color:#555">위키 맨 위 머리글 색입니다. 고르면 새로고침만으로 바로 바뀝니다.</span></details>
<details class="sec" id="sec-pub" data-default="0"><summary><h2>인터넷에 공개</h2><span class="sum" id="sum-pub"></span></summary>
<button onclick="pub(1)">공개하기</button><button onclick="act2('tunnel?on=0')">공개 끄기</button>
<div id="pubinfo" style="margin:6px 0;font-weight:bold"></div>
<p style="font-size:13px;color:#555">공유기 설정 없이 Cloudflare 임시 공개 주소(https)를 만듭니다. 켤 때마다 주소가 바뀝니다. [공개 끄기]를 누르기 전까지는 위키를 켤 때마다 다시 공개됩니다.<br>
<b>공개 전에</b>: 위키에서 먼저 가입해 관리자가 되고, 관리자 설정 → 권한에서 비로그인(ip) 사용자의 편집을 막으세요.
공개하는 순간 그 사이트의 운영 책임(권리 침해·게시중단 요청 대응 등)은 공개한 사람에게 있습니다.</p></details>
<details class="sec" id="sec-export" data-default="0"><summary><h2>내보내기</h2><span class="sum" id="sum-export"></span></summary>
<button onclick="exp('opennamu')">openNAMU 형식으로 내보내기 (백업·다른 애니위키로 옮기기)</button><br>
<button onclick="exp('mediawiki')">MediaWiki 로 내보내기</button><button onclick="exp('dokuwiki')">DokuWiki 로 내보내기</button>
<button onclick="exp('markdown')">Markdown 으로 내보내기</button>
<div id="eprog" style="margin:6px 0;font-weight:bold"></div>
<p style="font-size:13px;color:#555">위키의 문서를 파일로 만들어 <span id="expdir"></span> 폴더에 저장합니다.<br>
openNAMU: <code>anywiki-opennamu.db</code> → 다른 애니위키의 '가져오기'로 넣거나, 새 openNAMU 의 data.db 로 그대로 씁니다(문서 표만, 계정·IP 기록은 넣지 않음).<br>
MediaWiki: <code>anywiki-mediawiki.xml.gz</code> → <code>php maintenance/run.php importDump</code> 로 가져옵니다.<br>
DokuWiki: <code>anywiki-dokuwiki.zip</code> → DokuWiki 폴더에 풀고 <code>php bin/indexer.php</code> 로 색인을 만듭니다.<br>
Markdown: <code>anywiki-markdown.zip</code> → 문서마다 .md 파일 하나. Obsidian 같은 편집기에서 폴더째 엽니다.<br>
표·목록·각주·접기·틀 등 흔한 문법을 옮기고, 이미지와 #!html 은 옮기지 않습니다. 문서의 라이선스는 위키 운영자가 정한 대로 따르세요.</p>
<pre id="elog"></pre></details>
<details class="sec" id="sec-import" data-default="0"><summary><h2>가져오기 (openNAMU 형식)</h2><span class="sum" id="sum-import"></span></summary>
<select id="ifile"></select> <button onclick="imp()">가져오기</button>
<div id="iprog" style="margin:6px 0;font-weight:bold"></div>
<p style="font-size:13px;color:#555">애니위키가 내보낸 <code>anywiki-opennamu.db</code> 나 다른 openNAMU 위키의 <code>data.db</code> 를
<code id="impdir"></code> 폴더에 넣고 고르세요.<br>
문서마다 내 쪽보다 새 판만 역사 뒤에 이어 붙입니다. 내 쪽이 같거나 더 새로우면 건너뛰고, 지우기는 옮기지 않습니다.
가져온 판은 역사 요약에 [가져옴 파일이름] 이 붙습니다. <b>위키를 끈 상태에서만</b> 가져옵니다.<br>
파일의 내용은 검증하지 않으니 믿을 수 있는 곳에서 받은 파일만 넣으세요.</p>
<pre id="implog"></pre></details>
<details class="sec" id="sec-update" data-default="0"><summary><h2>새 판 알림</h2><span class="sum" id="sum-update"></span></summary>
<label><input type="checkbox" id="updon" onchange="api('/api/update_notice?on='+(this.checked?1:0)).then(load)"> GitHub 에 새 판이 나오면 알려 주기</label>
<button onclick="api('/api/update_check').then(load)">지금 확인</button>
<div id="updst" style="font-size:13px;color:#555;margin-top:6px"></div>
<p style="font-size:12px;color:#777">12시간에 한 번 GitHub(iamtalker/anywiki-kit)의 최신 릴리스만 확인합니다. 보내는 정보는 없고, 스스로 설치하지 않습니다.
새 판은 릴리스 내용을 보고 직접 받아 이 폴더에 덮어쓰세요(<code>wiki</code> 폴더는 그대로 두면 됩니다).</p></details>
<details class="sec" id="sec-install" data-default="0"><summary><h2>설치</h2><span class="sum" id="sum-install"></span></summary>
<button onclick="install()">설치 / 다시 설치</button>
<p style="font-size:13px;color:#555">위키 엔진(openNAMU)을 받고 빈 위키를 만듭니다(몇 분). 다시 설치해도 이미 있는 위키 문서는 지우지 않습니다. 위키는 설치 동안 꺼집니다.</p><pre id="inslog"></pre></details>
<script>
let listen="127.0.0.1:3000";
async function api(p){const r=await fetch(p,{method:'POST'});return (await r.json()).msg}
async function act(a){alert(await api('/api/'+a));load()}
async function act2(p){alert(await api('/api/'+p));load()}
async function pub(){if(confirm('위키를 인터넷에 공개할까요? 누구나 주소로 접속할 수 있게 됩니다.')){act2('tunnel?on=1')}}
async function setColor(c){await api('/api/color?c='+encodeURIComponent(c));load()}
async function install(){if(confirm('설치할까요? 몇 분 걸립니다.')){alert(await api('/api/install'));load()}}
async function exp(t){if(confirm('내보낼까요?')){alert(await api('/api/export?to='+t));load()}}
async function imp(){var f=document.getElementById('ifile').value;if(!f){alert('import 폴더에 파일을 넣은 뒤 고르세요');return}
if(confirm(f+' 을(를) 가져올까요?')){alert(await api('/api/import?file='+encodeURIComponent(f)));load()}}
function openWiki(){window.open('http://'+listen.replace('0.0.0.0','127.0.0.1')+'/','_blank')}
function esc(t){return String(t==null?'':t).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function dot(b){return b?'<span class=on>●</span>':'<span class=off>○</span>'}
async function load(){const s=await (await fetch('/api/status')).json();listen=s.listen;
var i=s.info;document.getElementById('st').innerHTML=(s.installed?'설치됨 · 문서 '+(s.docs??'?').toLocaleString()+'개':'아직 설치되지 않음 — 아래 [설치]를 누르세요')+
' · 디스크 여유 '+s.disk_free_gb+'GB<br><span style="font-size:13px;color:#555">애니위키 '+i.kit+' · 위키 엔진 '+i.engine+
' · 위키 DB '+i.db_mb+'MB · 검색 색인 '+i.index_mb+'MB</span><br>'+dot(s.running.engine)+' 위키 엔진 '+dot(s.running.proxy)+' 중계 서버 '+
(s.running.install?'· <b>설치 진행 중</b>':'')+
(s.running.engine?(s.ready?'<br><b class=on>위키 준비됨 — [위키 열기]를 누르세요</b>':'<br><b>위키 엔진 시작 중…</b>'):'');
sum('color','<span style="display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:middle;background:'+esc(s.color)+'"></span> '+esc(s.color));
sum('pub',s.public_url?'<span class=on>공개 중</span> '+esc(s.public_url):(s.running.tunnel?'주소 만드는 중…':'꺼짐'));
var el=s.export_log.filter(function(l){return l.indexOf('진행')===0||l.indexOf('완료')===0}).pop();
sum('export',s.running.export?'내보내는 중 · '+esc(el||''):(el&&el.indexOf('완료')===0?'마지막: '+esc(el.split('→')[0]):''));
var uu=s.update||{};sum('update',uu.on===false?'꺼짐':(uu.newer?'<b>새 판 '+esc(uu.latest)+'</b>':(uu.latest?'최신 판':'')));
sum('install',(s.installed?'설치됨':'설치 전')+(s.running.install?' · <b>설치 중</b>':''));
document.getElementById('inslog').textContent=s.install_log.join('');
var u=s.update||{},ub=document.getElementById('upd');document.getElementById('updon').checked=u.on!==false;
ub.hidden=!(u.on!==false&&u.newer);
if(u.newer&&ub.dataset.v!==u.latest){ub.dataset.v=u.latest;ub.innerHTML='<b>새 판이 나왔습니다: '+esc(u.name||u.latest)+'</b> ('+esc(u.published||'')+') · 지금 '+esc(u.current)+
' · <a href="'+esc(u.url)+'" target=_blank>릴리스 보기</a>'+(u.notes?'<details style="margin-top:6px"><summary>달라진 점</summary><pre>'+esc(u.notes)+'</pre></details>':'')}
document.getElementById('updst').textContent=u.on===false?'알림 꺼짐':(u.latest?(u.newer?'새 판 '+u.latest+' 이 있습니다':'최신 판입니다 ('+u.current+', GitHub 최신 '+u.latest+')')+
(u.checked_at?' · 확인 '+new Date(u.checked_at*1000).toLocaleString():''):(u.error?'확인하지 못했습니다: '+u.error:'확인 전'));
document.getElementById('elog').textContent=s.export_log.join('');
var pl=s.export_log.filter(l=>l.startsWith('진행')||l.startsWith('완료')).pop();
document.getElementById('eprog').textContent=s.running.export?('내보내는 중 · '+(pl||'준비 중…')):(pl&&pl.startsWith('완료')?pl:'');
document.getElementById('expdir').textContent=s.export_dir;
var fs=document.getElementById('ifile'),fk=s.import_files.join('\n');if(fs.dataset.k!==fk){var keep=fs.value;fs.dataset.k=fk;
fs.innerHTML=s.import_files.length?s.import_files.map(f=>'<option>'+esc(f)+'</option>').join(''):'<option value="">(import 폴더가 비어 있음)</option>';if(keep)fs.value=keep}
document.getElementById('impdir').textContent=s.import_dir;document.getElementById('implog').textContent=s.import_log.join('');
var il=s.import_log.filter(l=>l.startsWith('진행')||l.startsWith('완료')||l.startsWith('가져온')).pop();
var ig=s.import_log.filter(l=>l.startsWith('가져온')).pop();
document.getElementById('iprog').textContent=s.running.import?('가져오는 중 · '+(il||'준비 중…')):(ig||il||'');
sum('import',s.running.import?'<b>가져오는 중</b>':(s.import_files.length?'파일 '+s.import_files.length+'개':''));
document.getElementById('swatch').style.background=s.color;document.getElementById('picker').value=s.color;
document.getElementById('pubinfo').innerHTML=s.public_url?('공개 주소: <a href="'+s.public_url+'" target=_blank>'+s.public_url+'</a>'):(s.running.tunnel?'공개 주소를 만드는 중…':'')}
document.querySelectorAll('details.sec').forEach(function(d){
  try{var v=localStorage.getItem('kit-'+d.id);if(v!==null)d.open=v==='1'}catch(e){}
  d.addEventListener('toggle',function(){try{localStorage.setItem('kit-'+d.id,d.open?'1':'0')}catch(e){}})});
function esc(t){return String(t==null?'':t).replace(/[&<>"']/g,function(c){return '&#'+c.charCodeAt(0)+';'})}
function sum(k,h){var e=document.getElementById('sum-'+k);if(e&&e.innerHTML!==h)e.innerHTML=h}
load();setInterval(load,3000);
</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        b = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            return self.send(200, PAGE, "text/html; charset=utf-8")
        if path == "/api/status":
            return self.send(200, json.dumps(status(), ensure_ascii=False), "application/json")
        self.send(404, "없음", "text/plain; charset=utf-8")

    def do_POST(self):
        u = urlsplit(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/start":
            remember(wiki_on=True)
            msg = start_wiki()
        elif u.path == "/api/stop":
            remember(wiki_on=False)
            msg = stop_wiki()
        elif u.path == "/api/color":
            c = (q.get("c") or [""])[0]
            if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
                st = settings()
                st["color"] = c
                save_settings(st)
                msg = "색을 바꿨습니다. 위키 페이지를 새로고침하세요"
            else:
                msg = "색 형식이 올바르지 않습니다"
        elif u.path == "/api/tunnel":
            on = (q.get("on") or ["1"])[0] == "1"
            msg = tunnel(on)
            if not on or "시작" in msg or "이미" in msg:
                remember(public=on)
        elif u.path == "/api/install":
            msg = run_install()
        elif u.path == "/api/update_check":
            import update_check
            _cache["update"] = update_check.check(force=True)
            msg = update_check.message(_cache["update"])
        elif u.path == "/api/update_notice":
            st = settings()
            st["update_notice"] = (q.get("on") or ["1"])[0] == "1"
            save_settings(st)
            msg = "새 판 알림을 " + ("켰습니다" if st["update_notice"] else "껐습니다")
        elif u.path == "/api/export":
            msg = run_export((q.get("to") or [""])[0])
        elif u.path == "/api/import":
            msg = run_import((q.get("file") or [""])[0])
        else:
            return self.send(404, "{}", "application/json")
        self.send(200, json.dumps({"msg": msg}, ensure_ascii=False), "application/json")


def cleanup_leftovers():
    """전에 관리판 창을 그냥 닫아서 남은 위키 프로그램(엔진·중계 서버·터널)을 정리한다."""
    if not WIN:
        return
    ps = ("$root = '" + ROOT.replace("'", "''") + "'; "
          "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne " + str(os.getpid()) + " -and "
          "$_.ExecutablePath -and $_.ExecutablePath.StartsWith($root) -and "
          "$_.Name -in @('main.amd64.exe','python.exe','cloudflared.exe') } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=NO_WINDOW,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def update_loop():
    """새 판 알림: 한 시간마다 들여다보되 GitHub 에는 12시간에 한 번만 묻는다(update_check.py). 알리기만 한다."""
    import update_check
    while True:
        if settings().get("update_notice", True):
            try:
                _cache["update"] = update_check.check()
            except Exception:
                pass
        time.sleep(3600)


def main():
    cleanup_leftovers()
    os.makedirs(IMPORT_DIR, exist_ok=True)  # 가져올 파일을 넣는 곳
    threading.Thread(target=update_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PANEL_PORT), Handler)
    url = f"http://127.0.0.1:{PANEL_PORT}/"
    print(f"애니위키 관리판: {url}  (끌 때는 관리판에서 [끄기]를 누르세요)", flush=True)
    webbrowser.open(url)
    # 지난번에 위키를 켜 둔 채로 끝냈으면 다시 켠다(끄기를 누른 경우만 꺼진 채로 둔다)
    s = settings()
    if s.get("wiki_on") and os.path.exists(os.path.join(WIKI, "data.db")):
        print("지난번 설정대로 위키를 다시 켭니다" + (" (공개 포함, 주소는 새로 바뀝니다)" if s.get("public") else ""),
              flush=True)
        start_wiki(open_browser=False)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_wiki()


if __name__ == "__main__":
    main()
