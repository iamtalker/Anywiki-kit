"""내장 마크다운 엔진(scripts/mdwiki.py). 설치할 것이 없다(파이썬만 있으면 됨)."""
import os
import secrets
import sys

from .base import Engine, Page

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


PLUGINS = {"katex": ("수식(KaTeX)", "수식을 그려 보여 줍니다(동봉 파일, 인터넷 불필요)."),
           "highlight": ("코드 색칠(highlight.js)", "코드 블록에 언어별 색을 입힙니다(동봉 파일).")}


class MarkdownEngine(Engine):
    name = "markdown"
    syntax = "markdown"
    plugin_note = "내장 엔진의 부가 기능입니다. 켜고 끄면 바로 적용됩니다(페이지 새로고침)."

    def store(self):
        sys.path.insert(0, SCRIPTS)
        import mdwiki
        return mdwiki.Store(self.dir)

    def installed(self):
        return os.path.exists(os.path.join(self.dir, "wiki.db"))

    def install(self, log=print):
        import mdwiki
        os.makedirs(self.dir, exist_ok=True)
        st = self.store()
        if not st.conf("admin_pw"):
            pw = secrets.token_urlsafe(9)
            mdwiki.set_password(st, pw)
            st.set_conf("edit", "admin")
            st.set_conf("plugins", '["katex", "highlight"]')
            with open(os.path.join(self.dir, "관리자 비밀번호.txt"), "w", encoding="utf-8") as f:
                f.write(f"비밀번호: {pw}\n(위키의 [로그인]에서 이 비밀번호만 넣으면 됩니다)\n")
            log(f"관리자 비밀번호: {pw}  (wikis/markdown/관리자 비밀번호.txt 에도 적어 둠)")

    def command(self):
        return [sys.executable, os.path.join(SCRIPTS, "mdwiki.py"), self.dir, "--port", str(self.port)], self.dir, \
            dict(os.environ, PYTHONUTF8="1")

    def titles(self):
        return self.store().titles()

    def count(self):
        return len(self.titles())

    def pages(self):
        st = self.store()
        for t in st.titles():
            got = st.get(t)
            if got:
                yield Page(t, got[0], got[1], got[2])

    def get(self, title):
        got = self.store().get(title)
        return Page(title, got[0], got[1], got[2]) if got else None

    def put(self, page):
        return self.store().put(page.title, page.text, page.author or "애니위키 키트", page.summary, page.modified or None)

    def put_many(self, pages, log=None):
        st = self.store()
        n = 0
        for i, p in enumerate(pages, 1):
            n += bool(st.put(p.title, p.text, p.author or "애니위키 키트", p.summary, p.modified or None))
            if log and i % 2000 == 0:
                log(f"  {i:,}개 넣음")
        return n

    def changes_since(self, ts):
        st = self.store()
        db = st.db()
        titles = [t for (t,) in db.execute("select distinct title from rev where date > ?", (ts,))]
        db.close()
        return [p for p in (self.get(t) for t in titles) if p]

    def _on(self):
        import json
        try:
            return json.loads(self.store().conf("plugins", "[]") or "[]")
        except ValueError:
            return []

    def plugins(self):
        on = self._on()
        return [{"id": k, "name": n, "desc": d, "on": k in on, "locked": False} for k, (n, d) in PLUGINS.items()]

    def set_plugin(self, pid, on, log=print):
        import json
        if pid not in PLUGINS:
            raise ValueError("알 수 없는 기능입니다")
        cur = [p for p in self._on() if p != pid] + ([pid] if on else [])
        self.store().set_conf("plugins", json.dumps(cur))
        return f"{PLUGINS[pid][0]} 을(를) {'켰' if on else '껐'}습니다"

    def admin_password(self):
        try:
            return open(os.path.join(self.dir, "관리자 비밀번호.txt"), encoding="utf-8").read().strip()
        except OSError:
            return ""
