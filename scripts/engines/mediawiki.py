"""MediaWiki 엔진(PHP, SQLite).

설치: Docker Hub 공식 이미지(mediawiki)의 프로그램 층(동봉 확장 기능 포함)을 해시로 고정해 받아 wikis/mediawiki/w 에 풀고,
공식 설치 스크립트(maintenance install)로 SQLite 위키를 만든다(DB 서버 불필요). 관리자 계정 admin, 비밀번호는 설치 때 만든다.
기본 권한: 누구나 읽기, 로그인한 사람만 편집. 공개 주소가 바뀌어도 되도록 $wgServer 는 요청 주소에서 정한다.

문서 읽기: SQLite 를 직접 읽는다(빠름). 쓰기: 여러 개는 공식 importDump(XML), 하나는 공식 edit 스크립트.
"""
import calendar
import html
import os
import re
import secrets
import sqlite3
import subprocess
import tempfile
import time
import zlib

from .base import Engine, Page
from . import php as phpmod

NS = {0: "", 10: "틀:", 14: "분류:"}
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # XML 에 넣을 수 없는 글자
EXTENSIONS = ["Cite", "ParserFunctions", "SyntaxHighlight_GeSHi", "CategoryTree", "WikiEditor", "InputBox", "Poem"]


def utc_to_local(ts):
    if not ts or len(ts) < 14:
        return ""
    t = calendar.timegm(time.strptime(ts[:14], "%Y%m%d%H%M%S"))
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


def local_to_utc(s):
    t = time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S"))
    return time.strftime("%Y%m%d%H%M%S", time.gmtime(t))


