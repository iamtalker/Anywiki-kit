"""옮기기 시험(인터넷 없이): openNAMU 위키에 문서를 넣고, 네 형식으로 내보내고, openNAMU 형식은 새 위키에 가져와 같아지는지."""
import os
import shutil
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.environ.pop("ENGINE", None)
import engines  # noqa: E402
import transfer  # noqa: E402
from engines.base import Page  # noqa: E402

COLS = "test text default '', "
SCHEMA = [f"create table data ({COLS}title text default '', data text default '', type text default '')",
          f"create table history ({COLS}id text default '', title text default '', data text default '', "
          "date text default '', ip text default '', send text default '', leng text default '', "
          "hide text default '', type text default '')",
          f"create table data_set ({COLS}doc_name text default '', doc_rev text default '', set_name text default '', "
          "set_data text default '')",
          f"create table back ({COLS}title text default '', link text default '', type text default '', "
          "data text default '')",
          f"create table other ({COLS}name text default '', data text default '', coverage text default '')"]

DOCS = {
    "대문": "== 환영 ==\n'''굵게''' 와 [[다른 문서]] 링크.\n * 하나\n * 둘\n",
    "다른 문서": "||<-2> 가 ||\n|| 1 || 2 ||\n\n각주[* 설명]\n[[분류:예시]]\n",
    "분류:예시": "예시 분류.\n",
}
fails = 0


def check(cond, msg):
    global fails
    if not cond:
        fails += 1
        print("실패:", msg)


def make_root():
    """openNAMU 가 설치된 것처럼 꾸민 임시 폴더(실행 파일은 빈 파일, 시험에는 DB 만 쓴다).
    새 구조처럼 최상위(top) 안에 kit(root)와 wikis 를 나란히 둔다. 키트 폴더(kit)를 돌려준다."""
    top = tempfile.mkdtemp(prefix="awtest-")
    root = os.path.join(top, "kit")
    os.makedirs(root)
    shutil.copy(os.path.join(ROOT, "sources.json"), root)
    d = os.path.join(top, "wikis", "opennamu")
    os.makedirs(d)
    open(os.path.join(d, "main.amd64.exe" if os.name == "nt" else "main.bin"), "w").close()
    db = sqlite3.connect(os.path.join(d, "data.db"))
    for s in SCHEMA:
        db.execute(s)
    db.commit()
    db.close()
    return root


root = make_root()
try:
    e = engines.get("opennamu", root)
    check(e.installed(), "설치된 것으로 보임")
    check(engines.ENGINES == ("opennamu",), f"엔진은 openNAMU 하나: {engines.ENGINES}")
    for t, x in DOCS.items():
        check(e.put(Page(t, x, "2026-09-01 10:00:00", "시험", "처음")), f"넣기 {t}")
    check(not e.put(Page("대문", DOCS["대문"])), "같은 내용은 새 판을 만들지 않음")
    check(e.count() == 3, f"문서 수 {e.count()}")
    check(e.get("대문").text == DOCS["대문"], "읽기")

    for fmt in transfer.FORMATS:
        out = os.path.join(root, "export", f"t-{fmt}{transfer.EXT[fmt]}")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        n = transfer.WRITERS[fmt](transfer.translate(transfer.engine_pages(e), "opennamu", fmt), out)
        check(n == 3 and os.path.getsize(out) > 0, f"{fmt} 내보내기 수 {n}")
        if fmt == "mediawiki":
            import gzip
            xml = gzip.open(out, "rt", encoding="utf-8").read()
            check("굵게" in xml and "<title>대문</title>" in xml, "mediawiki XML 내용")
        if fmt == "markdown":
            import zipfile
            z = zipfile.ZipFile(out)
            check(any("굵게" in z.read(x).decode("utf-8") for x in z.namelist() if x.endswith(".md")), "markdown 내용")
        if fmt != "opennamu":
            continue
        check(transfer.detect(out) == "opennamu", "형식 알아보기")
        r2 = make_root()  # 새 위키에 가져오기
        try:
            e2 = engines.get("opennamu", r2)
            check(transfer.import_file(r2, out) == 3, "가져오기 수")
            check(e2.count() == 3, f"가져온 뒤 문서 수 {e2.count()}")
            check("굵게" in e2.get("대문").text, f"'굵게' 잃음: {e2.get('대문').text!r}")
            check(transfer.import_file(r2, out) == 0, "다시 넣으면 모두 건너뜀")
        finally:
            shutil.rmtree(os.path.dirname(r2), ignore_errors=True)
    for bad in ("a.xml", "a.zip", "a.md"):
        try:
            transfer.detect(bad)
            check(False, f"{bad} 는 가져올 수 없어야 함")
        except ValueError:
            pass
finally:
    shutil.rmtree(os.path.dirname(root), ignore_errors=True)

print("옮기기 시험 통과" if not fails else f"옮기기 시험 {fails}개 실패")
sys.exit(1 if fails else 0)
