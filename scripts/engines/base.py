"""엔진 공통 틀."""
import os
import socket
import subprocess
import time


class Page:
    __slots__ = ("title", "text", "modified", "author", "summary")

    def __init__(self, title, text, modified="", author="", summary=""):
        self.title, self.text, self.modified, self.author, self.summary = title, text, modified or "", author or "", summary or ""

    def __repr__(self):
        return f"Page({self.title!r}, {len(self.text)}자, {self.modified!r})"


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def port_open(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


class Engine:
    name = ""
    syntax = ""            # wikiconv 형식 이름
    port = 4001            # 엔진이 받는 내부 포트(중계 서버가 4000 에서 받아 넘긴다)
    write_while_running = True   # 켜진 채로 문서를 넣어도 되나(openNAMU 는 아니오)

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.dir = os.path.join(self.root, "wikis", self.name)

    # ---- 설치·켜기
    def installed(self):
        raise NotImplementedError

    def install(self, log=print):
        raise NotImplementedError

    def command(self):
        """엔진을 켜는 명령 (args, cwd, env)."""
        raise NotImplementedError

    def ready(self):
        return port_open(self.port)

    def spawn(self, log_path):
        args, cwd, env = self.command()
        out = open(log_path, "a", encoding="utf-8", errors="replace")
        flags = 0x08000000 if os.name == "nt" else 0
        # 리눅스: 새 프로세스 묶음으로 띄워, 끌 때 묶음째 끈다(panel.stop)
        return subprocess.Popen(args, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, env=env, creationflags=flags,
                                start_new_session=os.name != "nt")

    # ---- 문서
    def titles(self):
        return [p.title for p in self.pages()]

    def pages(self):
        """모든 문서의 최신판(Page)."""
        raise NotImplementedError

    def get(self, title):
        for p in self.pages():
            if p.title == title:
                return p
        return None

    def put(self, page):
        """새 판으로 올린다(역사에 남김). 바뀐 게 없으면 False."""
        raise NotImplementedError

    def changes_since(self, ts):
        """ts(YYYY-MM-DD HH:MM:SS) 뒤에 바뀐 문서의 최신판."""
        return [p for p in self.pages() if p.modified > ts]

    def count(self):
        return sum(1 for _ in self.titles())

    def info(self):
        return {}