class MediaWiki(Engine):
    name = "mediawiki"
    syntax = "mediawiki"

    @property
    def app(self):
        return os.path.join(self.dir, "w")

    @property
    def data(self):
        return os.path.join(self.dir, "data")

    @property
    def db_path(self):
        return os.path.join(self.data, "anywiki.sqlite")

    def installed(self):
        return os.path.exists(os.path.join(self.app, "LocalSettings.php")) and os.path.exists(self.db_path)

    def php(self):
        return phpmod.php_path(self.root)

    def maint(self, *args, stdin=None, timeout=3600):
        """공식 유지보수 스크립트 실행(maintenance/run.php)."""
        r = subprocess.run([self.php(), os.path.join(self.app, "maintenance", "run.php"), *args], cwd=self.app,
                           input=stdin, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            raise RuntimeError(f"MediaWiki {args[0]} 실패: {err[:700]}{' … ' + err[-200:] if len(err) > 900 else ''}")
        return r.stdout

    def install(self, log=print):
        import fetch
        src = fetch.sources(self.root)["engines"]["mediawiki"]
        phpmod.ensure(self.root, "mediawiki", log)
        if not os.path.exists(os.path.join(self.app, "index.php")):
            log(f"MediaWiki {src['version']} 받기(약 {src['size'] // (1 << 20)}MB)")
            fetch.docker_layer(src["repo"], src["digest"], os.path.join(self.root, "tools"), self.app, src["subdir"], log)
        os.makedirs(self.data, exist_ok=True)
        if not os.path.exists(os.path.join(self.app, "LocalSettings.php")):
            pw = secrets.token_urlsafe(12)
            log("MediaWiki 위키 만들기(공식 설치 스크립트)")
            self.maint("install", "--dbtype=sqlite", f"--dbpath={self.data}", "--dbname=anywiki",
                       "--server=http://127.0.0.1:3000", "--scriptpath=", "--lang=ko", f"--pass={pw}",
                       f"--confpath={self.app}", "애니위키", "admin", timeout=1800)
            with open(os.path.join(self.app, "LocalSettings.php"), "a", encoding="utf-8") as f:
                f.write("\n# ---- 애니위키 키트 설정\n"
                        "$wgServer = WebRequest::detectServer();  # 임시 공개 주소가 바뀌어도 되게\n"
                        "$wgGroupPermissions['*']['edit'] = false;\n"
                        "$wgGroupPermissions['*']['createaccount'] = false;\n"
                        "$wgEnableUploads = false;\n$wgUseInstantCommons = false;\n"
                        "require_once __DIR__ . '/AnywikiExtensions.php';\n")
            self.write_extensions(EXTENSIONS)
            with open(os.path.join(self.dir, "관리자 비밀번호.txt"), "w", encoding="utf-8") as f:
                f.write(f"아이디: admin\n비밀번호: {pw}\n")
            log(f"관리자 계정: admin / {pw}  (wikis/mediawiki/관리자 비밀번호.txt 에도 적어 둠)")
            self.maint("update", "--quick", timeout=1800)

    # ---- 확장 기능(플러그인)
    def ext_file(self):
        return os.path.join(self.app, "AnywikiExtensions.php")

    def enabled_extensions(self):
        try:
            return re.findall(r"wfLoadExtension\(\s*'([^']+)'", open(self.ext_file(), encoding="utf-8").read())
        except OSError:
            return []

    def write_extensions(self, names):
        names = [n for n in dict.fromkeys(names)
                 if os.path.exists(os.path.join(self.app, "extensions", n, "extension.json"))]
        with open(self.ext_file(), "w", encoding="utf-8") as f:
            f.write("<?php\n# 애니위키 관리판이 관리하는 확장 기능 목록(직접 고쳐도 됩니다)\n" +
                    "".join(f"wfLoadExtension( '{n}' );\n" for n in names))
        return names

    def command(self):
        return phpmod.server_command(self.php(), self.app, self.port)

    def admin_password(self):
        try:
            return open(os.path.join(self.dir, "관리자 비밀번호.txt"), encoding="utf-8").read().strip()
        except OSError:
            return ""

    # ---- 문서 읽기(SQLite 직접)
    def _db(self):
        return sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=30)

    @staticmethod
    def _title(ns, t):
        return NS[ns] + t.replace("_", " ")

    def _text(self, db, rev_id):
        r = db.execute("select c.content_address from slots s join content c on c.content_id = s.slot_content_id "
                       "where s.slot_revision_id = ? order by s.slot_role_id limit 1", (rev_id,)).fetchone()
        if not r or not r[0].startswith("tt:"):
            return ""
        t = db.execute("select old_text, old_flags from text where old_id = ?", (int(r[0][3:]),)).fetchone()
        if not t:
            return ""
        data, flags = t[0], (t[1] or "")
        if isinstance(data, str):
            data = data.encode("utf-8", "surrogateescape")
        if "gzip" in flags:
            data = zlib.decompress(data, -15)
        return data.decode("utf-8", "replace")

    def _rows(self, db, where="", args=()):
        return db.execute("select p.page_namespace, p.page_title, r.rev_id, r.rev_timestamp, a.actor_name "
                          "from page p join revision r on r.rev_id = p.page_latest "
                          "left join actor a on a.actor_id = r.rev_actor "
                          f"where p.page_namespace in (0, 10, 14) {where} order by p.page_namespace, p.page_title",
                          args).fetchall()

    def titles(self):
        db = self._db()
        try:
            return [self._title(ns, t) for ns, t, *_ in self._rows(db)]
        finally:
            db.close()

    def pages(self):
        db = self._db()
        try:
            for ns, t, rev, ts, actor in self._rows(db):
                yield Page(self._title(ns, t), self._text(db, rev), utc_to_local(ts), actor or "")
        finally:
            db.close()

    def get(self, title):
        ns, t = 0, title
        for k, p in NS.items():
            if p and title.startswith(p):
                ns, t = k, title[len(p):]
        t = t.replace(" ", "_")
        t = t[:1].upper() + t[1:] if t[:1].isascii() else t
        db = self._db()
        try:
            rows = self._rows(db, "and p.page_namespace = ? and p.page_title = ?", (ns, t))
            if not rows:
                return None
            ns, t, rev, ts, actor = rows[0]
            return Page(title, self._text(db, rev), utc_to_local(ts), actor or "")
        finally:
            db.close()

    def changes_since(self, ts):
        db = self._db()
        try:
            rows = self._rows(db, "and r.rev_timestamp > ?", (local_to_utc(ts),))
            return [Page(self._title(ns, t), self._text(db, rev), utc_to_local(tsx), actor or "")
                    for ns, t, rev, tsx, actor in rows]
        finally:
            db.close()

    # ---- 쓰기
    def put(self, page):
        from wikiconv.mediawiki import mw_title
        cur = self.get(page.title)
        if cur and cur.text == page.text:
            return False
        summary = page.summary or ""
        if page.author:
            summary = (summary + f" (작성: {page.author})").strip()
        self.maint("edit", "--user", "admin", "--summary", summary or "애니위키 키트", mw_title(page.title),
                   stdin=page.text, timeout=300)
        return True

    def put_many(self, pages, log=None):
        """여러 문서를 MediaWiki XML 로 묶어 공식 importDump 로 넣는다."""
        from wikiconv.mediawiki import mw_title
        fd, path = tempfile.mkstemp(suffix=".xml", dir=self.data)
        n = 0
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write('<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/" version="0.11" xml:lang="ko">\n')
            for p in pages:
                ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(
                    time.mktime(time.strptime(p.modified, "%Y-%m-%d %H:%M:%S")) if p.modified else time.time()))
                f.write(f"<page><title>{html.escape(mw_title(p.title))}</title><revision><timestamp>{ts}</timestamp>"
                        f"<contributor><username>{html.escape(p.author or '애니위키 키트')}</username></contributor>"
                        f"<comment>{html.escape(p.summary or '')}</comment><model>wikitext</model><format>text/x-wiki</format>"
                        f'<text xml:space="preserve">{html.escape(CTRL.sub("", p.text), quote=False)}</text></revision></page>\n')
                n += 1
            f.write("</mediawiki>\n")
        try:
            if log:
                log(f"  MediaWiki 로 문서 {n:,}개 넣는 중(공식 importDump)…")
            self.maint("importDump", "--no-local-users", "--username-prefix=", path, timeout=86400)
            self.maint("rebuildrecentchanges", timeout=3600)
            self.maint("initSiteStats", "--update", timeout=3600)
        finally:
            os.remove(path)
        return n

    def info(self):
        try:
            m = re.search(r"MW_VERSION', '([^']+)'", open(os.path.join(self.app, "includes", "Defines.php"),
                                                          encoding="utf-8").read())
            return {"version": m.group(1) if m else "?"}
        except OSError:
            return {}
