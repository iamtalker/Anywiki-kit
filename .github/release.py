"""CHANGELOG.md 의 판마다 GitHub 릴리스를 만들고, 받을 파일(anywiki-kit-판.zip)을 붙인다. release.yml 이 부른다.
이미 있는 릴리스는 새로 만들지 않고, 받을 파일이 없으면 붙이기만 한다.

판 머리줄: `## 0.5 — 2026-09-29 (커밋 da8d611)`. 커밋이 적혀 있지 않은 판은 맨 위 판이면 지금 커밋으로 만들고,
아래 판이면 건너뛴다(새 판을 위에 덧붙일 때 바로 아래 판의 커밋을 적어 둔다).
"""
import os
import re
import subprocess
import tempfile

HEAD = re.compile(r"^## (\d+\.\d+(?:\.\d+)?) — (\S+)(.*)$")


def run(*a, check=True):
    return subprocess.run(a, capture_output=True, text=True, check=check)


text = open("CHANGELOG.md", encoding="utf-8").read()
sections, cur = [], None
for line in text.splitlines():
    m = HEAD.match(line)
    if m:
        cur = {"ver": m.group(1), "rest": m.group(3), "body": []}
        sections.append(cur)
    elif cur is not None:
        cur["body"].append(line)

HOWTO = """

## 받기
아래 **Assets** 의 `anywiki-kit-{ver}.zip` 을 받아 원하는 곳에 압축을 풉니다.
- Windows: 푼 폴더의 `애니위키.bat` 을 더블클릭 → 관리판이 열리면 '엔진' 칸에서 [설치].
- 리눅스: `bash server/install.sh opennamu` → `bash server/anywiki.sh start` (자세한 것은 README).
- 이전 판에서 올릴 때: 새 판을 기존 폴더에 덮어 풀면 됩니다(`wikis` 폴더는 그대로 둠).

전체 변경 기록: CHANGELOG.md
"""

for i, s in enumerate(sections):
    tag = "v" + s["ver"]
    asset = f"anywiki-kit-{s['ver']}.zip"
    view = run("gh", "release", "view", tag, "--json", "assets", "-q", ".assets[].name", check=False)
    exists = view.returncode == 0
    if exists and asset in view.stdout.split():
        print(f"{tag}: 이미 있음")
        continue
    m = re.search(r"커밋 ([0-9a-f]{7,40})", s["rest"])
    ref = m.group(1) if m else ("HEAD" if i == 0 else None)
    if exists:
        ref = tag  # 이미 있는 릴리스는 그 태그의 커밋으로 파일을 만든다
    if not ref:
        print(f"{tag}: 커밋이 적혀 있지 않아 건너뜀")
        continue
    sha = run("git", "rev-parse", ref + "^{commit}").stdout.strip()
    run("git", "archive", "--format=zip", "--prefix=anywiki-kit/", "-o", asset, sha)
    if exists:
        run("gh", "release", "upload", tag, asset, "--clobber")
        notes = run("gh", "release", "view", tag, "--json", "body", "-q", ".body").stdout
        if "## 받기" not in notes:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
                f.write(notes.replace("\n\n전체 변경 기록: CHANGELOG.md", "").rstrip() + HOWTO.format(ver=s["ver"]))
            run("gh", "release", "edit", tag, "--notes-file", f.name)
            os.remove(f.name)
        print(f"{tag}: 받을 파일을 붙였음")
        continue
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
        f.write("\n".join(s["body"]).strip() + HOWTO.format(ver=s["ver"]))
    args = ["gh", "release", "create", tag, asset, "--target", sha, "--title", f"애니위키 키트 {s['ver']}",
            "--notes-file", f.name]
    if i != 0:
        args.append("--latest=false")
    run(*args)
    os.remove(f.name)
    print(f"{tag}: 만들었음 ({sha[:7]})")
