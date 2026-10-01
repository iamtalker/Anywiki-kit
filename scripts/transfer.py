"""데이터 옮기기: 내보내기·가져오기·엔진 바꾸기 (애니위키 키트, 표준 라이브러리만).

모든 문서는 '엔진 문법 → 공용 언어(wikiconv) → 다른 문법' 으로 통역된다.
파일 형식(내보내기·가져오기 공통):
  opennamu  : .db   (openNAMU data.db 와 같은 SQLite, 문서 표만. 계정·IP 기록은 넣지 않음)
  mediawiki : .xml.gz (MediaWiki 가져오기 XML)
  dokuwiki  : .zip  (DokuWiki data/pages 폴더 구조)
  markdown  : .zip  (문서마다 .md 하나)

    python transfer.py export <키트 폴더> <형식> [--out 파일]
    python transfer.py import <키트 폴더> <파일>
    python transfer.py switch <키트 폴더> <새 엔진>
엔진은 키트 설정(panel.json 의 engine, 기본 opennamu)을 따른다.
"""
import argparse
import gzip
import html
import json
import os
import pathlib
import re
import sqlite3
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engines  # noqa: E402
import wikiconv  # noqa: E402
from engines.base import Page  # noqa: E402

FORMATS = ("opennamu", "mediawiki", "dokuwiki", "markdown")
EXT = {"opennamu": ".db", "mediawiki": ".xml.gz", "dokuwiki": ".zip", "markdown": ".zip"}
SYNTAX = {"opennamu": "namumark", "mediawiki": "mediawiki", "dokuwiki": "dokuwiki", "markdown": "markdown"}


def log(msg):
    print(msg, flush=True)


def fmt_secs(sec):
    sec = int(sec)
    return f"{sec}초" if sec < 60 else f"{sec // 60}분" if sec < 3600 else f"{sec // 3600}시간 {sec % 3600 // 60}분"


class Progress:
    def __init__(self, total):
        self.total, self.t0, self.last = max(total, 1), time.time(), time.time()

    def tick(self, n, force=False):
        now = time.time()
        if not force and now - self.last < 5:
            return
        self.last = now
        rate = n / max(now - self.t0, 1e-6)
        left = (self.total - n) / rate if rate else 0
        log(f"진행 {n:,}/{self.total:,} ({min(100, n * 100 // self.total)}%) · 초당 {rate:,.0f}개 · 남은 시간 약 {fmt_secs(left)}")


def current_engine(root):
    if os.environ.get("ENGINE") in engines.ENGINES:  # 리눅스·Docker 는 설정 파일 대신 ENGINE 으로 정한다
        return os.environ["ENGINE"]
    try:
        return json.load(open(os.path.join(root, "panel.json"), encoding="utf-8")).get("engine", "opennamu")
    except (OSError, ValueError):
        return "opennamu"


# ================================================================ 통역
def to_doc(engine_name, text, title, resolve=None):
    if engine_name == "dokuwiki" and resolve:
        from wikiconv import dokuwiki
        from wikiconv.tree import tidy
        return tidy(dokuwiki.read(text.replace("\x00", ""), title, resolve))
    return wikiconv.parse(text, SYNTAX[engine_name], title)


def translate(pages, src, dst, resolve=None, total=None):
    """Page(원래 문법) 들 → Page(새 문법). 문제가 있는 문서는 원문을 코드 블록으로 감싸 넣는다(내용은 잃지 않게)."""
    prog = Progress(total or 1)
    for i, p in enumerate(pages, 1):
        if src == dst:
            yield p
        else:
            try:
                text = wikiconv.render(to_doc(src, p.text, p.title, resolve), SYNTAX[dst], p.title)
            except Exception as e:  # 한 문서가 이상해도 전체를 멈추지 않는다
                log(f"  통역 실패(원문 보존): {p.title} — {e}")
                text = wikiconv.render(wikiconv.Doc([["raw", SYNTAX[src], p.text]]), SYNTAX[dst], p.title)
            yield Page(p.title, text, p.modified, p.author, p.summary)
        if total:
            prog.tick(i)


# ================================================================ 파일 쓰기
OPENNAMU_SCHEMA = [
    "create table data (test text default '', title text default '', data text default '', type text default '')",
    "create table history (test text default '', id text default '', title text default '', data text default '', "
    "date text default '', ip text default '', send text default '', leng text default '', hide text default '', "
    "type text default '')",
    "create table data_set (test text default '', doc_name text default '', doc_rev text default '', "
    "set_name text default '', set_data text default '')",
    "create table back (test text default '', title text default '', link text default '', type text default '', "
    "data text default '')",
    "create table yourwiki_pack (k text primary key, v text)",
]
CAT_RE = re.compile(r"\[\[분류:([^\]|#]+)")


