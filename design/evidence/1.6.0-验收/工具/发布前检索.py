"""发布前核对：规则与模板之间的引用完整性，以及 R-001、R-013 要求的检索。只读。

用法：python -X utf8 发布前检索.py [Skill 根目录]   （默认 src/ruan-project2doc）
输出供人工判断：命中不等于不通过，要看它是禁止性表述、带来源说明的例子，还是正文规则。
"""
import re
import sys
from pathlib import Path

ROOT = Path("D:/AI workspace/program/ruan-project2doc")
SKILL = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "src" / "ruan-project2doc"

docs = [SKILL / "SKILL.md"] + sorted((SKILL / "references").glob("*.md")) + sorted((SKILL / "templates").glob("*.md"))
ref_names = {p.stem for p in (SKILL / "references").glob("*.md")}
tpl_names = {p.stem for p in (SKILL / "templates").glob("*.md")}

print(f"Skill 根：{SKILL}")
print(f"文件：SKILL.md + references {len(ref_names)} 份 + templates {len(tpl_names)} 份 + scripts {len(list((SKILL / 'scripts').glob('*')))} 个")

# 1. 《X》引用：X 必须是 references 或 templates 里的文件名
print("\n== 1. 《X》引用 ==")
unknown = {}
count = 0
for doc in docs:
    for no, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        for name in re.findall(r"《([^《》]+)》", line):
            count += 1
            if name not in ref_names and name not in tpl_names:
                unknown.setdefault(name, []).append(f"{doc.relative_to(SKILL).as_posix()}:{no}")
print(f"共 {count} 处引用；指向不存在文件的名称 {len(unknown)} 个")
for name, places in unknown.items():
    print(f"  《{name}》 <- {', '.join(places[:6])}")

# 2. SKILL.md 与其他文件里的相对链接
print("\n== 2. Markdown 相对链接 ==")
bad = []
links = 0
for doc in docs:
    for no, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", line):
            if re.match(r"[a-z]+://", target) or target.startswith("<"):
                continue
            links += 1
            if not (doc.parent / target).exists():
                bad.append(f"{doc.relative_to(SKILL).as_posix()}:{no} -> {target}")
print(f"共 {links} 处相对链接；失效 {len(bad)} 处")
for item in bad:
    print("  " + item)

# 3. R-001：取证格式与逐条检查编号体系
print("\n== 3. R-001 检索：一行一条的事实摘要、正文证据索引、逐条检查编号 ==")
patterns = [
    ("证据索引", re.compile(r"证据索引")),
    ("_事实 目录或事实摘要", re.compile(r"_事实|事实摘要|一行一条")),
    ("逐条检查编号（C-01 这类）", re.compile(r"\b[A-Z]{1,2}-\d{2,3}\b")),
    ("_校对记录 / _拆分方案（1.4 交接物）", re.compile(r"_校对记录|_拆分方案")),
]
for label, pattern in patterns:
    hits = []
    for doc in docs:
        for no, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                hits.append(f"  {doc.relative_to(SKILL).as_posix()}:{no}: {line.strip()[:110]}")
    print(f"-- {label}：{len(hits)} 处")
    for item in hits[:12]:
        print(item)

# 4. R-013：技术栈中立
print("\n== 4. R-013 检索：具体技术名（应只出现在标明来源的例子或线索表里）==")
tech = re.compile(r"Spring|Redis|MySQL|JWT|Kafka|RabbitMQ|MyBatis|React|Vue|Django|Flask|Kubernetes|Java\b|Python\b|Go\b|Rust\b|Node", re.I)
total = 0
for doc in docs:
    hits = [(no, line.strip()) for no, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1) if tech.search(line)]
    if hits:
        total += len(hits)
        print(f"-- {doc.relative_to(SKILL).as_posix()}：{len(hits)} 行")
        for no, line in hits[:8]:
            print(f"  {no}: {line[:120]}")
print(f"合计 {total} 行")

# 5. 补丁式写法
print("\n== 5. 补丁式写法检索（“原规则……现在补充”“相比 1.5”“新增要求”等）==")
patch = re.compile(r"原规则|现在补充|相比\s*1\.[0-9]|较\s*1\.[0-9]|新增要求|本版新增|1\.5\s*的做法|以前的版本")
hits = []
for doc in docs:
    for no, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        if patch.search(line):
            hits.append(f"  {doc.relative_to(SKILL).as_posix()}:{no}: {line.strip()[:110]}")
print(f"{len(hits)} 处")
for item in hits:
    print(item)
