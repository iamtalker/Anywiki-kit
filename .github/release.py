"""CHANGELOG.md 의 판마다 GitHub 릴리스를 만든다(이미 있으면 건너뜀). release.yml 이 부른다.

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

for i, s in enumerate(sections):
    tag = "v" + s["ver"]
    if run("gh", "release", "view", tag, check=False).returncode == 0:
        print(f"{tag}: 이미 있음")
        continue
    m = re.search(r"커밋 ([0-9a-f]{7,40})", s["rest"])
    ref = m.group(1) if m else ("HEAD" if i == 0 else None)
    if not ref:
        print(f"{tag}: 커밋이 적혀 있지 않아 건너뜀")
        continue
    sha = run("git", "rev-parse", ref + "^{commit}").stdout.strip()
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
        f.write("\n".join(s["body"]).strip() + "\n\n전체 변경 기록: CHANGELOG.md\n")
    args = ["gh", "release", "create", tag, "--target", sha, "--title", f"애니위키 키트 {s['ver']}", "--notes-file", f.name]
    if i != 0:
        args.append("--latest=false")
    run(*args)
    os.remove(f.name)
    print(f"{tag}: 만들었음 ({sha[:7]})")