def write_opennamu(pages, out):
    from engines.opennamu import to_db_title
    part = out + ".part"
    if os.path.exists(part):
        os.remove(part)
    db = sqlite3.connect(part)
    for s in OPENNAMU_SCHEMA:
        db.execute(s)
    n = 0
    for p in pages:
        t = to_db_title(p.title)
        when = p.modified or time.strftime("%Y-%m-%d %H:%M:%S")
        db.execute("insert into data (title, data, type) values (?, ?, '')", (t, p.text))
        db.execute("insert into history (id, title, data, date, ip, send, leng, hide, type) values "
                   "('1', ?, ?, ?, ?, ?, ?, '', 'r1')", (t, p.text, when, p.author or "애니위키 키트", p.summary or "",
                                                         str(len(p.text))))
        db.executemany("insert into data_set (doc_name, doc_rev, set_name, set_data) values (?, '', ?, ?)",
                       [(t, "last_edit", when), (t, "length", str(len(p.text)))])
        db.executemany("insert into back (link, title, type, data) values (?, ?, 'cat', '')",
                       [(t, "category:" + c.strip()) for c in dict.fromkeys(CAT_RE.findall(p.text))])
        n += 1
    db.executemany("insert into yourwiki_pack values (?, ?)", [("format", "anywiki-opennamu-1"), ("range", "all"),
                                                               ("created", time.strftime("%Y-%m-%d %H:%M:%S")),
                                                               ("docs", str(n))])
    db.execute("create index history_title_id_index on history (title, id)")
    db.execute("create index data_title_index on data (title)")
    db.commit()
    db.close()
    os.replace(part, out)
    return n


def write_mediawiki(pages, out, sitename="애니위키"):
    from wikiconv.mediawiki import mw_title
    n = 0
    with gzip.open(out + ".part", "wt", encoding="utf-8", compresslevel=6) as f:
        f.write('<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/" version="0.11" xml:lang="ko">\n'
                f"<siteinfo><sitename>{html.escape(sitename)}</sitename><case>first-letter</case></siteinfo>\n")
        for p in pages:
            t = mw_title(p.title)
            ns = 14 if t.startswith("Category:") else 10 if t.startswith("Template:") else 0
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(
                time.mktime(time.strptime(p.modified, "%Y-%m-%d %H:%M:%S")) if p.modified else time.time()))
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", p.text)
            f.write(f"<page><title>{html.escape(t)}</title><ns>{ns}</ns><revision><timestamp>{ts}</timestamp>"
                    f"<contributor><username>{html.escape(p.author or '애니위키 키트')}</username></contributor>"
                    f"<comment>{html.escape(p.summary or '애니위키 키트로 내보냄')}</comment>"
                    f"<model>wikitext</model><format>text/x-wiki</format>"
                    f'<text xml:space="preserve">{html.escape(text, quote=False)}</text></revision></page>\n')
            n += 1
        f.write("</mediawiki>\n")
    os.replace(out + ".part", out)
    return n


