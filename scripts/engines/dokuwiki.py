"""DokuWiki 엔진(PHP, 파일 저장).

설치: Docker Hub 공식 이미지(dokuwiki/dokuwiki)의 프로그램 층을 해시로 고정해 받아 wikis/dokuwiki/ 에 푼다.
이미지 안에서 conf·data·lib/plugins·lib/tpl 은 .core 이름으로 들어 있어 원래 자리로 되돌린다.
켜기: PHP 내장 서버(php -S). 관리자 계정은 설치할 때 만들고, 기본 권한은 '누구나 읽기, 로그인한 사람만 편집'.

문서 ID ↔ 제목: 키트가 넣은 문서는 anywiki_titles.json 에 제목을 적어 두고, 문서 첫 줄에 ====== 제목 ====== 을 넣는다.
DokuWiki 화면에서 새로 만든 문서는 첫 제목줄을, 없으면 ID 를 제목으로 쓴다.
"""
import gzip
import json
import os
import re
import secrets
import subprocess
import time
import urllib.parse

from .base import Engine, Page
from . import php as phpmod

SHIPPED_NS = ("wiki", "playground")
H1_RE = re.compile(r"^\s*======\s*(.+?)\s*======\s*\n?")


def id_path(pid):
    """내보낸 zip 용(DokuWiki 기본 설정 fnencode=url 과 같은 파일 이름)."""
    return "/".join(urllib.parse.quote(p, safe="") for p in pid.split(":"))


def id_path_utf8(pid):
    """키트의 DokuWiki 는 fnencode=utf-8(한글 이름이 길어도 파일 이름 한도를 넘지 않게)."""
    return "/".join(pid.split(":"))


