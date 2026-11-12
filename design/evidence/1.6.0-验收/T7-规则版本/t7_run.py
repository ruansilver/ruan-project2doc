"""T7 规则版本：脚本层面的实测。新建工程 + 无版本字段的旧工程副本。只写系统临时目录和 src/.work。"""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("D:/AI workspace/program/ruan-project2doc")
SCRIPT = ROOT / "src" / "ruan-project2doc" / "scripts" / "project2doc.py"
OUT = ROOT / "src" / ".work" / "1.6-验收" / "T7-规则版本"
OLD_SRC = Path("D:/AI workspace/claimYourPro/deepseek/ruan-project2doc/emg数据平台")  # 按 1.4 规则生成，只读
TMP = Path(sys.argv[1])


def run(*args):
    return subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def tree_hash(base: Path) -> dict:
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(base.rglob("*")) if p.is_file()}


log = []
if TMP.exists():
    shutil.rmtree(TMP)
TMP.mkdir(parents=True)

# 1. 新建工程
new = TMP / "demo-笔记工程"
r = run("scaffold", "--project", str(new), "--repo-name", "demo", "--json")
data = json.loads(r.stdout)
survey = (new / "笔记" / "_工作区" / "_勘察结果.md").read_text(encoding="utf-8")
task = (new / "需求包" / "00-任务说明.md").read_text(encoding="utf-8")
log.append("## 1. 新建工程（scaffold）")
log.append(f"- 退出码 {r.returncode}；JSON rules_version = {data['rules_version']}")
log.append(f"- _勘察结果.md 含版本行：{'| 规则版本 | ruan-project2doc 1.6.0 |' in survey}；残留占位符：{'{{规则版本}}' in survey}")
log.append(f"- 需求包/00-任务说明.md 含版本行：{'| 规则版本 | ruan-project2doc 1.6.0 |' in task}；残留占位符：{'{{规则版本}}' in task}")
rules = sorted(p.name for p in (new / "需求包" / "规则").glob("*.md"))
tpls = sorted(p.name for p in (new / "需求包" / "模板").glob("*.md"))
log.append(f"- 需求包/规则 {len(rules)} 份：{'、'.join(rules)}")
log.append(f"- 需求包/模板 {len(tpls)} 份：{'、'.join(tpls)}")
c = run("consistency", "--notes", str(new / "笔记"), "--json")
cd = json.loads(c.stdout)
log.append(f"- consistency：退出码 {c.returncode}；rules_version = {cd['rules_version']}；版本相关警告 = {[w for w in cd['warn'] if '规则版本' in w]}")
rr = subprocess.run([sys.executable, "-X", "utf8", str(new / "需求包" / "工具" / "project2doc.py"), "render-revise",
                     "--notes", str(new / "笔记"), "--repo-name", "demo", "--json"], capture_output=True, text=True, encoding="utf-8")
revise = (new / "笔记" / "修改已有笔记-demo.md").read_text(encoding="utf-8")
log.append(f"- 需求包内副本脚本独立运行 render-revise：退出码 {rr.returncode}；修改提示词含“规则版本：ruan-project2doc 1.6.0”：{'规则版本：ruan-project2doc 1.6.0' in revise}；残留 {{{{ 占位：{'{{' in revise}")
ver = subprocess.run([sys.executable, "-X", "utf8", str(new / "需求包" / "工具" / "project2doc.py"), "--version"],
                     capture_output=True, text=True, encoding="utf-8")
log.append(f"- 需求包内副本脚本 --version：{ver.stdout.strip()}")

# 需求包内文件间引用是否有效
missing = []
import re
for name in ("00-任务说明.md", "02-步骤拆分要求.md"):
    text = (new / "需求包" / name).read_text(encoding="utf-8")
    for ref in sorted(set(re.findall(r"(规则/[^\s，。；、）)]+?\.md|模板/[^\s，。；、）)]+?\.md)", text))):
        if not (new / "需求包" / ref).is_file():
            missing.append(f"{name} → {ref}")
log.append(f"- 需求包两份需求文件引用的 规则/、模板/ 路径不存在的：{missing or '无'}")
steps = (new / "需求包" / "02-步骤拆分要求.md").read_text(encoding="utf-8")
for needle in ["U-研读 NN", "U-成文 NN", "U-审读 NN", "U-收束", "讲述方案", "阶段 A", "阶段 B", "阶段 C", "等待用户确认第 NN 篇", "独立读者不得提前接触理解稿、源码和答案"]:
    log.append(f"  - 步骤拆分要求含“{needle}”：{needle in steps}")

# 2. 没有版本字段的旧工程副本
old = TMP / "旧工程副本-emg数据平台"
shutil.copytree(OLD_SRC, old, ignore=shutil.ignore_patterns(".git", "docs"))
before = tree_hash(old)
src_before = tree_hash(OLD_SRC / "需求包")
log.append("")
log.append("## 2. 没有版本字段的旧工程副本")
log.append(f"- 来源（只读）：{OLD_SRC}（按 1.4 规则生成）；副本 {len(before)} 个文件（不含 .git 与 docs）")
has_field = any("规则版本" in (old / rel).read_text(encoding="utf-8", errors="replace") for rel in ("笔记/_工作区/_勘察结果.md", "需求包/00-任务说明.md") if (old / rel).is_file())
log.append(f"- 旧工程的 _勘察结果.md / 00-任务说明.md 是否有“规则版本”字段：{has_field}")
c = run("consistency", "--notes", str(old / "笔记"), "--json")
cd = json.loads(c.stdout)
log.append(f"- consistency：退出码 {c.returncode}；rules_version = {cd['rules_version']}")
log.append(f"- 版本警告原文：{[w for w in cd['warn'] if '规则版本' in w]}")
log.append(f"- 其余失败 {len(cd['fail'])} 条（旧工程是 1.4 的交接物结构，不符合当前结构属预期；前 3 条：{cd['fail'][:3]}）")
after = tree_hash(old)
log.append(f"- consistency 之后副本文件是否改变：{'否' if before == after else '是'}")
rr = run("render-revise", "--notes", str(old / "笔记"), "--repo-name", "x-只读探测", "--json")
created = old / "笔记" / "修改已有笔记-x-只读探测.md"
if created.is_file():
    text = created.read_text(encoding="utf-8")
    found = re.search(r"规则版本：([^；\n]+)", text)
    log.append("- render-revise 在旧工程副本上新建的文档里，规则版本写的是：" + (found.group(1) if found else "（未找到）"))
    created.unlink()
log.append(f"- 清理探测文件后副本与复制时是否一致：{'是' if tree_hash(old) == before else '否'}")
log.append(f"- 用户原工程的需求包在测试前后是否一致：{'是' if tree_hash(OLD_SRC / '需求包') == src_before else '否'}")

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "脚本实测.md").write_text("# T7 规则版本：脚本实测\n\n" + "\n".join(log) + "\n", encoding="utf-8")
(OUT / "旧工程副本-文件哈希.json").write_text(json.dumps(before, ensure_ascii=False, indent=1), encoding="utf-8")
print("\n".join(log))