def write_dokuwiki(pages, out):
    from wikiconv.dokuwiki import doku_id
    from engines.dokuwiki import id_path
    seen, titles, n = set(), {}, 0
    with zipfile.ZipFile(out + ".part", "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for p in pages:
            pid = base = doku_id(p.title)
            k = 2
            while pid in seen:  # 대소문자·기호만 다른 제목은 DokuWiki 에서 같은 ID 가 되므로 번호를 붙인다
                pid, k = f"{base}_{k}", k + 1
            seen.add(pid)
            titles[pid] = p.title
            z.writestr("data/pages/" + id_path(pid) + ".txt", f"====== {p.title} ======\n\n" + p.text)
            n += 1
        z.writestr("anywiki_titles.json", json.dumps(titles, ensure_ascii=False))
        z.writestr("읽어 주세요.txt", "이 압축 파일의 data/ 폴더를 DokuWiki 폴더에 덮어 풀고, php bin/indexer.php 로 검색 색인을 만드세요.\n"
                                  "애니위키 키트의 '가져오기'로 넣어도 됩니다.\n")
    os.replace(out + ".part", out)
    return n


def write_markdown(pages, out):
    from wikiconv.markdown import md_name
    folder, seen, n = "anywiki-markdown/", set(), 0
    with zipfile.ZipFile(out + ".part", "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for p in pages:
            name = base = md_name(p.title)
            k = 2
            while name.lower() in seen:  # 대소문자만 다른 제목(윈도는 같은 파일로 본다)
                name, k = f"{base[:-3]} ({k}).md", k + 1
            seen.add(name.lower())
            z.writestr(folder + name, p.text)
            n += 1
    os.replace(out + ".part", out)
    return n


WRITERS = {"opennamu": write_opennamu, "mediawiki": write_mediawiki, "dokuwiki": write_dokuwiki,
           "markdown": write_markdown}


# ================================================================ 파일 읽기
def detect(path):
    low = path.lower()
    if low.endswith((".db", ".sqlite", ".sqlite3")):
        return "opennamu"
    if low.endswith((".xml", ".xml.gz")):
        return "mediawiki"
    if low.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        if any(re.search(r"(^|/)data/pages/.+\.txt$", n) for n in names):
            return "dokuwiki"
        if any(n.lower().endswith(".md") for n in names):
            return "markdown"
    if low.endswith(".md"):
        return "markdown"
    raise ValueError("알 수 없는 파일 형식입니다(.db / .xml / .xml.gz / DokuWiki·Markdown .zip)")


def read_opennamu(path):
    from engines.opennamu import from_db_title
    db = sqlite3.connect(pathlib.Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        has_set = db.execute("select 1 from sqlite_master where name = 'data_set'").fetchone()
        for t, text in db.execute("select title, data from data").fetchall():
            m = db.execute("select set_data from data_set where doc_name = ? and set_name = 'last_edit' and doc_rev = ''",
                           (t,)).fetchone() if has_set else None
            yield Page(from_db_title(t), text or "", (m[0] if m else "")[:19])
    finally:
        db.close()


def read_mediawiki(path):
    from wikiconv.mediawiki import to_common
    opener = gzip.open if path.lower().endswith(".gz") else open
    with opener(path, "rb") as f:
        title, ns, text, ts, user = "", "0", "", "", ""
        for ev, el in ET.iterparse(f, events=("end",)):
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "title":
                title = el.text or ""
            elif tag == "ns":
                ns = el.text or "0"
            elif tag == "timestamp":
                ts = el.text or ""
            elif tag in ("username", "ip"):
                user = el.text or ""
            elif tag == "text":
                text = el.text or ""
            elif tag == "page":
                if ns in ("0", "10", "14"):
                    mod = ""
                    if ts:
                        t = time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
                        import calendar
                        mod = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(calendar.timegm(t)))
                    yield Page(to_common(title), text, mod, user)
                title, ns, text, ts, user = "", "0", "", "", ""
                el.clear()


def read_dokuwiki(path):
    """(Page 들, 링크 ID → 제목 함수)."""
    from engines.dokuwiki import H1_RE
    from wikiconv.dokuwiki import doku_id, id_to_title
    z = zipfile.ZipFile(path)
    titles = {}
    for n in z.namelist():
        if n.endswith("anywiki_titles.json"):
            titles = json.loads(z.read(n).decode("utf-8"))
    entries = []
    for n in z.namelist():
        m = re.search(r"(?:^|/)data/pages/(.+)\.txt$", n)
        if not m:
            continue
        pid = ":".join(urllib.parse.unquote(p) for p in m.group(1).split("/"))
        text = z.read(n).decode("utf-8", "replace")
        h = H1_RE.match(text)
        title = titles.get(pid) or (h.group(1).strip() if h else id_to_title(pid))
        if h and h.group(1).strip() == title:
            text = text[h.end():].lstrip("\n")
        info = z.getinfo(n)
        entries.append(Page(title, text, time.strftime("%Y-%m-%d %H:%M:%S", info.date_time + (0, 0, -1))))
        titles.setdefault(pid, title)
    back = {doku_id(t): t for t in titles.values()}
    resolve = lambda pid: titles.get(pid.strip(":").lower()) or back.get(pid.strip(":").lower()) or id_to_title(pid)  # noqa: E731
    return entries, resolve


def read_markdown(path):
    from wikiconv.markdown import md_title
    if path.lower().endswith(".md"):
        yield Page(md_title(os.path.basename(path)), open(path, encoding="utf-8").read())
        return
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.lower().endswith(".md") and not os.path.basename(n).startswith("_"):
                info = z.getinfo(n)
                yield Page(md_title(os.path.basename(n)), z.read(n).decode("utf-8", "replace"),
                           time.strftime("%Y-%m-%d %H:%M:%S", info.date_time + (0, 0, -1)))


# ================================================================ 작업
def engine_pages(e):
    """엔진의 문서들과 (DokuWiki 면) 링크 ID → 제목 함수."""
    return list(e.pages()), (e.resolver() if hasattr(e, "resolver") else None)


def export(root, fmt, out=""):
    name = current_engine(root)
    e = engines.get(name, root)
    out = out or os.path.join(root, "export", f"anywiki-{fmt}{EXT[fmt]}")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    log(f"{engines.NAMES[name]} → {fmt} 형식으로 내보내기 시작 → {out}")
    t0 = time.time()
    if name == "opennamu" and fmt == "opennamu":  # 역사까지 그대로
        import wiki_pack
        n = wiki_pack.export(e.dir, out)
    else:
        pages, resolve = engine_pages(e)
        n = WRITERS[fmt](translate(pages, name, fmt, resolve, len(pages)), out)
    log(f"완료: 문서 {n:,}개, {time.time() - t0:.0f}초 → {out}")
    return n


def put_all(e, pages, total):
    prog = Progress(total)
    if hasattr(e, "put_many"):
        return e.put_many(pages, log)
    n = 0
    for i, p in enumerate(pages, 1):
        n += bool(e.put(p))
        prog.tick(i)
    return n


def import_file(root, path):
    name = current_engine(root)
    e = engines.get(name, root)
    src = detect(path)
    log(f"{src} 형식 파일을 {engines.NAMES[name]} 로 가져오기 시작 ← {os.path.basename(path)}")
    t0 = time.time()
    tag = f"[가져옴 {os.path.basename(path)}] "
    if name == "opennamu" and src == "opennamu":  # 역사까지 그대로, 내 쪽보다 새 판만
        import wiki_pack
        n = wiki_pack.import_pack(e.dir, path)
    else:
        resolve = None
        if src == "opennamu":
            pages = list(read_opennamu(path))
        elif src == "mediawiki":
            pages = list(read_mediawiki(path))
        elif src == "dokuwiki":
            pages, resolve = read_dokuwiki(path)
        else:
            pages = list(read_markdown(path))
        log(f"문서 {len(pages):,}개를 통역합니다")
        out = []
        for p in translate(pages, src, name, resolve, len(pages)):
            cur = e.get(p.title) if len(pages) < 5000 or name != "mediawiki" else None
            if cur and p.modified and cur.modified >= p.modified:
                continue  # 내 쪽이 같거나 더 새롭다
            p.summary = tag + (p.summary or "")
            out.append(p)
        log(f"넣을 문서 {len(out):,}개(내 쪽이 같거나 더 새로운 {len(pages) - len(out):,}개는 건너뜀)")
        n = put_all(e, out, len(out))
    log(f"가져온 문서 {n:,}개 · {time.time() - t0:.0f}초")
    return n


def switch(root, target, log_fn=log):
    """지금 엔진의 모든 문서를 새 엔진 문법으로 통역해 새 엔진에 넣는다. 옛 엔진의 데이터는 그대로 남는다(백업)."""
    name = current_engine(root)
    if name == target:
        raise ValueError("이미 그 엔진입니다")
    src, dst = engines.get(name, root), engines.get(target, root)
    if not dst.installed():
        log_fn(f"{engines.NAMES[target]} 설치")
        dst.install(log_fn)
    pages, resolve = engine_pages(src) if src.installed() else ([], None)
    import kit  # 첫 화면은 엔진마다 이름이 달라(FrontPage·start·대문) 새 엔진의 첫 화면 이름으로 옮긴다
    a, b = kit.FRONT_TITLE[name], kit.FRONT_TITLE[target]
    if a != b and not any(p.title == b for p in pages):
        pages = [Page(b, p.text, p.modified, p.author, p.summary) if p.title == a else p for p in pages]
    log_fn(f"{engines.NAMES[name]} → {engines.NAMES[target]}: 문서 {len(pages):,}개를 통역해 옮깁니다")
    t0 = time.time()
    n = put_all(dst, translate(pages, name, target, resolve, len(pages)), len(pages))
    log_fn(f"완료: 옮긴 문서 {n:,}개, {time.time() - t0:.0f}초. 옛 엔진의 데이터는 wikis/{name}/ 에 그대로 있습니다")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["export", "import", "switch"])
    ap.add_argument("root")
    ap.add_argument("arg")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    if a.action == "export":
        if a.arg not in FORMATS:
            raise SystemExit(f"형식: {', '.join(FORMATS)}")
        export(root, a.arg, a.out)
    elif a.action == "import":
        import_file(root, a.arg)
    else:
        if a.arg not in engines.ENGINES:
            raise SystemExit(f"엔진: {', '.join(engines.ENGINES)}")
        switch(root, a.arg)
        import kit  # 다 옮긴 뒤에만 지금 엔진을 바꾼다(중간에 끊기면 옛 엔진 그대로)
        st = kit.settings()
        st["engine"] = a.arg
        kit.save_settings(st)


if __name__ == "__main__":
    main()
