"""openNAMU 엔진(나무마크, SQLite data.db, Go 로 만든 실행 파일 하나)."""
import os
import platform
import re
import sqlite3
import subprocess
import time

from .base import Engine, Page, now, port_open

CAT_RE = re.compile(r"\[\[분류:([^\]|#]+)")


def to_db_title(t):
    return "category:" + t[3:] if t.startswith("분류:") else t


def from_db_title(t):
    return "분류:" + t[9:] if t.startswith("category:") else t


class OpenNamu(Engine):
    name = "opennamu"
    syntax = "namumark"
    write_while_running = False  # 켜진 채로 DB 를 크게 바꾸면 엔진이 꼬일 수 있다

    @property
    def exe(self):
        return os.path.join(self.dir, "main.amd64.exe" if os.name == "nt" else "main.bin")

    @property
    def db_path(self):
        return os.path.join(self.dir, "data.db")

    def installed(self):
        return os.path.exists(self.db_path) and os.path.exists(self.exe)

    def tool_key(self):
        if os.name == "nt":
            return "opennamu"
        return "opennamu-linux-arm64" if platform.machine().lower() in ("aarch64", "arm64") else "opennamu-linux-amd64"

    def install(self, log=print):
        import fetch
        t = fetch.sources(self.root)["tools"][self.tool_key()]
        log("위키 엔진(openNAMU) 받기")
        fetch.download(t["url"], self.exe, t["sha256"], log=log)
        if os.name != "nt":
            os.chmod(self.exe, 0o755)
        if not os.path.exists(self.db_path):
            log("빈 위키 만들기")
            p = subprocess.Popen([self.exe, str(self.port), "--localhost"], cwd=self.dir,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=0x08000000 if os.name == "nt" else 0)
            try:
                for _ in range(120):
                    if port_open(self.port) and os.path.exists(self.db_path):
                        break
                    time.sleep(1)
            finally:
                p.terminate()
                try:
                    p.wait(10)
                except subprocess.TimeoutExpired:
                    p.kill()
            if not os.path.exists(self.db_path):
                raise RuntimeError(f"openNAMU 가 DB 를 만들지 못했습니다({self.port}번 포트를 확인하세요)")

    def command(self):
        return [self.exe, str(self.port), "--localhost"], self.dir, None

    # ---- 문서
    def _db(self, ro=False):
        if ro:
            return sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=30)
        return sqlite3.connect(self.db_path, timeout=60)

    def titles(self):
        db = self._db(True)
        try:
            return [from_db_title(t) for (t,) in db.execute("select title from data order by title")]
        finally:
            db.close()

    def count(self):
        db = self._db(True)
        try:
            return db.execute("select count(*) from data").fetchone()[0]
        finally:
            db.close()

    def _modified(self, db, t):
        r = db.execute("select set_data from data_set where doc_name = ? and set_name = 'last_edit' and doc_rev = ''",
                       (t,)).fetchone()
        if r and r[0]:
            return r[0][:19]
        r = db.execute("select max(date) from history where title = ?", (t,)).fetchone()
        return (r[0] or "")[:19]

    def pages(self):
        db = self._db(True)
        try:
            for t, text in db.execute("select title, data from data order by title").fetchall():
                a = db.execute("select ip from history where title = ? order by id + 0 desc limit 1", (t,)).fetchone()
                yield Page(from_db_title(t), text or "", self._modified(db, t), a[0] if a else "")
        finally:
            db.close()

    def get(self, title):
        db = self._db(True)
        try:
            t = to_db_title(title)
            r = db.execute("select data from data where title = ?", (t,)).fetchone()
            if not r:
                return None
            a = db.execute("select ip from history where title = ? order by id + 0 desc limit 1", (t,)).fetchone()
            return Page(title, r[0] or "", self._modified(db, t), a[0] if a else "")
        finally:
            db.close()

    def put(self, page, db=None):
        own = db is None
        db = db or self._db()
        try:
            t = to_db_title(page.title)
            cur = db.execute("select data from data where title = ?", (t,)).fetchone()
            if cur and cur[0] == page.text:
                return False
            if cur:
                db.execute("update data set data = ? where title = ?", (page.text, t))
            else:
                db.execute("insert into data (title, data, type) values (?, ?, '')", (t, page.text))
            rev = (db.execute("select max(id + 0) from history where title = ?", (t,)).fetchone()[0] or 0) + 1
            when = page.modified or now()
            db.execute("insert into history (id, title, data, date, ip, send, leng, hide, type) "
                       "values (?, ?, ?, ?, ?, ?, ?, '', ?)",
                       (str(rev), t, page.text, when, page.author or "애니위키 키트", page.summary or "",
                        str(len(page.text)), "r1" if rev == 1 else ""))
            db.execute("delete from data_set where doc_name = ? and set_name in ('last_edit', 'length') and doc_rev = ''",
                       (t,))
            db.executemany("insert into data_set (doc_name, doc_rev, set_name, set_data) values (?, '', ?, ?)",
                           [(t, "last_edit", when), (t, "length", str(len(page.text)))])
            db.execute("delete from back where link = ? and type in ('cat', 'redirect')", (t,))
            m = re.match(r"\s*#redirect\s+(.+)", page.text, re.I)
            if m:
                db.execute("insert into back (link, title, type, data) values (?, ?, 'redirect', '')",
                           (t, to_db_title(m.group(1).split("\n")[0].strip())))
            else:
                db.executemany("insert into back (link, title, type, data) values (?, ?, 'cat', '')",
                               [(t, "category:" + c.strip()) for c in dict.fromkeys(CAT_RE.findall(page.text))])
            if own:
                db.commit()
            return True
        finally:
            if own:
                db.close()

    def put_many(self, pages, log=None):
        """여러 문서를 한 번에(빠르게). 넣은 수."""
        db = self._db()
        n = 0
        try:
            for i, p in enumerate(pages, 1):
                n += bool(self.put(p, db))
                if i % 2000 == 0:
                    db.commit()
                    if log:
                        log(f"  {i:,}개 넣음")
            total = db.execute("select count(*) from data").fetchone()[0]
            db.execute("delete from other where name = 'count_all_title'")
            db.execute("insert into other (name, data, coverage) values ('count_all_title', ?, '')", (str(total),))
            db.commit()
        finally:
            db.close()
        return n

    def changes_since(self, ts):
        db = self._db(True)
        try:
            titles = [t for (t,) in db.execute("select distinct title from history where date > ?", (ts,))]
        finally:
            db.close()
        return [p for p in (self.get(from_db_title(t)) for t in titles) if p]

    def info(self):
        import fetch
        m = re.search(r"/download/([^/]+)/", fetch.sources(self.root)["tools"][self.tool_key()]["url"])
        return {"version": m.group(1) if m else "?"}
