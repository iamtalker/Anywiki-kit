"""openNAMU 형식 내보내기·가져오기 시험: 내보낸 파일을 다른 위키에 넣으면 같아지는지, 계정 표가 안 나가는지."""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "scripts", "wiki_pack.py")
COLS = "test text default '', "
SCHEMA = [f"create table data ({COLS}title text default '', data text default '', type text default '')",
          f"create table history ({COLS}id text default '', title text default '', data text default '', "
          "date text default '', ip text default '', send text default '', leng text default '', "
          "hide text default '', type text default '')",
          f"create table data_set ({COLS}doc_name text default '', doc_rev text default '', set_name text default '', "
          "set_data text default '')",
          f"create table back ({COLS}title text default '', link text default '', type text default '', "
          "data text default '')",
          f"create table other ({COLS}name text default '', data text default '', coverage text default '')",
          "create table user_set (name text, id text, data text)"]


def make(path, docs):
    db = sqlite3.connect(path)
    for s in SCHEMA:
        db.execute(s)
    db.execute("insert into user_set values ('pw', 'admin', 'secret-hash')")  # 내보내면 안 되는 것
    for title, revs in docs.items():
        for i, (date, text) in enumerate(revs, 1):
            db.execute("insert into history (id, title, data, date, ip, type) values (?, ?, ?, ?, '1.2.3.4', ?)",
                       (str(i), title, text, date, "r1" if i == 1 else ""))
        db.execute("insert into data (title, data) values (?, ?)", (title, revs[-1][1]))
    db.execute("insert into back (title, link, type) values ('category:시험', '문서1', 'cat')")
    db.commit()
    db.close()


def run(*a):
    r = subprocess.run([sys.executable, PACK, *a], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def main():
    d = tempfile.mkdtemp(prefix="aw-pack-")
    try:
        a, b = os.path.join(d, "A"), os.path.join(d, "B")
        os.makedirs(a)
        os.makedirs(b)
        make(os.path.join(a, "data.db"), {
            "문서1": [("2026-01-01 00:00:00", "첫 판"), ("2026-02-01 00:00:00", "둘째 판 [[분류:시험]]")],
            "문서2": [("2026-01-05 00:00:00", "A 만 가진 문서")],
            "문서3": [("2026-03-01 00:00:00", "A 쪽 옛 판")]})
        make(os.path.join(b, "data.db"), {
            "문서1": [("2026-01-01 00:00:00", "첫 판")],                      # A 가 더 새로움 → 이어 붙임
            "문서3": [("2026-04-01 00:00:00", "B 쪽이 더 새로움")]})           # B 가 더 새로움 → 건너뜀
        out = os.path.join(d, "a.db")
        run("export", a, "--out", out)
        x = sqlite3.connect(out)
        assert x.execute("select count(*) from data").fetchone()[0] == 3
        assert "user_set" not in {r[0] for r in x.execute("select name from sqlite_master")}
        x.close()
        assert "가져온 문서 2개" in run("import", b, out)
        B = dict(sqlite3.connect(os.path.join(b, "data.db")).execute("select title, data from data"))
        assert B == {"문서1": "둘째 판 [[분류:시험]]", "문서2": "A 만 가진 문서", "문서3": "B 쪽이 더 새로움"}, B
        bdb = sqlite3.connect(os.path.join(b, "data.db"))
        assert bdb.execute("select id, type, send from history where title = '문서1' order by id + 0").fetchall() == \
            [("1", "r1", ""), ("2", "", "[가져옴 a.db]")]
        assert bdb.execute("select count(*) from back where link = '문서1'").fetchone()[0] == 1
        assert bdb.execute("select data from other where name = 'count_all_title'").fetchone()[0] == "3"
        assert "가져온 문서 0개" in run("import", b, out)  # 다시 넣으면 모두 건너뜀
        print("test_pack: 통과")
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    main()
