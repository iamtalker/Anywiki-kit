"""애니위키 관리판: 설치·켜기·끄기·공개·내보내기·가져오기 (파이썬 표준 라이브러리만).

    python panel.py            # http://127.0.0.1:4100 에 관리판을 열고 브라우저를 띄운다

관리판이 위키 엔진 openNAMU(4001)와 중계 서버(4000)를 띄우고 끈다.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 임베디드 파이썬은 스크립트 폴더를 path에 넣지 않음
import engines  # noqa: E402
import kit  # noqa: E402

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPTS)
PANEL_PORT = 4100
WIN = os.name == "nt"
NO_WINDOW = 0x08000000 if WIN else 0  # CREATE_NO_WINDOW
KIT_VERSION = "0.6.1"
EXPORT_DIR = os.path.join(ROOT, "export")
IMPORT_DIR = os.path.join(ROOT, "import")
IMPORT_EXT = (".db", ".sqlite", ".sqlite3")
EXPORT_FORMATS = ("opennamu", "mediawiki", "dokuwiki", "markdown")
ENGINE_DESC = {"opennamu": "나무마크 문법. 실행 파일 하나라 가볍고 빠릅니다."}

procs = {}
lock = threading.Lock()
_cache = {}
DEFAULTS = {"listen": "127.0.0.1:4000", "color": "#3b5bdb"}


def settings():
    """관리판에서 고른 설정(panel.json). 관리판을 껐다 켜도 그대로 남는다.
    wiki_on·public 은 '켜 둔 상태'도 기억해 두었다가 다음에 관리판을 열면 다시 켠다."""
    return dict(DEFAULTS, **kit.settings())


def remember(**kv):
    s = kit.settings()
    s.update(kv)
    kit.save_settings(s)


def engine_name():
    return kit.current()


def eng(name=None):
    return engines.get(name or engine_name(), ROOT)


def local_url():
    return "http://" + settings()["listen"].replace("0.0.0.0", "127.0.0.1")


def alive(name):
    p = procs.get(name)
    return p is not None and p.poll() is None


def spawn(name, args, log):
    out = open(os.path.join(ROOT, log), "a", encoding="utf-8", errors="replace")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    procs[name] = subprocess.Popen(args, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                                   env=env, creationflags=NO_WINDOW, start_new_session=not WIN)


def stop(name):
    p = procs.pop(name, None)
    if p and p.poll() is None:
        kill = p.terminate if WIN else (lambda: os.killpg(p.pid, signal.SIGTERM))  # 리눅스는 딸린 프로세스까지
        try:
            kill()
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill() if WIN else os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def busy():
    """위키 데이터를 바꾸는 작업 중이면 그 이름."""
    for n, label in (("install", "설치"), ("import", "가져오기")):
        if alive(n):
            return label
    return ""


def start_proxy():
    stop("proxy")
    args = [sys.executable, os.path.join(SCRIPTS, "offline_proxy.py"), os.path.join(ROOT, "assets"),
            "--listen", settings()["listen"], "--upstream", "127.0.0.1:4001"]
    args += ["--wiki-db", os.path.join(eng().dir, "data.db")]  # 키트 모양(색·글꼴)은 중계 서버가 입힌다
    spawn("proxy", args, "proxy.log")


def start_wiki(open_browser=True):
    with lock:
        kit.migrate(ROOT)
        e = eng()
        if not e.installed():
            return f"{engines.NAMES[e.name]} 가 아직 설치되지 않았습니다. '설치' 칸에서 [설치]를 누르세요"
        if busy():
            return f"{busy()} 중입니다. 끝난 뒤에 켜세요"
        if not alive("engine"):
            procs["engine"] = e.spawn(os.path.join(ROOT, "server.log"))
        if not alive("proxy"):
            start_proxy()

    def open_when_ready():  # 엔진이 준비되면 첫 화면을 브라우저로 열고, 공개를 켜 두었으면 다시 공개한다
        for _ in range(600):
            if not alive("engine"):
                return
            if e.ready():
                if open_browser:
                    webbrowser.open(local_url() + "/")
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


def run_install(name):
    if name not in engines.ENGINES:
        return "알 수 없는 엔진입니다"
    if busy():
        return f"{busy()} 중입니다"
    if name == engine_name():
        stop_wiki()
    open(os.path.join(ROOT, "install.log"), "w").close()
    _cache.pop("eng_at", None)
    spawn("install", [sys.executable, os.path.join(SCRIPTS, "kit.py"), "install", name], "install.log")
    return f"{engines.NAMES[name]} 설치를 시작했습니다(몇 분 걸릴 수 있습니다)"


def tunnel(on):
    if not on:
        stop("tunnel")
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
    spawn("tunnel", [exe, "tunnel", "--no-autoupdate", "--url", local_url()], "tunnel.log")
    return "공개를 시작했습니다. 잠시 뒤 공개 주소가 표시됩니다"


def tunnel_url():
    if not alive("tunnel"):
        return ""
    for line in tail("tunnel.log", 200):
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            return m.group(0)
    return ""


def import_files():
    try:
        return sorted(f for f in os.listdir(IMPORT_DIR) if f.lower().endswith(IMPORT_EXT))
    except OSError:
        return []


def run_import(name):
    if busy() or alive("export"):
        return f"{busy() or '내보내기'} 중입니다"
    if name not in import_files():
        return "import 폴더에서 파일을 고르세요"
    e = eng()
    if not e.installed():
        return "먼저 엔진을 설치하세요"
    if not e.write_while_running and alive("engine"):
        return f"먼저 위키를 끄세요({engines.NAMES[e.name]} 는 꺼져 있을 때만 가져옵니다)"
    open(os.path.join(ROOT, "import.log"), "w").close()
    _cache.pop("docs_at", None)
    spawn("import", [sys.executable, os.path.join(SCRIPTS, "transfer.py"), "import", ROOT,
                     os.path.join(IMPORT_DIR, name)], "import.log")
    return "가져오기를 시작했습니다"


def run_export(fmt):
    if fmt not in EXPORT_FORMATS:
        return "알 수 없는 형식입니다"
    if busy() or alive("export"):
        return f"{busy() or '내보내기'} 중입니다"
    if not eng().installed():
        return "아직 설치되지 않았습니다"
    os.makedirs(EXPORT_DIR, exist_ok=True)
    open(os.path.join(ROOT, "export.log"), "w").close()
    spawn("export", [sys.executable, os.path.join(SCRIPTS, "transfer.py"), "export", ROOT, fmt], "export.log")
    return "내보내기를 시작했습니다. 남은 시간은 진행 줄에 표시됩니다"


def tail(name, n=12):
    try:
        with open(os.path.join(ROOT, name), encoding="utf-8", errors="replace") as f:
            return f.readlines()[-n:]
    except OSError:
        return []


def engine_status():
    """엔진별 설치 여부·판(1분 동안 기억)."""
    if time.time() - _cache.get("eng_at", 0) < 60 and not busy():
        return _cache["eng"]
    out = {}
    for n in engines.ENGINES:
        e = eng(n)
        inst = e.installed()
        info = {}
        if inst:
            try:
                info = e.info()
            except Exception:
                info = {}
        out[n] = {"name": engines.NAMES[n], "desc": ENGINE_DESC.get(n, ""), "installed": inst,
                  "version": info.get("version", "")}
    _cache["eng"], _cache["eng_at"] = out, time.time()
    return out


def status():
    s = settings()
    name = engine_name()
    e = eng(name)
    installed = e.installed()
    run = {n: alive(n) for n in ("engine", "proxy", "install", "tunnel", "export", "import")}
    ready = run["engine"] and e.ready()
    starting = run["engine"] and not ready
    st = {"engine": name, "engine_name": engines.NAMES[name], "installed": installed, "listen": s["listen"],
          "color": s.get("color", "#3b5bdb"), "running": run, "ready": ready, "kit": KIT_VERSION,
          "engines": engine_status()}
    # 문서 수: 켜지는 중·작업 중에는 읽지 않고, 1분에 한 번만 센다. 마지막 수는 기억한다
    if installed and not starting and not busy() and time.time() - _cache.get("docs_at", 0) > 60:
        try:
            _cache["docs"], _cache["docs_at"] = e.count(), time.time()
            if s.get("docs") != _cache["docs"]:
                remember(docs=_cache["docs"])
        except Exception:
            pass
    st["docs"] = _cache.get("docs", s.get("docs"))
    st["admin"] = e.admin_password() if installed and hasattr(e, "admin_password") else ""
    st["disk_free_gb"] = round(shutil.disk_usage(ROOT).free / 1e9, 1)
    st["install_log"] = tail("install.log", 10)
    st["update"] = dict(_cache.get("update") or {}, on=s.get("update_notice", True))
    st["export_log"] = tail("export.log", 6)
    st["export_dir"] = EXPORT_DIR
    st["import_files"], st["import_dir"] = import_files(), IMPORT_DIR
    st["import_log"] = tail("import.log", 6)
    st["public_url"] = tunnel_url()
    st["busy"] = busy()
    return st


PAGE = r"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>애니위키 관리판</title><style>
body{font-family:system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#222}
h1{font-size:22px}details.sec{border:1px solid #ddd;border-radius:8px;padding:12px 16px;margin:10px 0}details.sec>summary{cursor:pointer;list-style:none;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}details.sec>summary::-webkit-details-marker{display:none}details.sec>summary::before{content:'▸';color:#888;width:1em}details.sec[open]>summary::before{content:'▾'}details.sec>summary h2{margin:0}details.sec[open]>summary{margin-bottom:10px}.sum{font-size:13px;color:#666}.sum .on{color:#0a0}
h2{font-size:16px;margin:0 0 8px}button{font-size:14px;padding:6px 12px;margin:2px;cursor:pointer}
.on{color:#0a0}.off{color:#999}pre{background:#f6f6f6;padding:8px;font-size:12px;white-space:pre-wrap;max-height:220px;overflow:auto}
label{margin-right:12px}.eng{border:1px solid #e3e3e3;border-radius:6px;padding:8px 10px;margin:6px 0}
.pl{display:flex;gap:8px;align-items:baseline;padding:3px 0;border-bottom:1px solid #f0f0f0;font-size:14px}.pl .d{font-size:12px;color:#666}
.eng.cur{border-color:#3b5bdb;background:#f5f7ff}.eng b{font-size:15px}.eng .d{font-size:13px;color:#555}.note{font-size:13px;color:#555}
code.pw{background:#fff4e0;padding:2px 6px;border-radius:4px}
</style><div id="upd" hidden style="background:#fff4e0;border:1px solid #f0c060;border-radius:8px;padding:10px 14px;margin:12px 0"></div>
<h1>애니위키 관리판</h1>
<details class="sec" id="sec-st" open><summary><h2>상태</h2><span class="sum" id="sum-st"></span></summary><div id="st">불러오는 중…</div></details>
<details class="sec" id="sec-wiki" open><summary><h2>위키</h2><span class="sum" id="sum-wiki"></span></summary>
<button onclick="act('start')">켜기</button><button onclick="act('stop')">끄기</button>
<button onclick="openWiki()">위키 열기</button></details>
<details class="sec" id="sec-engine"><summary><h2>설치</h2><span class="sum" id="sum-engine"></span></summary>
<div id="englist"></div>
<pre id="englog"></pre></details>
<details class="sec" id="sec-color"><summary><h2>위키 색</h2><span class="sum" id="sum-color"></span></summary>
<span id="swatch" style="display:inline-block;width:28px;height:28px;border-radius:6px;vertical-align:middle;border:1px solid #ccc"></span>
<select id="preset" onchange="if(this.value)setColor(this.value)">
<option value="">추천 색 고르기…</option>
<option value="#3b5bdb">인디고 블루 (기본)</option><option value="#1c3f94">딥 오션</option><option value="#1971c2">코발트</option>
<option value="#364fc7">로열 블루</option><option value="#5f3dc4">바이올렛</option><option value="#862e9c">자두</option>
<option value="#c2255c">라즈베리</option><option value="#c92a2a">레드</option><option value="#e8590c">오렌지</option>
<option value="#343a40">차콜</option><option value="#212529">블랙</option></select>
<input type="color" id="picker" onchange="setColor(this.value)" title="원하는 색 직접 고르기">
<p class="note">위키 맨 위 머리글 색입니다.</p></details>
<details class="sec" id="sec-pub"><summary><h2>인터넷에 공개</h2><span class="sum" id="sum-pub"></span></summary>
<button onclick="pub()">공개하기</button><button onclick="act2('tunnel?on=0')">공개 끄기</button>
<div id="pubinfo" style="margin:6px 0;font-weight:bold"></div>
<p class="note">공유기 설정 없이 Cloudflare 임시 공개 주소(https)를 만듭니다. 켤 때마다 주소가 바뀝니다. [공개 끄기]를 누르기 전까지는 위키를 켤 때마다 다시 공개됩니다.<br>
<b>공개 전에</b>: 관리자 계정으로 로그인해 편집 권한을 확인하세요.
공개하는 순간 그 사이트의 운영 책임(권리 침해·게시중단 요청 대응 등)은 공개한 사람에게 있습니다.</p></details>
<details class="sec" id="sec-export"><summary><h2>내보내기</h2><span class="sum" id="sum-export"></span></summary>
<button onclick="exp('opennamu')">openNAMU (.db)</button><button onclick="exp('mediawiki')">MediaWiki (.xml.gz)</button>
<button onclick="exp('dokuwiki')">DokuWiki (.zip)</button><button onclick="exp('markdown')">Markdown (.zip)</button>
<div id="eprog" style="margin:6px 0;font-weight:bold"></div>
<p class="note">위키의 모든 문서를 고른 형식으로 통역해 <code id="expdir"></code> 폴더에 저장합니다.<br>
openNAMU: data.db 와 같은 형식(문서 표만) · MediaWiki: <code>php maintenance/run.php importDump</code> 로 가져옴 ·
DokuWiki: DokuWiki 폴더에 풀고 <code>php bin/indexer.php</code> · Markdown: 문서마다 .md 파일 하나.<br>
이미지 파일은 옮기지 않습니다.</p>
<pre id="elog"></pre></details>
<details class="sec" id="sec-import"><summary><h2>가져오기</h2><span class="sum" id="sum-import"></span></summary>
<select id="ifile"></select> <button onclick="imp()">가져오기</button>
<div id="iprog" style="margin:6px 0;font-weight:bold"></div>
<p class="note">openNAMU 형식(.db) 파일(이 키트나 유어위키가 내보낸 것, 또는 다른 openNAMU 의 data.db)을 <code id="impdir"></code> 폴더에 넣고 고르세요.
문서마다 내 쪽보다 새 판만 역사 뒤에 이어 붙이고, 같거나 더 새로우면 건너뜁니다.
파일 내용은 검증하지 않으니 믿을 수 있는 파일만 넣으세요. 위키를 끈 상태에서만 가져옵니다.</p>
<pre id="implog"></pre></details>
<details class="sec" id="sec-update"><summary><h2>새 판 알림</h2><span class="sum" id="sum-update"></span></summary>
<label><input type="checkbox" id="updon" onchange="api('/api/update_notice?on='+(this.checked?1:0)).then(load)"> GitHub 에 새 판이 나오면 알려 주기</label>
<button onclick="api('/api/update_check').then(load)">지금 확인</button>
<div id="updst" class="note" style="margin-top:6px"></div>
<p style="font-size:12px;color:#777">12시간에 한 번 GitHub(iamtalker/anywiki-kit)의 최신 릴리스만 확인합니다. 보내는 정보는 없고, 스스로 설치하지 않습니다.
새 판은 직접 받아 이 폴더에 덮어쓰세요(<code>wikis</code> 폴더는 그대로 두면 됩니다).</p></details>
<script>
let listen="127.0.0.1:4000";
async function api(p){const r=await fetch(p,{method:'POST'});return (await r.json()).msg}
async function act(a){alert(await api('/api/'+a));load()}
async function act2(p){alert(await api('/api/'+p));load()}
async function pub(){if(confirm('위키를 인터넷에 공개할까요? 누구나 주소로 접속할 수 있게 됩니다.')){act2('tunnel?on=1')}}
async function setColor(c){await api('/api/color?c='+encodeURIComponent(c));load()}
async function install(n,name){if(confirm(name+' 을(를) 설치할까요?')){alert(await api('/api/install?engine='+n));load()}}
async function exp(t){if(confirm(t+' 형식으로 내보낼까요?')){alert(await api('/api/export?to='+t));load()}}
async function imp(){var f=document.getElementById('ifile').value;if(!f){alert('import 폴더에 파일을 넣은 뒤 고르세요');return}
if(confirm(f+' 을(를) 가져올까요?')){alert(await api('/api/import?file='+encodeURIComponent(f)));load()}}
function openWiki(){window.open('http://'+listen.replace('0.0.0.0','127.0.0.1')+'/','_blank')}
function esc(t){return String(t==null?'':t).replace(/[&<>"']/g,function(c){return '&#'+c.charCodeAt(0)+';'})}
function dot(b){return b?'<span class=on>●</span>':'<span class=off>○</span>'}
function sum(k,h){var e=document.getElementById('sum-'+k);if(e&&e.innerHTML!==h)e.innerHTML=h}
function lastLine(log,pre){return log.filter(l=>pre.some(p=>l.startsWith(p))).pop()||''}
function num(n){return n==null?'?':Number(n).toLocaleString()}
async function load(){const s=await (await fetch('/api/status')).json();listen=s.listen;
var en=s.engines[s.engine]||{};
document.getElementById('st').innerHTML='엔진: <b>'+esc(s.engine_name)+'</b>'+(en.version?' '+esc(en.version):'')+' · '+
(s.installed?'문서 '+num(s.docs)+'개':'아직 설치되지 않음 — 아래 \'설치\' 칸에서 [설치]')+' · 디스크 여유 '+s.disk_free_gb+'GB'+
'<br><span class="note">애니위키 키트 '+esc(s.kit)+'</span><br>'+dot(s.running.engine)+' 위키 엔진 '+dot(s.running.proxy)+' 중계 서버 '+
(s.busy?'· <b>'+esc(s.busy)+' 중</b>':'')+
(s.running.engine?(s.ready?'<br><b class=on>위키 준비됨 — [위키 열기]를 누르세요</b>':'<br><b>위키 엔진 시작 중…</b>'):'')+
(s.admin?'<br><span class="note">관리자 계정: <code class="pw">'+esc(s.admin.replace(/\n/g,' · '))+'</code></span>':
 (s.engine==='opennamu'&&s.installed?'<br><span class="note">openNAMU 는 위키에서 처음 가입한 사람이 관리자가 됩니다</span>':''));
sum('st',esc(s.engine_name)+(s.installed?' · 문서 '+num(s.docs)+'개':''));
sum('wiki',s.running.engine?(s.ready?'<span class=on>켜짐</span>':'켜는 중'):'꺼짐');
var h='';for(const n in s.engines){var x=s.engines[n],cur=n===s.engine;
h+='<div class="eng'+(cur?' cur':'')+'"><b>'+esc(x.name)+'</b> '+(cur?'<span class=on>· 지금 엔진</span> ':'')+
(x.installed?'<span class=note>· 설치됨'+(x.version?' '+esc(x.version):'')+'</span>':'<span class=note>· 설치 안 됨</span>')+
'<div class="d">'+esc(x.desc)+'</div>'+
(!x.installed?'<button onclick="install(\''+n+'\',\''+esc(x.name)+'\')">설치</button>':'')+
'</div>'}
var eb=document.getElementById('englist');if(eb.dataset.h!==h){eb.dataset.h=h;eb.innerHTML=h}
document.getElementById('englog').textContent=s.install_log.join('');
sum('engine',s.running.install?'<b>설치 중</b>':(s.installed?'설치됨':'설치 안 됨'));
sum('color','<span style="display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:middle;background:'+esc(s.color)+'"></span> '+esc(s.color));
sum('pub',s.public_url?'<span class=on>공개 중</span> '+esc(s.public_url):(s.running.tunnel?'주소 만드는 중…':'꺼짐'));
var pl=lastLine(s.export_log,['진행','완료']);
sum('export',s.running.export?'내보내는 중 · '+esc(pl):(pl.startsWith('완료')?'마지막: '+esc(pl.split('→')[0]):''));
document.getElementById('elog').textContent=s.export_log.join('');
document.getElementById('eprog').textContent=s.running.export?('내보내는 중 · '+(pl||'준비 중…')):(pl.startsWith('완료')?pl:'');
document.getElementById('expdir').textContent=s.export_dir;
var fs=document.getElementById('ifile'),fk=s.import_files.join('\n');if(fs.dataset.k!==fk){var keep=fs.value;fs.dataset.k=fk;
fs.innerHTML=s.import_files.length?s.import_files.map(f=>'<option>'+esc(f)+'</option>').join(''):'<option value="">(import 폴더가 비어 있음)</option>';if(keep)fs.value=keep}
document.getElementById('impdir').textContent=s.import_dir;document.getElementById('implog').textContent=s.import_log.join('');
var il=lastLine(s.import_log,['진행','가져온','완료']);
document.getElementById('iprog').textContent=s.running.import?('가져오는 중 · '+(il||'준비 중…')):il;
sum('import',s.running.import?'<b>가져오는 중</b>':(s.import_files.length?'파일 '+s.import_files.length+'개':''));
var u=s.update||{},ub=document.getElementById('upd');document.getElementById('updon').checked=u.on!==false;
ub.hidden=!(u.on!==false&&u.newer);
if(u.newer&&ub.dataset.v!==u.latest){ub.dataset.v=u.latest;ub.innerHTML='<b>새 판이 나왔습니다: '+esc(u.name||u.latest)+'</b> ('+esc(u.published||'')+') · 지금 '+esc(u.current)+
' · <a href="'+esc(u.url)+'" target=_blank>릴리스 보기</a>'+(u.notes?'<details style="margin-top:6px"><summary>달라진 점</summary><pre>'+esc(u.notes)+'</pre></details>':'')}
document.getElementById('updst').textContent=u.on===false?'알림 꺼짐':(u.latest?(u.newer?'새 판 '+u.latest+' 이 있습니다':'최신 판입니다 ('+u.current+', GitHub 최신 '+u.latest+')')+
(u.checked_at?' · 확인 '+new Date(u.checked_at*1000).toLocaleString():''):(u.error?'확인하지 못했습니다: '+u.error:'확인 전'));
sum('update',u.on===false?'꺼짐':(u.newer?'<b>새 판 '+esc(u.latest)+'</b>':(u.latest?'최신 판':'')));
document.getElementById('swatch').style.background=s.color;document.getElementById('picker').value=s.color;
document.getElementById('pubinfo').innerHTML=s.public_url?('공개 주소: <a href="'+esc(s.public_url)+'" target=_blank>'+esc(s.public_url)+'</a>'):(s.running.tunnel?'공개 주소를 만드는 중…':'')}
document.querySelectorAll('details.sec').forEach(function(d){
  try{var v=localStorage.getItem('kit-'+d.id);if(v!==null)d.open=v==='1'}catch(e){}
  d.addEventListener('toggle',function(){try{localStorage.setItem('kit-'+d.id,d.open?'1':'0')}catch(e){}})});
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
        # 다른 사이트가 브라우저를 시켜 관리판을 누르지 못하게: 관리판 자신의 화면에서 온 요청만 받는다
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{PANEL_PORT}", f"http://localhost:{PANEL_PORT}"):
            return self.send(403, "{}", "application/json")
        q = parse_qs(u.query)
        arg = lambda k, d="": (q.get(k) or [d])[0]  # noqa: E731
        if u.path == "/api/start":
            remember(wiki_on=True)
            msg = start_wiki()
        elif u.path == "/api/stop":
            remember(wiki_on=False)
            msg = stop_wiki()
        elif u.path == "/api/color":
            c = arg("c")
            if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
                remember(color=c)
                msg = "색을 바꿨습니다. 위키 페이지를 새로고침하세요"
            else:
                msg = "색 형식이 올바르지 않습니다"
        elif u.path == "/api/tunnel":
            on = arg("on", "1") == "1"
            msg = tunnel(on)
            if not on or "시작" in msg or "이미" in msg:
                remember(public=on)
        elif u.path == "/api/install":
            msg = run_install(arg("engine", engine_name()))
        elif u.path == "/api/update_check":
            import update_check
            _cache["update"] = update_check.check(force=True)
            msg = update_check.message(_cache["update"])
        elif u.path == "/api/update_notice":
            remember(update_notice=arg("on", "1") == "1")
            msg = "새 판 알림을 " + ("켰습니다" if settings()["update_notice"] else "껐습니다")
        elif u.path == "/api/export":
            msg = run_export(arg("to"))
        elif u.path == "/api/import":
            msg = run_import(arg("file"))
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
          "$_.Name -in @('main.amd64.exe','python.exe','pythonw.exe','cloudflared.exe') } | "
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
    kit.migrate(ROOT)
    os.makedirs(IMPORT_DIR, exist_ok=True)  # 가져올 파일을 넣는 곳
    threading.Thread(target=update_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PANEL_PORT), Handler)
    url = f"http://127.0.0.1:{PANEL_PORT}/"
    print(f"애니위키 관리판: {url}", flush=True)
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    # 지난번에 위키를 켜 둔 채로 끝냈으면 다시 켠다(끄기를 누른 경우만 꺼진 채로 둔다)
    s = settings()
    if s.get("wiki_on") and eng().installed():
        print("지난번 설정대로 위키를 다시 켭니다" + (" (공개 포함, 주소는 새로 바뀝니다)" if s.get("public") else ""),
              flush=True)
        start_wiki(open_browser=False)
    if not WIN:  # 리눅스: kill 로 관리판을 끄면 위키 프로그램도 함께 끈다(따로 띄운 프로세스 묶음이라 저절로는 안 꺼짐)
        def on_term(*_):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, on_term)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_wiki()


if __name__ == "__main__":
    main()
