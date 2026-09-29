"""애니위키 키트 명령줄 도구 (관리판·리눅스 스크립트·Docker 가 함께 쓴다).

    python kit.py install [엔진]      # 엔진 설치(없으면 지금 엔진). 빈 위키와 첫 화면까지
    python kit.py run-engine          # 지금 엔진을 켠다(이 프로세스가 엔진이 됨: 리눅스·Docker 용)
    python kit.py engine [엔진]       # 지금 엔진 보기 / 바꾸기(데이터는 옮기지 않음. 옮기려면 transfer.py switch)
    python kit.py info                # 엔진·문서 수·관리자 계정 (JSON)
엔진: opennamu · markdown · dokuwiki · mediawiki
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engines  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS = os.path.join(ROOT, "panel.json")
FRONT = """---
categories: []
---
# 새 위키에 오신 것을 환영합니다

이 위키는 **애니위키 키트**로 만든 위키입니다. 이 첫 화면은 키트가 넣은 안내 문서이니 자유롭게 고쳐 쓰세요.

## 처음 할 일

- **관리자 계정**: 관리판의 '상태' 칸에 적힌 관리자 계정으로 로그인하세요(openNAMU 는 처음 가입한 사람이 관리자).
- **편집 권한**: 공개하기 전에 관리자 설정에서 누가 편집할 수 있는지 정하세요.
- **엔진 바꾸기**: 관리판의 '엔진' 칸에서 openNAMU · Markdown · DokuWiki · MediaWiki 사이를 오갈 수 있습니다. 문서는 자동으로 옮겨집니다.

## 키트

- 켜기·끄기, 인터넷에 공개, 4가지 형식 내보내기·가져오기, 플러그인, 공동위키는 **관리판**에서 합니다.
- [애니위키 키트](https://github.com/iamtalker/anywiki-kit)
"""
FRONT_TITLE = {"opennamu": "FrontPage", "markdown": "FrontPage", "dokuwiki": "start", "mediawiki": "대문"}


def settings():
    for path in (SETTINGS, SETTINGS + ".bak"):
        try:
            s = json.load(open(path, encoding="utf-8"))
            if isinstance(s, dict):
                return s
        except (OSError, ValueError):
            pass
    return {}


def save_settings(s):
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    if os.path.exists(SETTINGS):
        try:
            shutil.copyfile(SETTINGS, SETTINGS + ".bak")
        except OSError:
            pass
    os.replace(tmp, SETTINGS)


def current():
    e = os.environ.get("ENGINE") or settings().get("engine") or "opennamu"
    return e if e in engines.ENGINES else "opennamu"


def migrate(root=ROOT):
    """0.1 의 wiki/ (openNAMU) 를 0.2 의 wikis/opennamu/ 로 옮긴다."""
    old, new = os.path.join(root, "wiki"), os.path.join(root, "wikis", "opennamu")
    if os.path.exists(os.path.join(old, "data.db")) and not os.path.exists(new):
        os.makedirs(os.path.dirname(new), exist_ok=True)
        os.replace(old, new)
        print("예전 위키 폴더(wiki/)를 wikis/opennamu/ 로 옮겼습니다", file=sys.stderr, flush=True)


def install(name, log=print):
    import wikiconv
    from engines.base import Page
    e = engines.get(name, ROOT)
    e.install(log)
    front = FRONT_TITLE[name]
    if name != "dokuwiki" and not e.get(front):
        text = wikiconv.convert(FRONT, "awm", e.syntax, front)
        e.put(Page(front, text, author="애니위키 키트", summary="첫 화면"))
        log("첫 화면 문서를 넣었습니다")
    log(f"{engines.NAMES[name]} 설치 완료")


def run_engine():
    e = engines.get(current(), ROOT)
    if not e.installed():
        raise SystemExit(f"{engines.NAMES[e.name]} 가 아직 설치되지 않았습니다: python scripts/kit.py install {e.name}")
    args, cwd, env = e.command()
    os.chdir(cwd)
    os.execvpe(args[0], args, env or os.environ)


def info():
    name = current()
    e = engines.get(name, ROOT)
    out = {"engine": name, "name": engines.NAMES[name], "installed": e.installed()}
    if e.installed():
        try:
            out["docs"] = e.count()
        except Exception as ex:  # 엔진 파일을 읽지 못해도 정보 보기는 된다
            out["docs_error"] = str(ex)
        out.update(e.info())
        if hasattr(e, "admin_password"):
            out["admin"] = e.admin_password()
    return out


def main():
    migrate()
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "install":
        name = sys.argv[2] if len(sys.argv) > 2 else current()
        t0 = time.time()
        install(name, lambda m: print(m, flush=True))
        s = settings()
        if not s.get("engine"):
            s["engine"] = name
            save_settings(s)
        print(f"완료 ({time.time() - t0:.0f}초)", flush=True)
    elif cmd == "run-engine":
        run_engine()
    elif cmd == "engine":
        if len(sys.argv) > 2:
            if sys.argv[2] not in engines.ENGINES:
                raise SystemExit(f"엔진: {', '.join(engines.ENGINES)}")
            s = settings()
            s["engine"] = sys.argv[2]
            save_settings(s)
        print(current())
    elif cmd == "info":
        print(json.dumps(info(), ensure_ascii=False, indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
