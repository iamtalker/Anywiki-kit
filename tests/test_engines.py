"""엔진·옮기기 시험(인터넷 없이): 마크다운 엔진에 문서를 넣고, 네 형식으로 내보냈다 다시 가져와 같아지는지.
DokuWiki 는 받아 둔 파일이 있을 때만(ANYWIKI_DOKU_LAYER=받아 둔 .tgz), MediaWiki 는 이 시험에서 다루지 않는다."""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.environ.pop("ENGINE", None)
import engines  # noqa: E402
import transfer  # noqa: E402
import wikiconv  # noqa: E402
from engines.base import Page  # noqa: E402

DOCS = {
    "대문": "# 환영\n\n**굵게** 와 [[다른 문서]] 링크.\n\n- 하나\n- 둘\n",
    "다른 문서": "| 가 | 나 |\n|---|---|\n| 1 | 2 |\n\n각주[^1]\n\n[^1]: 설명\n",
    "분류:예시": "예시 분류.\n",
}
fails = 0


def check(cond, msg):
    global fails
    if not cond:
        fails += 1
        print("실패:", msg)


def make_root():
    root = tempfile.mkdtemp(prefix="awtest-")
    shutil.copy(os.path.join(ROOT, "sources.json"), root)
    return root


root = make_root()
try:
    e = engines.get("markdown", root)
    e.install(lambda m: None)
    check(e.installed(), "마크다운 엔진 설치")
    for t, x in DOCS.items():
        check(e.put(Page(t, x, "2026-09-01 10:00:00", "시험", "처음")), f"넣기 {t}")
    check(not e.put(Page("대문", DOCS["대문"])), "같은 내용은 새 판을 만들지 않음")
    check(e.count() == 3, f"문서 수 {e.count()}")
    check(e.get("대문").text == DOCS["대문"], "읽기")
    check([p.title for p in e.changes_since("2026-08-31 00:00:00")] != [], "changes_since")

    for fmt in transfer.FORMATS:
        out = os.path.join(root, "export", f"t-{fmt}{transfer.EXT[fmt]}")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        pages, resolve = transfer.engine_pages(e)
        n = transfer.WRITERS[fmt](transfer.translate(pages, "markdown", fmt, resolve), out)
        check(n == 3, f"{fmt} 내보내기 수 {n}")
        check(transfer.detect(out) == fmt, f"{fmt} 형식 알아보기: {transfer.detect(out)}")
        # 새 위키에 가져오기
        r2 = make_root()
        try:
            e2 = engines.get("markdown", r2)
            e2.install(lambda m: None)
            open(os.path.join(r2, "panel.json"), "w").write('{"engine": "markdown"}')
            transfer.import_file(r2, out)
            check(e2.count() == 3, f"{fmt} 가져오기 수 {e2.count()}")
            got = getattr(transfer, "read_" + fmt)(out)
            got = got[0] if fmt == "dokuwiki" else list(got)
            if got:
                check(len(got) == 3, f"{fmt} 읽기 수 {len(got)}")
                titles = {p.title for p in got}
                check(titles == set(DOCS), f"{fmt} 제목 {titles}")
                for p in got:
                    back = wikiconv.convert(p.text, transfer.SYNTAX[fmt], "markdown", p.title)
                    for w in ("굵게", "환영", "설명", "하나"):
                        if w in DOCS.get(p.title, ""):
                            check(w in back, f"{fmt} 에서 '{w}' 잃음: {back!r}")
        finally:
            shutil.rmtree(r2, ignore_errors=True)

    # 엔진 바꾸기: 마크다운 → DokuWiki
    doku = os.environ.get("ANYWIKI_DOKU_LAYER")
    if doku and shutil.which("php"):
        os.makedirs(os.path.join(root, "tools"), exist_ok=True)
        shutil.copy(doku, os.path.join(root, "tools", os.path.basename(doku)))
        import json
        json.dump({"engine": "markdown"}, open(os.path.join(root, "panel.json"), "w"))
        n = transfer.switch(root, "dokuwiki", lambda m: None)
        d = engines.get("dokuwiki", root)
        check(n == 3 and d.count() == 4, f"(설치 때 넣은 start + 3) DokuWiki 로 바꾸기 {n} {d.count()}")
        check("굵게" in d.get("대문").text, "DokuWiki 본문")
    else:
        print("(DokuWiki 바꾸기 시험은 건너뜀: ANYWIKI_DOKU_LAYER 와 php 필요)")
finally:
    shutil.rmtree(root, ignore_errors=True)

print("엔진 시험 통과" if not fails else f"엔진 시험 {fails}개 실패")
sys.exit(1 if fails else 0)
