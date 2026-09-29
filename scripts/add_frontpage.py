"""새 위키의 첫 화면 문서(FrontPage)를 넣는다. 이미 있으면 그대로 둔다(--force 로 덮어쓰기).

사용: python add_frontpage.py <wiki 폴더> [--force]
"""
import os
import sqlite3
import sys
import time

TITLE = "FrontPage"
TEXT = """[목차]
== 새 위키에 오신 것을 환영합니다 ==
이 위키는 '''애니위키 키트'''로 만든 위키입니다. 이 첫 화면은 키트가 넣은 안내 문서이니 자유롭게 고쳐 쓰세요.

== 처음 할 일 ==
 * '''관리자 계정''': 처음 가입한 사람이 관리자가 됩니다. 공개하기 전에 먼저 가입하세요.
 * '''편집 권한''': 관리자 설정에서 누구나 / 가입자만 / 읽기 전용 중에서 정하세요.
 * '''위키 이름''': 관리자 설정에서 바꿀 수 있습니다.

== 문법 ==
이 위키는 openNAMU 엔진을 씁니다. 문법은 나무마크와 같습니다.
 * 굵게 {{{'''글자'''}}} · 기울임 {{{''글자''}}} · 링크 {{{[[문서 이름]]}}} · 문단 {{{== 제목 ==}}} · 분류 {{{[[분류:분류 이름]]}}}

== 키트 ==
 * 켜기·끄기, 인터넷에 공개, 다른 위키(MediaWiki·DokuWiki·Markdown)로 내보내기, openNAMU 형식 가져오기는 '''관리판'''에서 합니다.
 * 키트와 사용법: [[https://github.com/iamtalker/anywiki-kit|github.com/iamtalker/anywiki-kit]]
"""


def main(wiki_dir, force=False):
    db = sqlite3.connect(os.path.join(wiki_dir, "data.db"), timeout=60)
    if db.execute("select 1 from data where title = ?", (TITLE,)).fetchone() and not force:
        print("첫 화면 문서가 이미 있습니다")
        return
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    db.execute("delete from data where title = ?", (TITLE,))
    db.execute("insert into data (title, data, type) values (?, ?, '')", (TITLE, TEXT))
    rev = (db.execute("select max(id + 0) from history where title = ?", (TITLE,)).fetchone()[0] or 0) + 1
    db.execute("insert into history (id, title, data, date, ip, send, leng, hide, type) "
               "values (?, ?, ?, ?, '애니위키 키트', '첫 화면', ?, '', ?)",
               (str(rev), TITLE, TEXT, now, str(len(TEXT)), "r1" if rev == 1 else ""))
    db.execute("delete from data_set where doc_name = ? and set_name in ('last_edit', 'length')", (TITLE,))
    db.executemany("insert into data_set (doc_name, doc_rev, set_name, set_data) values (?, '', ?, ?)",
                   [(TITLE, "last_edit", now), (TITLE, "length", str(len(TEXT)))])
    db.commit()
    print("첫 화면 문서를 넣었습니다")


if __name__ == "__main__":
    main(sys.argv[1], "--force" in sys.argv)