class DokuWiki(Engine):
    name = "dokuwiki"
    syntax = "dokuwiki"

    @property
    def app(self):
        return self.dir

    def installed(self):
        return os.path.exists(os.path.join(self.dir, "doku.php")) and \
            os.path.exists(os.path.join(self.dir, "conf", "users.auth.php"))

    def install(self, log=print):
        import fetch
        src = fetch.sources(self.root)["engines"]["dokuwiki"]
        php = phpmod.ensure(self.root, "dokuwiki", log)
        if not os.path.exists(os.path.join(self.dir, "doku.php")):
            log(f"DokuWiki {src['version']} 받기")
            fetch.docker_layer(src["repo"], src["digest"], os.path.join(self.root, "tools"), self.dir, src["subdir"], log)
            for d in ("conf", "data", os.path.join("lib", "plugins"), os.path.join("lib", "tpl")):
                p = os.path.join(self.dir, d)
                if os.path.islink(p) or (os.path.exists(p) and not os.listdir(p)):
                    os.remove(p) if os.path.islink(p) else os.rmdir(p)
                if os.path.exists(p + ".core") and not os.path.exists(p):
                    os.replace(p + ".core", p)
            for f in ("docker.php", "docker.protected.php", "plugins.docker.php"):
                try:
                    os.remove(os.path.join(self.dir, "conf", f))
                except OSError:
                    pass
            for f in (".htaccess", "install.php"):
                try:
                    os.remove(os.path.join(self.dir, f))
                except OSError:
                    pass
        conf = os.path.join(self.dir, "conf")
        if not os.path.exists(os.path.join(conf, "users.auth.php")):
            pw = secrets.token_urlsafe(9)
            h = subprocess.run([php, "-r", "echo password_hash($argv[1], PASSWORD_BCRYPT);", pw],
                               capture_output=True, text=True, timeout=60).stdout.strip()
            if not h.startswith("$2"):
                raise RuntimeError("관리자 비밀번호를 만들지 못했습니다(PHP 확인)")
            with open(os.path.join(conf, "users.auth.php"), "w", encoding="utf-8") as f:
                f.write("# <?php exit()?>\n# 애니위키 키트가 만든 사용자 목록\n"
                        f"admin:{h}:관리자:admin@localhost:admin,user\n")
            with open(os.path.join(conf, "acl.auth.php"), "w", encoding="utf-8") as f:
                f.write("# <?php exit()?>\n*\t@ALL\t1\n*\t@user\t8\n")
            with open(os.path.join(conf, "local.php"), "w", encoding="utf-8") as f:
                f.write("<?php\n$conf['title'] = '애니위키';\n$conf['lang'] = 'ko';\n$conf['useacl'] = 1;\n"
                        "$conf['superuser'] = '@admin';\n$conf['userewrite'] = 0;\n$conf['useheading'] = 1;\n"
                        "$conf['disableactions'] = 'register';\n$conf['start'] = 'start';\n$conf['fnencode'] = 'utf-8';\n")
            with open(os.path.join(self.dir, "관리자 비밀번호.txt"), "w", encoding="utf-8") as f:
                f.write(f"아이디: admin\n비밀번호: {pw}\n")
            log(f"관리자 계정: admin / {pw}  (wikis/dokuwiki/관리자 비밀번호.txt 에도 적어 둠)")
        if not os.path.exists(self.page_file("start")):
            self.put(Page("start", "====== 애니위키 ======\n\n애니위키 키트로 만든 DokuWiki 입니다. "
                                   "이 첫 화면은 자유롭게 고쳐 쓰세요.\n", author="애니위키 키트", summary="첫 화면"))

    def command(self):
        php = phpmod.php_path(self.root)
        return phpmod.server_command(php, self.dir, self.port)

    def admin_password(self):
        try:
            return open(os.path.join(self.dir, "관리자 비밀번호.txt"), encoding="utf-8").read().strip()
        except OSError:
            return ""

    # ---- 경로
    @property
    def data(self):
        return os.path.join(self.dir, "data")

    def page_file(self, pid):
        return os.path.join(self.data, "pages", *id_path_utf8(pid).split("/")) + ".txt"

    def _titles_map(self):
        try:
            return json.load(open(os.path.join(self.dir, "anywiki_titles.json"), encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_titles_map(self, m):
        tmp = os.path.join(self.dir, "anywiki_titles.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(self.dir, "anywiki_titles.json"))

    def ids(self):
        base = os.path.join(self.data, "pages")
        for dp, _, files in os.walk(base):
            for fn in files:
                if fn.endswith(".txt"):
                    rel = os.path.relpath(os.path.join(dp, fn[:-4]), base)
                    pid = ":".join(rel.split(os.sep))
                    if pid.split(":")[0] in SHIPPED_NS and not os.path.exists(
                            os.path.join(self.data, "meta", *pid.split(":")) + ".changes"):
                        continue  # DokuWiki 가 딸려 보낸 설명서(wiki:syntax 등)는 한 번도 고치지 않았으면 위키 문서로 치지 않는다
                    yield pid

    def title_of(self, pid, text=None, m=None):
        m = self._titles_map() if m is None else m
        if pid in m:
            return m[pid]
        if text is not None:
            h = H1_RE.match(text)
            if h:
                return h.group(1).strip()
        from wikiconv.dokuwiki import id_to_title
        return id_to_title(pid)

    def resolver(self):
        """문서 안 링크의 ID → 제목."""
        m = self._titles_map()
        from wikiconv.dokuwiki import id_to_title
        from wikiconv.dokuwiki import doku_id
        back = {doku_id(t): t for t in m.values()}
        return lambda pid: m.get(pid.strip(":").lower()) or back.get(pid.strip(":").lower()) or id_to_title(pid)

    def titles(self):
        m = self._titles_map()
        return [self.title_of(pid, self._read(pid), m) for pid in self.ids()]

    def _read(self, pid):
        try:
            with open(self.page_file(pid), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def _body(self, title, text):
        """키트가 붙인 첫 제목줄을 떼고 본문만."""
        h = H1_RE.match(text)
        return text[h.end():].lstrip("\n") if h and h.group(1).strip() == title else text

    def pages(self):
        m = self._titles_map()
        for pid in sorted(self.ids()):
            text = self._read(pid)
            t = self.title_of(pid, text, m)
            mtime = os.path.getmtime(self.page_file(pid))
            yield Page(t, self._body(t, text), time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)))

    def get(self, title):
        from wikiconv.dokuwiki import doku_id
        pid = next((k for k, v in self._titles_map().items() if v == title), None) or doku_id(title)
        text = self._read(pid)
        if not text:
            return None
        return Page(title, self._body(title, text),
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(self.page_file(pid)))))

    def put(self, page):
        from wikiconv.dokuwiki import doku_id
        m = self._titles_map()
        pid = next((k for k, v in m.items() if v == page.title), None) or (page.title if page.title == "start"
                                                                           else doku_id(page.title))
        body = page.text
        if page.title != pid and not H1_RE.match(body):
            body = f"====== {page.title} ======\n\n" + body
        path = self.page_file(pid)
        old = self._read(pid)
        if old == body:
            return False
        ts = int(time.mktime(time.strptime(page.modified, "%Y-%m-%d %H:%M:%S"))) if page.modified else int(time.time())
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if old:  # 옛 판을 attic 에
            attic = os.path.join(self.data, "attic", *id_path_utf8(pid).split("/")) + f".{int(os.path.getmtime(path))}.txt.gz"
            os.makedirs(os.path.dirname(attic), exist_ok=True)
            with gzip.open(attic, "wt", encoding="utf-8") as f:
                f.write(old)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, path)
        os.utime(path, (ts, ts))
        # 바뀜 기록(DokuWiki 형식: 시각 IP 종류 ID 사용자 요약 덧붙임 크기변화)
        kind = "E" if old else "C"
        user = re.sub(r"\s", "_", page.author or "anywiki")
        line = f"{ts}\t127.0.0.1\t{kind}\t{pid}\t{user}\t{(page.summary or '').replace(chr(9), ' ')}\t\t{len(body) - len(old)}\n"
        meta = os.path.join(self.data, "meta", *id_path_utf8(pid).split("/")) + ".changes"
        os.makedirs(os.path.dirname(meta), exist_ok=True)
        with open(meta, "a", encoding="utf-8") as f:
            f.write(line)
        with open(os.path.join(self.data, "meta", "_dokuwiki.changes"), "a", encoding="utf-8") as f:
            f.write(line)
        if page.title != pid and m.get(pid) != page.title:
            m[pid] = page.title
            self._save_titles_map(m)
        return True

    def put_many(self, pages, log=None):
        n = 0
        for i, p in enumerate(pages, 1):
            n += bool(self.put(p))
            if log and i % 2000 == 0:
                log(f"  {i:,}개 넣음")
        self.reindex(log)
        return n

    def reindex(self, log=None):
        """검색 색인을 다시 만든다(많이 넣은 뒤)."""
        php = phpmod.php_path(self.root)
        if php and os.path.exists(os.path.join(self.dir, "bin", "indexer.php")):
            if log:
                log("  검색 색인 만드는 중…")
            subprocess.run([php, os.path.join(self.dir, "bin", "indexer.php"), "-q"], cwd=self.dir,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3600)

    def changes_since(self, ts):
        t0 = time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S")) if ts else 0
        return [p for p in self.pages() if time.mktime(time.strptime(p.modified, "%Y-%m-%d %H:%M:%S")) > t0]

    def info(self):
        try:
            return {"version": open(os.path.join(self.dir, "VERSION"), encoding="utf-8").read().strip()}
        except OSError:
            return {}
