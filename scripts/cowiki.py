"""공동위키: 서로의 ID 를 등록한 위키끼리 편집을 주고받는다 (표준 라이브러리만 사용).

- ID: 처음 켤 때 서명 열쇠(Ed25519)를 만들고 공개 열쇠(64자 16진수)가 곧 ID 다(wikis/_cowiki/key.json). 엔진을 바꿔도 ID 는 그대로.
- 서로 등록: A 가 B 를, B 가 A 를 회원으로 적어야 이어진다. 창구는 요청한 ID 가 내 회원이 아니면 거절하고(not_member),
  나도 내 회원에게만 묻는다. 요청과 응답 모두 서명한다(주소를 가로챈 다른 서버가 끼어들 수 없음).
- 무엇을 주나: 내 위키에서 '내가(내 위키 사용자가)' 고친 문서만. 남에게서 받은 판은 다시 퍼뜨리지 않는다.
  그래서 세 위키가 모두 편집을 나누려면 서로서로 등록해야 한다.
- 공용 언어: 문서는 AWM(확장 마크다운)으로 주고받고, 받는 쪽이 자기 엔진 문법으로 통역한다. 엔진이 달라도 된다.
- 충돌: 마지막에 쓴 판이 이긴다(시각은 UTC). 10분 넘게 미래인 판은 받지 않는다. 지우기는 옮기지 않는다.
- 주소: 창구(127.0.0.1:3002)는 공동위키 전용 임시 공개 주소(cloudflared)로 열거나 고정 주소를 쓴다.
  'ID → 지금 창구 주소'는 BitTorrent DHT(dht.py)에 서명해 올려, 주소가 바뀌어도 회원이 찾아온다. 회원의 주소를 직접 적어도 된다.

    python cowiki.py <root> run [--listen 127.0.0.1:3002] [--tunnel-log 파일 | --self-url URL] [--bootstrap 호스트:포트]
    python cowiki.py <root> id | name 이름 | add ID [이름] [주소] | remove ID | list | sync
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ed25519  # noqa: E402

UA = "Anywiki-cowiki/1 (+https://github.com/iamtalker/anywiki-kit)"
MAGIC = b"anywiki-cowiki-v1\n"
SYNC_EVERY = 60          # 회원에게 묻는 주기(초)
SCAN_EVERY = 30          # 내 위키의 바뀐 문서를 살피는 주기(초)
DHT_EVERY = 1800         # DHT 에 내 주소를 다시 올리는 주기(초)
RESOLVE_EVERY = 1800     # 회원 주소를 DHT 에서 다시 찾는 주기(초)
PAGE = 200               # 한 번에 주는 문서 수
MAX_BODY = 32 << 20
MAX_TEXT = 4 << 20
SKEW = 300               # 요청 시각 허용 오차(초)
FUTURE = 600             # 이만큼 넘게 미래인 판은 받지 않음(초)
ID_RE = re.compile(r"[0-9a-f]{64}")


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def canonical(obj):
    return MAGIC + json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def local_to_epoch(s):
    try:
        return int(time.mktime(time.strptime(s[:19], "%Y-%m-%d %H:%M:%S")))
    except (ValueError, TypeError):
        return int(time.time())


def epoch_to_local(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


# ================================================================ 저장소
class State:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.dir = os.path.join(self.root, "wikis", "_cowiki")  # 엔진 데이터와 함께 백업·Docker 볼륨에 남게
        os.makedirs(self.dir, exist_ok=True)
        self.secret, self.id = self._key()
        self.path = os.path.join(self.dir, "cowiki.db")
        db = self.db()
        db.executescript("""
            create table if not exists members (id text primary key, name text default '', url text default '',
                added real, cursor int default 0, last_ok real default 0, last_try real default 0, status text default '',
                resolved_url text default '', resolved_at real default 0, got int default 0);
            create table if not exists journal (seq integer primary key autoincrement, title text, awm text,
                modified int, author text, sha text);
            create index if not exists journal_title on journal(title);
            create table if not exists applied (title text primary key, sha text);
            create table if not exists meta (k text primary key, v text);
        """)
        db.commit()
        db.close()

    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("pragma journal_mode=wal")
        return db

    def _key(self):
        path = os.path.join(self.dir, "key.json")
        for _ in range(20):
            try:
                secret = bytes.fromhex(json.load(open(path, encoding="utf-8"))["secret"])
                return secret, ed25519.public_key(secret).hex()
            except FileNotFoundError:
                secret = ed25519.new_secret()
                try:
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    continue
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({"secret": secret.hex(), "주의": "공동위키 ID 의 비밀 열쇠입니다. 남에게 주지 마세요."}, f,
                              ensure_ascii=False)
                return secret, ed25519.public_key(secret).hex()
            except (OSError, ValueError, KeyError):
                time.sleep(0.1)
        raise RuntimeError(f"공동위키 열쇠 파일을 읽지 못했습니다: {path}")

    def meta(self, k, default=""):
        db = self.db()
        try:
            r = db.execute("select v from meta where k = ?", (k,)).fetchone()
            return r[0] if r else default
        finally:
            db.close()

    def set_meta(self, k, v):
        db = self.db()
        db.execute("insert or replace into meta values (?, ?)", (k, str(v)))
        db.commit()
        db.close()

    def name(self):
        return self.meta("name") or "애니위키"

    def members(self):
        db = self.db()
        db.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in db.execute("select * from members order by added")]
        finally:
            db.close()

    def member_ids(self):
        return {m["id"] for m in self.members()}

    def add(self, mid, name="", url=""):
        mid = mid.strip().lower()
        if not ID_RE.fullmatch(mid):
            raise ValueError("ID 는 64자리 16진수입니다")
        if mid == self.id:
            raise ValueError("내 ID 입니다")
        if url and not re.match(r"https?://", url):
            raise ValueError("주소는 http:// 나 https:// 로 시작해야 합니다")
        db = self.db()
        db.execute("insert into members (id, name, url, added) values (?, ?, ?, ?) "
                   "on conflict(id) do update set name = excluded.name, url = excluded.url",
                   (mid, name.strip()[:60], url.strip().rstrip("/"), time.time()))
        db.commit()
        db.close()

    def remove(self, mid):
        db = self.db()
        db.execute("delete from members where id = ?", (mid,))
        db.commit()
        db.close()

    def update_member(self, mid, **kv):
        db = self.db()
        db.execute(f"update members set {', '.join(k + ' = ?' for k in kv)} where id = ?", (*kv.values(), mid))
        db.commit()
        db.close()


# ================================================================ 내 위키 살피기(내 편집을 기록)
def engine_of(root):
    import engines
    import transfer
    return engines.get(transfer.current_engine(root), root)


def to_awm(e, text, title, resolve=None):
    import transfer
    import wikiconv
    return wikiconv.render(transfer.to_doc(e.name, text, title, resolve), "awm", title)


_scan_lock = threading.Lock()


def scan(st, e=None, log=None):
    """내 위키에서 바뀐 문서를 AWM 으로 바꿔 기록한다. 남에게서 받아 넣은 판(applied)은 기록하지 않는다."""
    with _scan_lock:
        n = _scan(st, e or engine_of(st.root), log or (lambda m: globals()["log"](m)))
        st.last_scan = time.time()
        return n


def _scan(st, e, log):
    if not e.installed():
        return 0
    if st.meta("engine") != e.name:
        # 처음이면 지금 있는 문서를 모두 나누고, 엔진을 바꾼 뒤라면(모든 문서가 새 문법으로 바뀜) 지금부터만 살핀다
        first = not st.meta("engine")
        st.set_meta("engine", e.name)
        if not first:
            st.set_meta("scan_ts", time.strftime("%Y-%m-%d %H:%M:%S"))
            log(f"엔진이 {e.name} 로 바뀌어 지금부터의 편집만 나눕니다")
            return 0
    since = st.meta("scan_ts", "")
    pages = e.changes_since(since) if since else list(e.pages())
    if not pages:
        return 0
    resolve = e.resolver() if hasattr(e, "resolver") else None
    db = st.db()
    n = 0
    newest = since
    try:
        applied = dict(db.execute("select title, sha from applied"))
        for p in pages:
            newest = max(newest, p.modified or "")
            if applied.get(p.title) == sha(p.text):
                continue  # 남에게서 받아 넣은 그대로다
            try:
                awm = to_awm(e, p.text, p.title, resolve)
            except Exception as ex:  # 한 문서가 이상해도 멈추지 않는다
                log(f"  통역 실패로 건너뜀: {p.title} — {ex}")
                continue
            h = sha(awm)
            last = db.execute("select sha from journal where title = ? order by seq desc limit 1", (p.title,)).fetchone()
            if last and last[0] == h:
                continue
            db.execute("delete from journal where title = ?", (p.title,))  # 문서마다 마지막 판만 둔다
            db.execute("insert into journal (title, awm, modified, author, sha) values (?, ?, ?, ?, ?)",
                       (p.title, awm, local_to_epoch(p.modified), p.author or "", h))
            n += 1
        db.commit()
    finally:
        db.close()
    # 같은 초에 바뀐 문서를 놓치지 않게 조금 앞에서 다시 살핀다(같은 내용은 위에서 걸러짐)
    if newest:
        st.set_meta("scan_ts", epoch_to_local(local_to_epoch(newest) - 2))
    if n:
        log(f"내 편집 {n}개를 공동위키에 나눌 준비를 했습니다")
    return n


# ================================================================ 창구(서버)
def signed_headers(st, to_id, path_q):
    t = str(int(time.time()))
    sig = ed25519.sign(st.secret, canonical({"from": st.id, "to": to_id, "t": t, "path": path_q}))
    return {"X-Cowiki-Id": st.id, "X-Cowiki-Time": t, "X-Cowiki-Sig": sig.hex(), "User-Agent": UA}


def serve_changes(st, requester, since, limit=PAGE):
    if time.time() - getattr(st, "last_scan", 0) > SCAN_EVERY:  # 창구만 켜져 있어도 최근 편집을 준다
        try:
            scan(st)
        except Exception as ex:
            log(f"살피기 오류: {ex}")
    db = st.db()
    try:
        rows = db.execute("select seq, title, awm, modified, author from journal where seq > ? order by seq limit ?",
                          (since, limit + 1)).fetchall()
    finally:
        db.close()
    more = len(rows) > limit
    items = [{"seq": s, "title": t, "awm": a, "modified": m, "author": au} for s, t, a, m, au in rows[:limit]]
    body = {"from": st.id, "to": requester, "name": st.name(), "t": int(time.time()), "since": since,
            "items": items, "more": more}
    body["sig"] = ed25519.sign(st.secret, canonical(body)).hex()
    return body


def make_handler(st):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, code, obj):
            b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urllib.parse.urlsplit(self.path)
            if u.path == "/cowiki/hello":
                return self.reply(200, {"id": st.id, "name": st.name(), "v": 1})
            if u.path != "/cowiki/changes":
                return self.reply(404, {"error": "없음"})
            who = (self.headers.get("X-Cowiki-Id") or "").lower()
            t = self.headers.get("X-Cowiki-Time") or "0"
            try:
                sig = bytes.fromhex(self.headers.get("X-Cowiki-Sig") or "")
                ok_time = abs(time.time() - int(t)) <= SKEW
            except ValueError:
                return self.reply(400, {"error": "잘못된 요청"})
            if not ID_RE.fullmatch(who) or not ok_time:
                return self.reply(401, {"error": "시각이나 ID 가 맞지 않음(컴퓨터 시계를 확인하세요)"})
            path_q = u.path + ("?" + u.query if u.query else "")
            if not ed25519.verify(bytes.fromhex(who), canonical({"from": who, "to": st.id, "t": t, "path": path_q}), sig):
                return self.reply(401, {"error": "서명이 맞지 않음"})
            if who not in st.member_ids():
                return self.reply(403, {"error": "not_member", "name": st.name()})
            q = urllib.parse.parse_qs(u.query)
            try:
                since = int((q.get("since") or ["0"])[0])
            except ValueError:
                since = 0
            self.reply(200, serve_changes(st, who, since))
    return Handler


# ================================================================ 회원에게 묻기
class Worker:
    def __init__(self, st, tunnel_log="", self_url="", bootstrap=None):
        self.st, self.tunnel_log, self.self_url, self.bootstrap = st, tunnel_log, self_url.rstrip("/"), bootstrap
        self._dht = None
        self.published = ("", 0)

    def dht(self):
        import dht
        if self._dht is None:
            self._dht = dht.DHT(bootstrap=self.bootstrap)
        return self._dht

    def my_url(self):
        if self.self_url:
            return self.self_url
        try:
            with open(self.tunnel_log, encoding="utf-8", errors="replace") as f:
                found = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", f.read())
            return found[-1] if found else ""
        except OSError:
            return ""

    def publish(self):
        url = self.my_url()
        if not url or (url == self.published[0] and time.time() - self.published[1] < DHT_EVERY):
            return
        pub = bytes.fromhex(self.st.id)
        try:
            ok, seq = self.dht().put(self.st.secret, pub, {"u": url, "t": int(time.time())}, int(time.time()))
            if ok:
                self.published = (url, time.time())
                log(f"내 창구 주소를 DHT 에 올렸습니다({ok}곳): {url}")
            else:
                log("DHT 에 주소를 올리지 못했습니다(인터넷이 UDP 를 막았을 수 있음). 회원이 내 주소를 직접 적어야 합니다")
                self.published = ("", time.time() - DHT_EVERY + 300)  # 5분 뒤 다시
        except Exception as ex:
            log(f"DHT 오류: {ex}")
            self.published = ("", time.time() - DHT_EVERY + 300)
        self.st.set_meta("my_url", url)

    def resolve(self, m):
        if m["url"]:
            return m["url"]
        if m["resolved_url"] and time.time() - m["resolved_at"] < RESOLVE_EVERY:
            return m["resolved_url"]
        try:
            got = self.dht().get(bytes.fromhex(m["id"]))
        except Exception as ex:
            log(f"DHT 오류: {ex}")
            got = None
        url = ""
        if got:
            v = got[1]
            u = v.get(b"u") if isinstance(v, dict) else None
            if isinstance(u, bytes) and re.match(rb"https?://", u):
                url = u.decode("utf-8", "replace")
        self.st.update_member(m["id"], resolved_url=url, resolved_at=time.time())
        return url

    def fetch(self, m, url, since):
        path_q = f"/cowiki/changes?since={since}"
        req = urllib.request.Request(url + path_q, headers=signed_headers(self.st, m["id"], path_q))
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read(MAX_BODY + 1)
        except urllib.error.HTTPError as ex:
            try:
                err = json.loads(ex.read(4096).decode("utf-8"))
            except Exception:
                err = {}
            if ex.code == 403 and err.get("error") == "not_member":
                raise PermissionError(err.get("name", ""))
            raise RuntimeError(f"HTTP {ex.code} {err.get('error', '')}".strip())
        if len(data) > MAX_BODY:
            raise RuntimeError("응답이 너무 큼")
        body = json.loads(data.decode("utf-8"))
        sig = bytes.fromhex(body.pop("sig", "") or "00")
        if body.get("from") != m["id"] or body.get("to") != self.st.id or body.get("since") != since:
            raise RuntimeError("다른 위키의 응답입니다(주소가 바뀌었을 수 있음)")
        if not ed25519.verify(bytes.fromhex(m["id"]), canonical(body), sig):
            raise RuntimeError("응답 서명이 맞지 않습니다")
        return body

    def apply(self, m, items, e):
        """회원이 준 문서를 내 엔진 문법으로 통역해 넣는다. 내 쪽이 더 새로우면 건너뛴다."""
        import wikiconv
        from engines.base import Page
        now = time.time()
        who = m["name"] or m["id"][:8]
        todo = []
        for it in items:
            title, awm = it.get("title"), it.get("awm")
            if not isinstance(title, str) or not isinstance(awm, str) or not title.strip() or len(title) > 250 \
                    or re.search(r"[\x00-\x1f]", title) or len(awm) > MAX_TEXT:
                continue
            modified = int(it.get("modified") or 0)
            if modified > now + FUTURE:
                log(f"  미래 시각이라 받지 않음: {title}")
                continue
            cur = e.get(title)
            if cur and local_to_epoch(cur.modified) > modified:
                continue  # 내 쪽이 더 새롭다(마지막에 쓴 판이 이김)
            try:
                text = wikiconv.convert(awm, "awm", wikiconv_syntax(e), title)
            except Exception as ex:
                log(f"  통역 실패로 건너뜀: {title} — {ex}")
                continue
            if cur and cur.text == text:
                continue
            author = str(it.get("author") or "")[:60]
            todo.append(Page(title, text, epoch_to_local(modified),
                             f"{author}@{who}" if author else who, f"[공동위키 {who}]"))
        if not todo:
            return 0
        if len(todo) > 20 and hasattr(e, "put_many"):
            n = e.put_many(todo)
        else:
            n = sum(bool(e.put(p)) for p in todo)
        # 넣은 그대로를 기억해, 내 위키를 살필 때 '내 편집'으로 다시 퍼뜨리지 않는다
        db = self.st.db()
        for p in todo:
            got = e.get(p.title)
            if got:
                db.execute("insert or replace into applied values (?, ?)", (p.title, sha(got.text)))
        db.commit()
        db.close()
        return n

    def sync_member(self, m, e):
        url = self.resolve(m)
        self.st.update_member(m["id"], last_try=time.time())
        if not url:
            self.st.update_member(m["id"], status="no_url")
            return
        since, got = m["cursor"], 0
        try:
            for _ in range(1000):
                body = self.fetch(m, url, since)
                items = body.get("items") or []
                got += self.apply(m, items, e)
                if items:
                    since = max(int(it.get("seq") or 0) for it in items)
                    self.st.update_member(m["id"], cursor=since)
                if not body.get("more"):
                    break
            self.st.update_member(m["id"], status="ok", last_ok=time.time(), got=m["got"] + got)
            if got:
                log(f"{m['name'] or m['id'][:8]} 에게서 문서 {got}개를 받았습니다")
        except PermissionError:
            self.st.update_member(m["id"], status="not_member")
        except Exception as ex:
            if not m["url"]:
                self.st.update_member(m["id"], resolved_at=0)  # 주소가 바뀌었을 수 있어 다음에 다시 찾는다
            self.st.update_member(m["id"], status=f"error: {str(ex)[:150]}")

    def sync(self):
        e = engine_of(self.st.root)
        scan(self.st, e)
        for m in self.st.members():
            self.sync_member(m, e)

    def loop(self, stop):
        last_sync = 0
        while not stop.is_set():
            try:
                if self.tunnel_log or self.self_url:
                    self.publish()
                e = engine_of(self.st.root)
                scan(self.st, e)
                if time.time() - last_sync >= SYNC_EVERY or self.st.meta("sync_now"):
                    self.st.set_meta("sync_now", "")
                    for m in self.st.members():
                        self.sync_member(m, e)
                    last_sync = time.time()
            except Exception as ex:
                log(f"공동위키 오류: {ex}")
            stop.wait(SCAN_EVERY if not self.st.meta("sync_now") else 1)


def wikiconv_syntax(e):
    import transfer
    return transfer.SYNTAX[e.name]


# ================================================================ 명령줄
def status(root):
    st = State(root)
    return {"id": st.id, "name": st.name(), "my_url": st.meta("my_url"), "members": st.members(),
            "shared": _count(st, "journal"), "applied": _count(st, "applied")}


def _count(st, table):
    db = st.db()
    try:
        return db.execute(f"select count(*) from {table}").fetchone()[0]
    finally:
        db.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("action", choices=["run", "id", "name", "add", "remove", "list", "sync"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--listen", default="127.0.0.1:3002")
    ap.add_argument("--tunnel-log", default="")
    ap.add_argument("--self-url", default="")
    ap.add_argument("--bootstrap", action="append", default=None, help="DHT 시작 노드 호스트:포트(시험용)")
    a = ap.parse_args()
    st = State(a.root)
    if a.action == "id":
        print(st.id)
    elif a.action == "name":
        if a.args:
            st.set_meta("name", " ".join(a.args)[:60])
        print(st.name())
    elif a.action == "add":
        if not a.args:
            raise SystemExit("사용: add ID [이름] [주소]")
        try:
            st.add(a.args[0], a.args[1] if len(a.args) > 1 else "", a.args[2] if len(a.args) > 2 else "")
        except ValueError as ex:
            raise SystemExit(f"실패: {ex}")
        print("등록했습니다. 상대도 내 ID 를 등록해야 이어집니다. 내 ID:", st.id)
    elif a.action == "remove":
        st.remove((a.args or [""])[0].lower())
        print("지웠습니다")
    elif a.action == "list":
        s = status(a.root)
        print(f"내 ID: {s['id']}  이름: {s['name']}  창구 주소: {s['my_url'] or '(없음)'}")
        for m in s["members"]:
            print(f"- {m['name'] or '(이름 없음)'} {m['id']}  {m['status'] or '아직 안 물어봄'}"
                  f"{'  받은 문서 ' + str(m['got']) if m['got'] else ''}")
    elif a.action == "sync":
        bootstrap = [(h, int(p)) for h, p in (b.rsplit(":", 1) for b in a.bootstrap)] if a.bootstrap else None
        Worker(st, a.tunnel_log, a.self_url, bootstrap).sync()
    else:
        host, port = a.listen.rsplit(":", 1)
        bootstrap = [(h, int(p)) for h, p in (b.rsplit(":", 1) for b in a.bootstrap)] if a.bootstrap else None
        srv = ThreadingHTTPServer((host, int(port)), make_handler(st))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        log(f"공동위키 창구: http://{a.listen}  내 ID: {st.id}")
        stop = threading.Event()
        try:
            Worker(st, a.tunnel_log, a.self_url, bootstrap).loop(stop)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
