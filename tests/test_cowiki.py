"""공동위키 시험(인터넷 없이): 두 위키(A: Markdown, B: Markdown 또는 DokuWiki)가 서로 등록해야만 이어지고,
편집을 공용 언어로 주고받고, 받은 판을 다시 퍼뜨리지 않고, 마지막에 쓴 판이 이기는지. 가짜 DHT 로 주소 찾기도."""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.environ.pop("ENGINE", None)
import cowiki  # noqa: E402
import engines  # noqa: E402
from engines.base import Page  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    if not cond:
        fails += 1
        print("실패:", msg)


def ts(delta=0):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + delta))


def make(engine):
    root = tempfile.mkdtemp(prefix="cowiki-")
    shutil.copy(os.path.join(ROOT, "sources.json"), root)
    json.dump({"engine": engine}, open(os.path.join(root, "panel.json"), "w"))
    if engine == "dokuwiki":
        os.makedirs(os.path.join(root, "tools"))
        shutil.copy(os.environ["ANYWIKI_DOKU_LAYER"], os.path.join(root, "tools"))
    e = engines.get(engine, root)
    e.install(lambda m: None)
    st = cowiki.State(root)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), cowiki.make_handler(st))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    return root, e, st, url, srv


b_engine = "dokuwiki" if os.environ.get("ANYWIKI_DOKU_LAYER") and shutil.which("php") else "markdown"
ra, ea, sa, ua, srva = make("markdown")
rb, eb, sb, ub, srvb = make(b_engine)
cowiki.log = lambda m: None
try:
    sa.set_meta("name", "위키A")
    sb.set_meta("name", "위키B")
    ea.put(Page("공동 문서", "**굵게** 쓴 [[다른 문서]]\n\n- 하나\n", ts(-100), "철수", "처음"))
    ea.put(Page("A 만의 문서", "A 에서 씀\n", ts(-100), "철수"))
    wa, wb = cowiki.Worker(sa), cowiki.Worker(sb)

    # 1) B 만 A 를 등록: A 가 B 를 모르므로 A 창구가 거절(not_member)
    sb.add(sa.id, "위키A", ua)
    wb.sync()
    check(sb.members()[0]["status"] == "not_member", f"한쪽만 등록 → {sb.members()[0]['status']}")
    check(eb.get("공동 문서") is None, "한쪽만 등록했는데 문서가 넘어옴")

    # 2) A 도 B 를 등록 → 이어짐
    sa.add(sb.id, "위키B", ub)
    wb.sync()
    check(sb.members()[0]["status"] == "ok", f"서로 등록 → {sb.members()[0]['status']}")
    got = eb.get("공동 문서")
    check(got is not None and "굵게" in got.text, f"B 가 A 의 문서를 받음: {got}")
    check(eb.get("A 만의 문서") is not None, "두 번째 문서")

    # 3) 받은 판을 다시 퍼뜨리지 않음: B 를 살펴도 B 의 기록에 A 문서가 없어야
    cowiki.scan(sb, eb)
    db = sb.db()
    titles = [t for (t,) in db.execute("select title from journal")]
    db.close()
    check("공동 문서" not in titles, f"받은 문서를 다시 퍼뜨림: {titles}")

    # 4) B 에서 고치면 A 가 받음(엔진이 달라도 공용 언어로)
    time.sleep(1.1)
    cur = eb.get("공동 문서")
    eb.put(Page("공동 문서", cur.text + "\n추가한 줄\n", ts(), "영희", "B 에서 고침"))
    cowiki.scan(sb, eb)  # B 의 작업자가 30초마다 하는 일
    wa.sync()
    check("추가한 줄" in (ea.get("공동 문서").text if ea.get("공동 문서") else ""), f"A 가 B 의 편집을 받음: {ea.get('공동 문서')}")

    # 5) 마지막에 쓴 판이 이김: A 가 더 새로 고친 뒤 B 의 옛 판은 A 를 덮지 않음
    time.sleep(1.1)
    ea.put(Page("공동 문서", "A 가 마지막으로 씀\n", ts(), "철수"))
    wa.sync()
    cowiki.scan(sa, ea)  # B 에서 새로 받을 것은 없음
    check("A 가 마지막으로" in ea.get("공동 문서").text, "A 의 새 판이 유지됨")
    wb.sync()
    check("A 가 마지막으로" in eb.get("공동 문서").text, f"B 가 A 의 마지막 판을 받음: {eb.get('공동 문서').text!r}")

    # 6) 미래 시각 판은 받지 않음
    db = sa.db()
    db.execute("insert into journal (title, awm, modified, author, sha) values ('미래', '미래 글', ?, 'x', 'z')",
               (int(time.time()) + 86400,))
    db.commit()
    db.close()
    wb.sync()
    check(eb.get("미래") is None, "미래 시각 판을 받음")

    # 7) 서명 위조: B 가 A 인 척하는 요청 → 거절
    import urllib.request
    import urllib.error
    h = cowiki.signed_headers(sb, sa.id, "/cowiki/changes?since=0")
    h["X-Cowiki-Id"] = "ab" * 32
    try:
        urllib.request.urlopen(urllib.request.Request(ua + "/cowiki/changes?since=0", headers=h), timeout=10)
        check(False, "위조한 요청이 통과")
    except urllib.error.HTTPError as ex:
        check(ex.code == 401, f"위조 요청 → {ex.code}")

    # 8) 엉뚱한 서버(다른 ID)가 주소를 차지하면 응답 서명이 안 맞아 거절
    rc, ec, sc, uc, srvc = make("markdown")
    sc.add(sb.id, "B", ub)
    sb.add(sc.id, "C", ua)   # C 의 주소로 A 의 창구를 적음(가로채기 흉내)
    sa.add(sb.id, "위키B", ub)
    wb.sync()
    mc = next(m for m in sb.members() if m["id"] == sc.id)
    check(mc["status"].startswith("error") or mc["status"] == "not_member", f"엉뚱한 서버 → {mc['status']}")
    srvc.shutdown()
    shutil.rmtree(rc, ignore_errors=True)

    # 9) 가짜 DHT 로 주소 찾기: A 가 주소를 올리고, B 는 주소 없이 등록해 DHT 에서 찾음
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fake_dht
    net = fake_dht.start(6)
    boot = [net[0].addr]
    pa = cowiki.Worker(sa, self_url=ua, bootstrap=boot)
    pa.publish()
    sb.remove(sa.id)
    sb.add(sa.id, "위키A")      # 주소 없이
    db = sb.db()
    db.execute("update members set cursor = 0")
    db.commit()
    db.close()
    pb = cowiki.Worker(sb, bootstrap=boot)
    pb.sync()
    ma = next(m for m in sb.members() if m["id"] == sa.id)
    check(ma["resolved_url"] == ua and ma["status"] == "ok", f"DHT 로 주소 찾기: {ma['resolved_url']} {ma['status']}")
finally:
    for s in (srva, srvb):
        s.shutdown()
    shutil.rmtree(ra, ignore_errors=True)
    shutil.rmtree(rb, ignore_errors=True)

print(f"공동위키 시험 통과(B={b_engine})" if not fails else f"공동위키 시험 {fails}개 실패")
sys.exit(1 if fails else 0)
