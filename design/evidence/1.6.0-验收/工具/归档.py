"""把 src/.work/1.6-验收 里有价值的验收依据归档到 design/evidence/1.6.0-验收。

分工见 验收记录.md 第 7 节：合成用例与通用记录入库；真实项目材料只留本机（本机留档（不入库）/，已被 .gitignore 忽略）。
每一项复制后立即核对文件数与内容哈希；任何一项不一致就停止，不做清理。本脚本不删除任何源文件。
"""
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path("D:/AI workspace/program/ruan-project2doc")
WORK = ROOT / "src" / ".work" / "1.6-验收"
DEST = ROOT / "design" / "evidence" / "1.6.0-验收"
LOCAL = DEST / "本机留档（不入库）" / "真实项目样篇"
READERS = WORK / "读者隔离区"

REAL = ("t1-", "t2-", "t3-", "t4-")          # 真实项目用例的子代理
T7_LOCAL = ["开工检查-过程.md", "开工说明-原话.md", "旧工程副本-文件哈希.json", "继续生成场景-复制时哈希.json"]
T7_REPO = ["T7-结论.md", "脚本实测.md", "t7_run.py", "继续生成场景-哈希核对.txt"]
TOOLS = ["执行约定.md", "prep_reader.py", "导出子代理提示词.py", "构建与校验.py", "安装三处.py", "发布前检索.py", "归档.py"]

# （源，目标）；目录整体复制，文件单个复制
PLAN = [
    (WORK / "规则修订记录.md", DEST / "规则修订记录.md"),
    (WORK / "回归", DEST / "回归"),
    (WORK / "T5-质量门负例", DEST / "T5-质量门负例"),
    (READERS / "T5-负例1-首轮", DEST / "T5-质量门负例" / "读者隔离区" / "T5-负例1-首轮"),
    (READERS / "T5-修复版1-复验", DEST / "T5-质量门负例" / "读者隔离区" / "T5-修复版1-复验"),
    (READERS / "T5-修复版3-复验", DEST / "T5-质量门负例" / "读者隔离区" / "T5-修复版3-复验"),
    (READERS / "_待发放" / "T5-负例1-首轮", DEST / "T5-质量门负例" / "读者隔离区" / "_待发放" / "T5-负例1-首轮"),
    (READERS / "_待发放" / "T5-修复版1-复验", DEST / "T5-质量门负例" / "读者隔离区" / "_待发放" / "T5-修复版1-复验"),
    (READERS / "_待发放" / "T5-修复版3-复验", DEST / "T5-质量门负例" / "读者隔离区" / "_待发放" / "T5-修复版3-复验"),
    (WORK / "T6-修改回归", DEST / "T6-修改回归"),
    (READERS / "T6-修改后-复验", DEST / "T6-修改回归" / "读者隔离区" / "T6-修改后-复验"),
    (READERS / "_待发放" / "T6-修改后-复验", DEST / "T6-修改回归" / "读者隔离区" / "_待发放" / "T6-修改后-复验"),
    # 真实项目：只留本机
    (WORK / "T1-nanyang-人员登录", LOCAL / "T1-nanyang-人员登录"),
    (WORK / "T2-nanyang-工位身份", LOCAL / "T2-nanyang-工位身份"),
    (WORK / "T3-EMG-缓存专题", LOCAL / "T3-EMG-缓存专题"),
    (WORK / "T4-EMG-规划期00", LOCAL / "T4-EMG-规划期00"),
    (READERS / "T1-首轮", LOCAL / "读者隔离区" / "T1-首轮"),
    (READERS / "T2-首轮", LOCAL / "读者隔离区" / "T2-首轮"),
    (READERS / "_待发放" / "T1-首轮", LOCAL / "读者隔离区" / "_待发放" / "T1-首轮"),
    (READERS / "_待发放" / "T2-首轮", LOCAL / "读者隔离区" / "_待发放" / "T2-首轮"),
]
PLAN += [(WORK / name, DEST / "工具" / name) for name in TOOLS]
PLAN += [(WORK / "T7-规则版本" / name, DEST / "T7-规则版本" / name) for name in T7_REPO]
PLAN += [(WORK / "T7-规则版本" / name, LOCAL / "T7-规则版本-本机部分" / name) for name in T7_LOCAL]
for path in sorted((WORK / "子代理提示词").glob("*.md")):
    if path.name == "README.md":
        continue
    target = (LOCAL / "子代理提示词-真实项目") if path.name.startswith(REAL) else (DEST / "子代理提示词")
    PLAN.append((path, target / path.name))


def digest(base: Path) -> dict:
    if base.is_file():
        return {"": hashlib.sha256(base.read_bytes()).hexdigest()}
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(base.rglob("*")) if p.is_file()}


missing = [str(src) for src, _ in PLAN if not src.exists()]
if missing:
    print("源不存在，停止：", *missing, sep="\n  ")
    sys.exit(1)
existing = [str(dst) for _, dst in PLAN if dst.exists()]
if existing:
    print("目标已存在，停止（不覆盖）：", *existing, sep="\n  ")
    sys.exit(1)

total = 0
for src, dst in PLAN:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        shutil.copy2(src, dst)
    before = {k: v for k, v in digest(src).items() if "__pycache__" not in k and not k.endswith(".pyc")}
    after = digest(dst)
    if before != after:
        print(f"核对不一致，停止：{src} -> {dst}")
        sys.exit(1)
    total += len(after)
    where = "本机留档" if LOCAL in dst.parents or dst == LOCAL else "入库"
    print(f"[{where}] {len(after):>3} 个文件  {src.relative_to(WORK).as_posix()}  ->  {dst.relative_to(DEST).as_posix()}")

print(f"\n归档完成并逐文件核对一致：{len(PLAN)} 项，{total} 个文件。源文件未删除。")
