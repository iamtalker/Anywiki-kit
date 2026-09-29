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

    # ---- 플러그인
    plugin_search = True
    plugin_note = ("DokuWiki 에 들어 있는 플러그인은 켜고 끌 수 있고, DokuWiki 플러그인 저장소에서 찾아 설치할 수 있습니다. "
                   "저장소의 플러그인은 여러 사람이 만든 것이라 키트가 내용을 검증하지 못합니다. 보안 문제가 알려진 것은 설치하지 않습니다.")

    def _plugin_state(self):
        """plugins.local.php 의 켜고 끈 값, plugins.required.php 의 꼭 필요한 것."""
        def read(name):
            try:
                txt = open(os.path.join(self.dir, "conf", name), encoding="utf-8").read()
            except OSError:
                return {}
            return {k: v == "1" for k, v in re.findall(r"\$plugins\['([^']+)'\]\s*=\s*(\d)", txt)}
        return read("plugins.local.php"), read("plugins.required.php")

    def plugins(self):
        local, req = self._plugin_state()
        base = os.path.join(self.dir, "lib", "plugins")
        out = []
        for pid in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            info = os.path.join(base, pid, "plugin.info.txt")
            if not os.path.exists(info):
                continue
            meta = dict(re.findall(r"^(\w+)\s+(.+)$", open(info, encoding="utf-8", errors="replace").read(), re.M))
            out.append({"id": pid, "name": meta.get("name", pid), "desc": meta.get("desc", ""),
                        "on": local.get(pid, True), "locked": pid in req})
        return out

    def set_plugin(self, pid, on, log=print):
        local, req = self._plugin_state()
        if not os.path.exists(os.path.join(self.dir, "lib", "plugins", pid, "plugin.info.txt")):
            raise ValueError("없는 플러그인입니다")
        if pid in req:
            raise ValueError("DokuWiki 가 꼭 필요로 하는 플러그인이라 끌 수 없습니다")
        local[pid] = bool(on)
        path = os.path.join(self.dir, "conf", "plugins.local.php")
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            f.write("<?php\n/* 애니위키 관리판과 DokuWiki 확장 관리자가 함께 쓰는 플러그인 켜고 끄기 */\n" +
                    "".join(f"$plugins['{k}'] = {int(v)};\n" for k, v in sorted(local.items())))
        os.replace(path + ".tmp", path)
        self._touch_conf()
        return f"{pid} 플러그인을 {'켰' if on else '껐'}습니다"

    def _touch_conf(self):
        """설정이 바뀐 것을 DokuWiki 에 알린다(캐시 무효화)."""
        try:
            os.utime(os.path.join(self.dir, "conf", "local.php"))
        except OSError:
            pass

    def _repo(self):
        import fetch
        return os.environ.get("ANYWIKI_DOKU_REPO") or \
            fetch.sources(self.root).get("plugin_repos", {}).get("dokuwiki", "https://www.dokuwiki.org/lib/plugins/pluginrepo/api.php")

    def _api(self, **q):
        import fetch
        url = self._repo() + "?" + urllib.parse.urlencode(dict(q, fmt="json"), doseq=True)
        with fetch._get(url, timeout=30) as r:
            return json.loads(r.read(4 << 20).decode("utf-8"))

    @staticmethod
    def _entry(d):
        pid = str(d.get("plugin", ""))
        return {"id": pid, "name": d.get("name") or pid, "desc": d.get("description", ""),
                "updated": d.get("lastupdate", ""), "popularity": d.get("popularity", 0),
                "security": d.get("securityissue", "") or d.get("securitywarning", ""),
                "download": d.get("downloadurl", ""), "url": f"https://www.dokuwiki.org/plugin:{pid}",
                "template": pid.startswith("template:")}

    def search_plugins(self, q):
        got = self._api(q=q) if q else self._api(cat="", order="popularity")
        items = got if isinstance(got, list) else list(got.values()) if isinstance(got, dict) else []
        have = {p["id"] for p in self.plugins()}
        out = []
        for d in items:
            e = self._entry(d)
            if e["id"] and not e["template"]:
                e["installed"] = e["id"] in have
                out.append(e)
        return out[:50]

    def install_plugin(self, pid, log=print):
        """저장소에서 플러그인 하나를 받아 lib/plugins/<id>/ 에 넣는다."""
        import fetch
        import shutil
        import tarfile
        import tempfile
        import zipfile
        if not re.fullmatch(r"[a-z0-9_]+", pid or ""):
            raise ValueError("플러그인 이름이 올바르지 않습니다")
        got = self._api(**{"ext[]": [pid]})
        items = got if isinstance(got, list) else list(got.values()) if isinstance(got, dict) else []
        e = next((self._entry(d) for d in items if str(d.get("plugin")) == pid), None)
        if not e or not e["download"]:
            raise ValueError("저장소에 그 플러그인이 없거나 받을 주소가 없습니다")
        if e["security"]:
            raise ValueError(f"보안 문제가 알려진 플러그인이라 설치하지 않습니다: {e['security']}")
        if not e["download"].startswith("https://") and not os.environ.get("ANYWIKI_DOKU_REPO"):  # 시험용 저장소만 http
            raise ValueError("https 가 아닌 주소에서는 받지 않습니다")
        tmp = tempfile.mkdtemp(prefix="dwplugin-", dir=self.dir)
        try:
            arc = os.path.join(tmp, "plugin.bin")
            log(f"{pid} 받는 중: {e['download']}")
            fetch.download(e["download"], arc, log=log)
            if os.path.getsize(arc) > 50 << 20:
                raise ValueError("파일이 너무 큽니다(50MB 넘음)")
            out = os.path.join(tmp, "x")
            os.makedirs(out)
            real = os.path.realpath(out)

            def safe(name):
                dest = os.path.realpath(os.path.join(out, name))
                if not (dest == real or dest.startswith(real + os.sep)):
                    raise ValueError(f"압축 파일에 위험한 경로가 있습니다: {name}")
                return dest
            if zipfile.is_zipfile(arc):
                with zipfile.ZipFile(arc) as z:
                    for n in z.namelist():
                        safe(n)
                    z.extractall(out)
            else:
                with tarfile.open(arc) as t:
                    members = [m for m in t.getmembers() if m.isfile() or m.isdir()]
                    for m in members:
                        safe(m.name)
                    t.extractall(out, members=members)
            src = None
            for dp, _, files in os.walk(out):
                if "plugin.info.txt" in files:
                    if src is None or len(dp) < len(src):
                        src = dp
            if not src:
                raise ValueError("DokuWiki 플러그인이 아닙니다(plugin.info.txt 없음)")
            dest = os.path.join(self.dir, "lib", "plugins", pid)
            old = dest + ".old"
            if os.path.exists(dest):
                shutil.rmtree(old, ignore_errors=True)
                os.replace(dest, old)
            shutil.move(src, dest)
            shutil.rmtree(old, ignore_errors=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self._touch_conf()
        log(f"{pid} 플러그인을 설치했습니다")
        return f"{pid} 플러그인을 설치했습니다"
