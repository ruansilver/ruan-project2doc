"""为独立读者准备分阶段输入：冻结正文、生成骨架视图、暂存正文与题面。

用法：python -X utf8 prep_reader.py <正文路径> <轮次目录名> [题面路径]
- 隔离目录：读者隔离区/<轮次目录名>/，开始时只放 阶段A-骨架视图.md；
- 阶段 B、C 的输入先放在 读者隔离区/_待发放/<轮次目录名>/，轮到该阶段时再用 release 发放：
  python -X utf8 prep_reader.py --release <轮次目录名> B|C
"""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("D:/AI workspace/program/ruan-project2doc")
SCRIPT = ROOT / "src" / "ruan-project2doc" / "scripts" / "project2doc.py"
ISO = ROOT / "src" / ".work" / "1.6-验收" / "读者隔离区"

if sys.argv[1] == "--release":
    name, stage = sys.argv[2], sys.argv[3].upper()
    src = ISO / "_待发放" / name / {"B": "阶段B-正文.md", "C": "阶段C-题面.md"}[stage]
    dst = ISO / name / src.name
    shutil.copyfile(src, dst)
    print(f"已发放：{dst}")
    sys.exit(0)

body, name = Path(sys.argv[1]), sys.argv[2]
questions = Path(sys.argv[3]) if len(sys.argv) > 3 else None
iso, hold = ISO / name, ISO / "_待发放" / name
for d in (iso, hold):
    if d.exists():
        raise SystemExit(f"{d} 已存在，换一个轮次目录名（首次结果与复验结果要分开保留）")
    d.mkdir(parents=True)
r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), "skeleton", "--file", str(body),
                    "--out", str(iso / "阶段A-骨架视图.md")], capture_output=True, text=True, encoding="utf-8")
if r.returncode != 0:
    raise SystemExit(r.stderr)
shutil.copyfile(body, hold / "阶段B-正文.md")
if questions:
    shutil.copyfile(questions, hold / "阶段C-题面.md")
digest = hashlib.sha256(body.read_bytes()).hexdigest()
(iso.parent / "_待发放" / name / "冻结版本.txt").write_text(f"{body}\nsha256 {digest}\n", encoding="utf-8")
print(f"隔离目录：{iso}")
print(f"冻结正文：{body}")
print(f"sha256：{digest}")
print(f"骨架视图行数：{len((iso / '阶段A-骨架视图.md').read_text(encoding='utf-8').splitlines())}")
