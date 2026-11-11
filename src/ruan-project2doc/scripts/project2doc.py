#!/usr/bin/env python3
"""ruan-project2doc 的机械辅助脚本（只用标准库 + git）。

命令：
  deps           检查依赖（只读）
  survey         勘察源码仓与 project-map（只读）
  scaffold       建笔记工程骨架（只新建，不覆盖；写入规则版本）
  progress       核对步骤总览与笔记仓产物（只读）
  consistency    跨篇一致性检查（只读）
  lint           讲解与表达候选扫描（只读，命中只是线索）
  skeleton       输出骨架视图（只读；--out 另写一个文件）
  render-revise  生成修改提示词文档（只新建，不覆盖）

退出码：0 通过；1 存在失败项；2 参数或环境错误。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

SCRIPT = Path(__file__).resolve()
BASE = SCRIPT.parent.parent
VERSION = "1.6.0"
RULES_VERSION = f"ruan-project2doc {VERSION}"

SKIP_DIRS = {
    ".git", "node_modules", "target", "build", "dist", "out", ".venv", "venv", "__pycache__",
    ".idea", ".vscode", ".gradle", ".mvn", ".next", ".nuxt", "coverage", ".pytest_cache", "project-map",
}
BUILD_FILES = {
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "package.json",
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "go.mod", "Cargo.toml", "Gemfile",
    "composer.json", "Makefile", "CMakeLists.txt", "AndroidManifest.xml", "Dockerfile", "docker-compose.yml",
    "pubspec.yaml", "Package.swift", "mix.exs", "deno.json",
}
STATE_KEYS = ["梳理中模块数", "待验收模块数", "本层完成模块数", "已证叶子模块数", "待办数", "阻塞数", "入口数", "汇点数", "覆盖记录数"]
HEX = re.compile(r"(?<![0-9A-Za-z])([0-9a-f]{7,40})(?![0-9A-Za-z])")
SUPPLEMENT_LABELS = {"异常情况", "并发情况", "设计取舍", "版本演进", "当前局限"}
EDIT_PHRASES = ["修正补充", "代码核验说明", "此前理解有误", "重新确认后", "更正：", "更正:", "经核实后发现", "之前写错", "此前写错", "（已修正）"]
AI_WORDS = ["钉死", "拓扑", "抓手", "闭环", "赋能", "打通", "底层逻辑", "颗粒度", "兜底逻辑", "心智"]
SALES_TITLE = re.compile(r"^(必须|真正|关键是|只需要)")
TRANSITIONS = ["明确了", "回到正题", "接下来我们", "下面我们来看", "让我们", "综上所述", "值得注意的是", "需要注意的是", "如前所述", "不难看出"]
TAG_THRESHOLD = 5  # 默认值，可按项目口径调整。
NONCORE_PASS_RATIO = 0.8  # 默认值；脚本只核对审读者已经写下的判定。
SOURCE_LINE = re.compile(r"[\w./\\-]+\.[A-Za-z0-9]+(?::\d+(?:[-–]\d+)?|#L\d+(?:-L?\d+)?)")
TEST_NAME = re.compile(r"\b(?:[A-Z][A-Za-z0-9_]*(?:Tests?|Spec)|test_[A-Za-z0-9_]+|test[A-Z][A-Za-z0-9_]*|should[A-Z][A-Za-z0-9_]*)\b")
PROCESS_NOTE = re.compile(r"本次(?:均)?未运行|尚无真实容器证据|测试未执行|未跑(?:过)?测试|仅静态(?:核对|核查|分析)")
CROSS_REFERENCE = re.compile(r"(?:参见|详见|见|在)\s*第\s*\d{1,2}\s*篇")
# 1.6 新增信号；数值都是默认值，可按实测调整并把理由记入验收记录。
SUPPLEMENT_SPACING = 20  # 补充块平均间距低于这个行数时提示。
NAME_PARAGRAPH_LIMIT = 5  # 一个自然段里的反引号名称超过这个数时提示。
NAME_DENSITY_REFERENCE = 4.0  # 正文每 10 行的反引号名称参考线。
NEGATIVE_THRESHOLD = 6  # 否定限定句式的提示阈值。
LONG_SENTENCE_CHARS = 120  # 长并列句的字数。
LONG_SENTENCE_SEPARATORS = 3  # 长并列句的分号或顿号数。
COUNT_CLAIM = re.compile(r"(共有|共计|共|合计|总共|一共)?\s*(\d{1,4}|[一二两三四五六七八九十百千]+)\s*([项条步道类种处份组层个款])")
NEGATIVE_CLAUSE = re.compile(r"(?:不能|不可|不应|不宜|无法)[^，。；！？,;!?\n]{0,16}?(?:断言|认为|当作|当成|等同|概括|套用|推断|理解为|视为|看作)")
FIGURE_LANGS = ("mermaid", "plantuml", "puml", "dot", "graphviz")
FENCE_LINE = re.compile(r"^(```+|~~~+)\s*([A-Za-z0-9_-]*)")
IMG_LINE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
CN_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


# ---------- 基础 ----------

def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "core.quotepath=off", "-C", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def git_root(path: Path) -> Path | None:
    if not path.exists():
        return None
    r = git(path, "rev-parse", "--show-toplevel")
    return Path(r.stdout.strip()).resolve() if r.returncode == 0 else None


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def emit(data: dict, as_json: bool, text_lines: list[str]) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print("\n".join(text_lines))


def resource_dirs() -> tuple[Path, Path]:
    """返回 (references, templates)。脚本可能在 Skill 内，也可能在需求包/工具/ 下。"""
    if (BASE / "references").is_dir():
        return BASE / "references", BASE / "templates"
    if (BASE / "规则").is_dir():
        return BASE / "规则", BASE / "模板"
    raise SystemExit("找不到 references/ 或 规则/ 目录，脚本不在 Skill 或需求包内。")


def strip_code(text: str) -> list[tuple[int, str]]:
    """返回 (行号, 行)；跳过围栏代码块和 HTML 注释。"""
    out, fence, comment = [], False, False
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            continue
        if fence:
            continue
        if comment:
            if "-->" in s:
                comment = False
            continue
        if s.startswith("<!--"):
            comment = "-->" not in s
            continue
        out.append((i, line))
    return out


def md_tables(text: str) -> list[list[list[str]]]:
    """解析 Markdown 表格：返回 [表[行[单元格]]]，第一行是表头，分隔行已去掉。"""
    tables, current = [], []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and len(s) > 1:
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", s[1:-1])]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            current.append(cells)
        else:
            if current:
                tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def section(text: str, title_pattern: str) -> str:
    """取标题匹配 title_pattern 的那一节（到下一个同级或更高标题为止）。"""
    lines = text.splitlines()
    start, level = None, 0
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if not m:
            continue
        if start is None and re.search(title_pattern, m.group(2)):
            start, level = i, len(m.group(1))
        elif start is not None and len(m.group(1)) <= level:
            return "\n".join(lines[start:i])
    return "\n".join(lines[start:]) if start is not None else ""


def table_after(text: str, header_pattern: str) -> list[list[str]]:
    for t in md_tables(text):
        if t and re.search(header_pattern, " ".join(t[0])):
            return t
    return []


def col(table: list[list[str]], name_pattern: str) -> int | None:
    if not table:
        return None
    for i, h in enumerate(table[0]):
        if re.search(name_pattern, h):
            return i
    return None


def hashes_in(text: str) -> list[str]:
    seen: list[str] = []
    for h in HEX.findall(text):
        if re.search(r"[a-f]", h) and re.search(r"[0-9]", h) and h not in seen:
            seen.append(h)
    return seen


def cn_number(value: str) -> int | None:
    """解析中文数词或阿拉伯数字；解析不了返回 None。"""
    if value.isdigit():
        return int(value)
    total, current = 0, 0
    for ch in value:
        if ch in CN_DIGITS:
            current = CN_DIGITS[ch]
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
        elif ch == "百":
            total += (current or 1) * 100
            current = 0
        elif ch == "千":
            total += (current or 1) * 1000
            current = 0
        else:
            return None
    return total + current


def prose_paragraphs(text: str) -> list[tuple[int, str]]:
    """正文自然段：(起始行号, 段落文本)。不含标题、表格、代码块、注释和代码地图。
    空行、列表项和引用块切换都另起一段；连续行号中断（中间隔着代码块等）也另起一段。"""
    out: list[tuple[int, str]] = []
    cur: list[str] = []
    start, quote, last, in_map = 0, None, None, False

    def flush() -> None:
        nonlocal cur
        if cur:
            out.append((start, "\n".join(cur)))
            cur = []

    for no, line in strip_code(text):
        s = line.strip()
        heading = re.match(r"^(#{1,6})\s+(.*)$", s)
        if heading:
            flush()
            if re.search(r"代码地图", heading.group(2)):
                in_map = True
            elif len(heading.group(1)) <= 2:
                in_map = False
            continue
        if in_map or not s or s.startswith("|"):
            flush()
            continue
        is_quote = s.startswith(">")
        is_item = bool(re.match(r"^(?:>\s*)?(?:[-*+]|\d+[.、)])\s", s))
        if cur and (is_item or is_quote != quote or (last is not None and no != last + 1)):
            flush()
        if not cur:
            start, quote = no, is_quote
        cur.append(s)
        last = no
    flush()
    return out


def lint_extra_signals(text: str) -> dict:
    """G6-名称密集、G6-长并列句、G6-否定限定的统计；行号按原文。"""
    dense_paragraphs, long_sentences, negatives = [], [], []
    names, body_lines = 0, 0
    in_map = False
    for no, line in strip_code(text):
        s = line.strip()
        heading = re.match(r"^(#{1,6})\s+(.*)$", s)
        if heading:
            if re.search(r"代码地图", heading.group(2)):
                in_map = True
            elif len(heading.group(1)) <= 2:
                in_map = False
        if in_map or s.startswith("|"):
            continue
        body_lines += 1
        if not heading:
            names += len(re.findall(r"`[^`\n]+`", line))
        for match in NEGATIVE_CLAUSE.findall(line):
            negatives.append({"line": no, "match": match, "text": s[:160]})
    for start, para in prose_paragraphs(text):
        count = len(re.findall(r"`[^`\n]+`", para))
        if count > NAME_PARAGRAPH_LIMIT:
            dense_paragraphs.append({"line": start, "count": count, "text": para.replace("\n", " ")[:160]})
        for sentence in re.split(r"[。！？!?]", para):
            compact = re.sub(r"\s", "", sentence)
            separators = len(re.findall(r"[；;、]", sentence))
            if len(compact) > LONG_SENTENCE_CHARS and separators >= LONG_SENTENCE_SEPARATORS:
                long_sentences.append({"line": start, "chars": len(compact), "separators": separators,
                                       "text": sentence.strip()[:160]})
    density = round(names / body_lines * 10, 1) if body_lines else 0.0
    return {
        "name_density": {"names": names, "body_lines": body_lines, "per_10_lines": density,
                         "reference": NAME_DENSITY_REFERENCE,
                         "note": "行数含标题与空行，不含表格、代码块和代码地图；参考线是默认值。"},
        "dense_paragraphs": dense_paragraphs,
        "long_sentences": long_sentences,
        "negatives": negatives,
    }


def figure_blocks(text: str) -> list[dict]:
    """按行解析围栏图块：起点、终点、语言、是否有判断节点与虚线边。"""
    figures, fence, cur = [], None, None
    for idx, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if fence is None:
            m = FENCE_LINE.match(s) if s.startswith(("```", "~~~")) else None
            if m:
                fence = m.group(1)[0] * 3
                cur = {"start": idx, "lang": m.group(2).lower(), "lines": []}
        else:
            if s.startswith(fence):
                cur["end"] = idx
                figures.append(cur)
                fence, cur = None, None
            else:
                cur["lines"].append(line)
    for fig in figures:
        body = "\n".join(l for l in fig["lines"] if not l.strip().startswith("%%"))
        lang = fig["lang"]
        first = (fig["lines"][0].strip() if fig["lines"] else "")
        if lang in ("mermaid", ""):
            if re.match(r"sequenceDiagram", first):
                fig["has_dashed"] = bool(re.search(r"-->>|--x|--\)|-->", body))
                fig["has_decision"] = bool(re.search(r"^\s*(alt|opt|else)\b", body, re.M))
            else:
                fig["has_decision"] = bool(re.search(r"\{[^{}\n]+\}", body) or "<<choice>>" in body)
                fig["has_dashed"] = bool(re.search(r"-\.->|-\.-|-\.\s|\.->", body))
        elif lang in ("plantuml", "puml"):
            fig["has_decision"] = bool(re.search(r"\bif\s*\(|\belse\b", body))
            fig["has_dashed"] = bool(re.search(r"\.\.>|-\[dashed\]", body))
        else:
            fig["has_decision"] = bool(re.search(r"\{[^{}\n]+\}|\bif\s*\(", body))
            fig["has_dashed"] = bool(re.search(r"-\.->|\.\.>|dashed", body))
    return figures


def figure_legend_hits(text: str) -> list[dict]:
    """G3-图例不符：图后文字提到“菱形”而图里没有判断节点，提到“虚线”而图里没有虚线边。"""
    hits: list[dict] = []
    lines = text.splitlines()
    for fig in figure_blocks(text):
        for idx in range(fig["end"] + 1, min(fig["end"] + 15, len(lines)) + 1):
            s = lines[idx - 1]
            if re.match(r"^\s*#{1,6}\s", s) or s.strip().startswith(("```", "~~~")):
                break
            if "菱形" in s and not fig["has_decision"]:
                hits.append({"line": idx, "match": "菱形；图里没有判断节点", "text": s.strip()[:160]})
            if "虚线" in s and not fig["has_dashed"]:
                hits.append({"line": idx, "match": "虚线；图里没有虚线边", "text": s.strip()[:160]})
    return hits


def parse_headings(text: str) -> list[tuple[int, int, str]]:
    """(0 基行号, 级别, 标题)；跳过围栏代码块。"""
    headings, fence = [], None
    for i, line in enumerate(text.splitlines()):
        s = line.strip()
        if fence:
            if s.startswith(fence):
                fence = None
            continue
        if s.startswith(("```", "~~~")):
            fence = s[:3]
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            headings.append((i, len(m.group(1)), m.group(2).strip()))
    return headings


def first_paragraph_after(lines: list[str], start: int, stop: int) -> str | None:
    """标题后的第一个自然段（0 基行号区间 [start, stop)）；遇下级标题或没有正文返回 None。"""
    i = start
    while i < stop:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if re.match(r"^#{1,6}\s", s):
            return None
        if s.startswith(("```", "~~~")):
            fence = s[:3]
            i += 1
            while i < stop and not lines[i].strip().startswith(fence):
                i += 1
            i += 1
            continue
        if s.startswith("<!--"):
            while i < stop and "-->" not in lines[i]:
                i += 1
            i += 1
            continue
        if s.startswith("|"):
            while i < stop and lines[i].strip().startswith("|"):
                i += 1
            continue
        block: list[str] = []
        while i < stop:
            s = lines[i].strip()
            if not s or re.match(r"^#{1,6}\s", s) or s.startswith(("```", "~~~")):
                break
            block.append(s)
            i += 1
            if len(block) >= 10:
                block.append("……")
                break
        return "\n".join(block) if block else None
    return None


def narrative_plan_problem(section_text: str) -> str | None:
    """讲述方案区块的非空检查；返回问题描述或 None。"""
    body = "\n".join(section_text.splitlines()[1:])
    walk = re.search(r"全流程走查[：:]\s*(.*)", body)
    if walk is not None:
        if not filled(walk.group(1)):
            return "的“全流程走查”未填写"
        org = re.search(r"组织方式(?:与理由)?[：:]\s*(.*)", body)
        if org and not filled(org.group(1)):
            return "的“组织方式与理由”未填写"
        return None
    stripped = re.sub(r"<[^<>\n]*>", "", body)
    stripped = re.sub(r"[\s|:\-—]", "", stripped)
    return None if len(stripped) >= 20 else "为空或仍是模板占位"


def block_has_content(section_text: str) -> bool:
    """区块（去掉标题行、占位符与表格符）是否留有实际内容。"""
    body = "\n".join(section_text.splitlines()[1:])
    body = re.sub(r"<[^<>\n]*>", "", body)
    body = re.sub(r"[\s|:\-—#]", "", body)
    return len(body) >= 10


def rules_version_of(text: str) -> str | None:
    """从文本里取“规则版本”字段；缺失或仍是占位符时返回 None。"""
    m = re.search(r"规则版本\s*[|：:]\s*([^|\n]+)", text)
    if not m:
        return None
    value = m.group(1).strip().strip("`").strip()
    if not value or re.fullmatch(r"\{\{.*?\}\}|<[^>]+>", value):
        return None
    return value


def skill_roots(extra: list[str]) -> list[Path]:
    home = Path.home()
    roots = [Path(p) for p in extra]
    roots += [Path.cwd() / ".claude" / "skills", home / ".claude" / "skills", home / ".agents" / "skills",
              home / ".dsh" / "skills", home / ".codex" / "skills"]
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        roots.insert(0, Path(os.environ["CLAUDE_CONFIG_DIR"]) / "skills")
    return [r for r in roots if r.is_dir()]


def find_skill(name: str, roots: list[Path]) -> Path | None:
    for r in roots:
        if (r / name / "SKILL.md").is_file():
            return (r / name).resolve()
    return None


# ---------- deps ----------

def cmd_deps(a: argparse.Namespace) -> int:
    roots = skill_roots(a.skills_dir or [])
    g = subprocess.run(["git", "--version"], capture_output=True, text=True) if shutil.which("git") else None
    dev = find_skill("ruan-dev-skills", roots)
    dev_version = None
    if dev:
        m = re.search(r"Ruan Dev Skills\s+([0-9.]+)", read(dev / "SKILL.md"))
        dev_version = m.group(1) if m else "未知"
    reader = find_skill("ruan-project-reader", roots)
    check_py = reader / "scripts" / "check.py" if reader and (reader / "scripts" / "check.py").is_file() else None
    plain = next((find_skill(n, roots) for n in ("shuorenhua",) if find_skill(n, roots)), None)
    data = {
        "python": sys.version.split()[0],
        "python_ok_for_reader_check": sys.version_info >= (3, 10),
        "git": g.stdout.strip() if g and g.returncode == 0 else None,
        "ruan_dev_skills": str(dev) if dev else None,
        "ruan_dev_skills_version": dev_version,
        "reader_check_py": str(check_py) if check_py else None,
        "plain_language_skill": str(plain) if plain else None,
        "skill_roots_scanned": [str(r) for r in roots],
    }
    problems = []
    if not data["git"]:
        problems.append("没有 Git：停止。")
    if not dev:
        problems.append("ruan-dev-skills 未安装：停止，提示用户先安装（硬依赖，不提供降级编排）。")
    elif dev_version and dev_version != "未知" and not dev_version.startswith("2."):
        problems.append(f"ruan-dev-skills 版本是 {dev_version}，本 Skill 按 2.0 设计，请人工确认兼容。")
    data["problems"] = problems
    lines = [
        f"Python：{data['python']}（reader check.py 需要 3.10+：{'满足' if data['python_ok_for_reader_check'] else '不满足'}）",
        f"Git：{data['git'] or '未找到'}",
        f"ruan-dev-skills：{data['ruan_dev_skills'] or '未安装'}" + (f"（版本 {dev_version}）" if dev_version else ""),
        f"ruan-project-reader check.py：{data['reader_check_py'] or '未找到（有 map 时改为人工检查）'}",
        f"“说人话”类 Skill：{data['plain_language_skill'] or '未找到'}",
    ] + [f"问题：{p}" for p in problems]
    emit(data, a.json, lines)
    return 1 if (not data["git"] or not dev) else 0


# ---------- survey ----------

def git_roots_near(paths: list[Path], depth: int = 2) -> list[Path]:
    """base 自身是 Git 根，或 base 下没有嵌套仓库时，取 base 所在的仓库；否则取 base 下（深度 depth 内）的各个仓库。"""
    found: list[Path] = []
    for base in paths:
        if not base.is_dir():
            continue
        r = git_root(base)
        if r == base.resolve():
            if r not in found:
                found.append(r)
            continue
        nested = git_roots_below(base, depth)
        for n in nested or ([r] if r else []):
            if n not in found:
                found.append(n)
    return found


def git_roots_below(base: Path, depth: int) -> list[Path]:
    found: list[Path] = []
    if True:
        frontier = [base]
        for _ in range(depth):
            nxt = []
            for d in frontier:
                try:
                    children = [c for c in d.iterdir() if c.is_dir() and c.name not in SKIP_DIRS and not c.name.startswith(".")]
                except OSError:
                    continue
                for c in children:
                    if (c / ".git").exists():
                        rc = c.resolve()
                        if rc not in found:
                            found.append(rc)
                    else:
                        nxt.append(c)
            frontier = nxt
    return found


def repo_info(root: Path) -> dict:
    head = git(root, "rev-parse", "HEAD")
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    status = git(root, "status", "--porcelain")
    log = git(root, "log", "-1", "--format=%H %cs %s")
    return {
        "path": str(root),
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "branch": branch.stdout.strip() if branch.returncode == 0 else None,
        "dirty_paths": status.stdout.splitlines()[:50],
        "dirty_count": len(status.stdout.splitlines()),
        "last_commit": log.stdout.strip(),
    }


def scale(root: Path) -> dict:
    exts: dict[str, int] = {}
    builds: list[str] = []
    total = 0
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
        for f in files:
            total += 1
            ext = Path(f).suffix.lower() or "(无扩展名)"
            exts[ext] = exts.get(ext, 0) + 1
            if f in BUILD_FILES or f.endswith(".csproj") or f.endswith(".sln"):
                builds.append(Path(d, f).relative_to(root).as_posix())
    top = sorted(exts.items(), key=lambda kv: -kv[1])[:12]
    return {"total_files": total, "top_extensions": top, "build_files": sorted(builds)[:60]}


def find_map(repo: Path, explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).resolve()
        return p if p.is_dir() else None
    for c in (repo / "project-map", repo.parent / "project-map", repo.parent.parent / "project-map"):
        if (c / "STATE.md").is_file() or (c / "COVERAGE.md").is_file():
            return c.resolve()
    return None


def map_status(m: Path) -> dict:
    state_text = read(m / "STATE.md")
    stats = {}
    for k in STATE_KEYS:
        mm = re.search(rf"^{k}[：:]\s*(.+)$", state_text, re.M)
        stats[k] = mm.group(1).strip() if mm else None
    spec = re.search(r"^规范版本[：:]\s*(.+)$", state_text, re.M)
    cov = read(m / "COVERAGE.md")
    conv = re.search(r"本轮发现暂时收敛[：:]\s*(\S+)", cov)
    done = re.search(r"本轮范围整体完成[：:]\s*(\S+)", cov)
    modules = []
    for f in sorted((m / "modules").glob("*.md")) if (m / "modules").is_dir() else []:
        head = read(f).splitlines()[:12]
        st = next((re.sub(r"^状态[：:]\s*", "", x).strip() for x in head if re.match(r"^状态[：:]", x)), None)
        lim = next((re.sub(r"^限制[：:]\s*", "", x).strip() for x in head if re.match(r"^限制[：:]", x)), None)
        modules.append({"file": f.name, "status": st, "limit": lim})
    head_text = base_lines(read(m / "README.md").splitlines()[:30] + cov.splitlines()[:30])
    return {
        "path": str(m),
        "spec_version": spec.group(1).strip() if spec else None,
        "state": stats,
        "discovery_converged": conv.group(1) if conv else None,
        "scope_complete": done.group(1) if done else None,
        "modules": modules,
        "base_candidates": hashes_in(head_text),
    }


def base_lines(lines: list[str]) -> str:
    """只取说明源码基准的行：含“基准/提交/commit/HEAD/@”，或紧跟在“源码基准：”这类以冒号结尾的行之后；排除指纹行。"""
    keep, window = [], 0
    for ln in lines:
        s = ln.strip()
        if re.search(r"指纹|fingerprint|sha256|SHA-256", s, re.I):
            window = max(0, window - 1)
            continue
        if re.search(r"基准|提交|commit|HEAD|@", s, re.I):
            keep.append(s)
            window = 3 if re.search(r"[：:]\s*$", s) else 0
        elif window and s:
            keep.append(s)
            window -= 1
    return "\n".join(keep)


def compare_base(base: str, repos: list[Path]) -> dict:
    for r in repos:
        if git(r, "cat-file", "-e", f"{base}^{{commit}}").returncode != 0:
            continue
        head = git(r, "rev-parse", "HEAD").stdout.strip()
        full = git(r, "rev-parse", base).stdout.strip()
        if head == full:
            return {"base": base, "repo": str(r), "head": head, "same": True, "behind": 0, "changed_files": []}
        behind = git(r, "rev-list", "--count", f"{full}..HEAD").stdout.strip()
        names = git(r, "diff", "--name-only", full, "HEAD").stdout.splitlines()
        return {"base": base, "repo": str(r), "head": head, "same": False,
                "behind": int(behind) if behind.isdigit() else None, "changed_files": names}
    return {"base": base, "repo": None, "found": False}


def run_reader_check(m: Path, check_py: Path | None) -> dict:
    if not check_py:
        return {"ran": False, "reason": "未找到 ruan-project-reader 的 check.py"}
    if sys.version_info < (3, 10):
        return {"ran": False, "reason": "check.py 需要 Python 3.10+"}
    try:
        r = subprocess.run([sys.executable, str(check_py), str(m)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ran": False, "reason": f"运行失败：{exc}"}
    tail = (r.stdout + r.stderr).strip().splitlines()[-15:]
    return {"ran": True, "exit_code": r.returncode, "tail": tail}


def cmd_survey(a: argparse.Namespace) -> int:
    repo = Path(a.repo).resolve()
    if not repo.is_dir():
        print(f"仓库路径不存在：{repo}", file=sys.stderr)
        return 2
    repos = git_roots_near([repo], depth=2)
    m = find_map(repo, a.map)
    data: dict = {"repo": str(repo), "git_repos": [repo_info(r) for r in repos], "scale": scale(repo), "project_map": None}
    lines = [f"# 勘察：{repo}", ""]
    if not repos:
        lines.append("警告：仓库路径下没有找到 Git 仓库，无法记录源码基准。")
    for info in data["git_repos"]:
        lines.append(f"- Git：{info['path']} @ {info['head']}（{info['branch']}；未提交路径 {info['dirty_count']} 个）")
    sc = data["scale"]
    lines += ["", f"文件总数（已跳过构建与依赖目录）：{sc['total_files']}",
              "主要扩展名：" + "，".join(f"{e} {n}" for e, n in sc["top_extensions"]),
              "构建文件：" + ("，".join(sc["build_files"][:20]) or "未发现")]
    if not m:
        lines += ["", "project-map：未找到（依次查了 <仓库>/project-map、同级目录、父目录）。走自带路径，提示一句可以先跑 ruan-project-reader。"]
        emit(data, a.json, lines)
        return 0
    ms = map_status(m)
    search_repos = git_roots_near([repo, m.parent], depth=2)
    compares, seen_full = [], set()
    for h in ms["base_candidates"]:
        c = compare_base(h, search_repos)
        key = (c.get("repo"), git(Path(c["repo"]), "rev-parse", h).stdout.strip()) if c.get("repo") else None
        if key and key in seen_full:
            continue
        if key:
            seen_full.add(key)
        compares.append(c)
    ms["base_compare"] = compares
    roots = skill_roots(a.skills_dir or [])
    reader = find_skill("ruan-project-reader", roots)
    check_py = Path(a.reader_check) if a.reader_check else (reader / "scripts" / "check.py" if reader else None)
    ms["check"] = run_reader_check(m, check_py if check_py and check_py.is_file() else None) if not a.no_check else {"ran": False, "reason": "--no-check"}
    data["project_map"] = ms
    lines += ["", f"project-map：{m}（规范版本 {ms['spec_version'] or '未写'}）",
              "STATE：" + "，".join(f"{k} {v}" for k, v in ms["state"].items()),
              f"本轮发现暂时收敛：{ms['discovery_converged']}；本轮范围整体完成：{ms['scope_complete']}",
              "模块："]
    for mod in ms["modules"]:
        lines.append(f"  - {mod['file']}：状态 {mod['status']}；限制 {mod['limit']}")
    lines.append("基准比对：")
    if not ms["base_compare"]:
        lines.append("  - 在 README.md / COVERAGE.md 前 30 行没有找到提交号：基准未知，借鉴事实一律按“必须核对”对待。")
    for c in ms["base_compare"]:
        if c.get("repo") is None:
            lines.append(f"  - {c['base']}：在附近的 Git 仓库里找不到这个提交（可能不是提交号，或仓库不在本机）")
        elif c["same"]:
            lines.append(f"  - {c['base']}：{c['repo']} 当前 HEAD 一致")
        else:
            lines.append(f"  - {c['base']}：{c['repo']} 当前 HEAD {c['head'][:12]}，落后 {c['behind']} 个提交，{len(c['changed_files'])} 个文件有变化")
            for n in c["changed_files"][:40]:
                lines.append(f"      {n}")
            if len(c["changed_files"]) > 40:
                lines.append(f"      ……其余 {len(c['changed_files']) - 40} 个见 --json")
    ck = ms["check"]
    lines.append(f"check.py：{'退出码 ' + str(ck['exit_code']) if ck.get('ran') else '未执行：' + ck.get('reason', '')}")
    if ck.get("ran") and ck["exit_code"] != 0:
        lines += ["  " + t for t in ck["tail"]]
        lines.append("  注意：退出码 1 不等于放弃借鉴，只降低失败项牵涉模块的信任。")
    emit(data, a.json, lines)
    return 0


# ---------- scaffold ----------

def copy_new(src: Path, dst: Path, created: list[str], skipped: list[str]) -> None:
    if dst.exists():
        skipped.append(str(dst))
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    created.append(str(dst))


def cmd_scaffold(a: argparse.Namespace) -> int:
    proj = Path(a.project).resolve()
    probe = proj
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    outer = git_root(probe)
    if outer and outer != (proj / "笔记").resolve():
        print(f"笔记工程目录位于 Git 仓库 {outer} 之内。资料仓和笔记仓都必须是独立 Git 根，请换一个不在任何 Git 仓库里的位置。", file=sys.stderr)
        return 2
    refs, tpls = resource_dirs()
    created: list[str] = []
    skipped: list[str] = []
    notes = proj / "笔记"
    notes.mkdir(parents=True, exist_ok=True)
    if git_root(notes) != notes.resolve():
        r = git(notes, "init")
        if r.returncode != 0:
            print(f"git init 失败：{r.stderr}", file=sys.stderr)
            return 2
        created.append(f"{notes}（git init）")
    for name in ("00-系统总览与阅读路线.md", "99-复核说明.md"):
        copy_new(tpls / name, notes / name, created, skipped)
    for name in ("_勘察结果.md", "_规划方案.md", "_术语表.md", "_衔接约定.md", "_问题台账.md"):
        copy_new(tpls / name, notes / "_工作区" / name, created, skipped)
    for name in ("_研读", "_审读记录"):
        directory = notes / "_工作区" / name
        if not directory.exists():
            directory.mkdir(parents=True)
            created.append(str(directory))
    pack = proj / "需求包"
    copy_new(tpls / "需求包-00-任务说明.md", pack / "00-任务说明.md", created, skipped)
    copy_new(tpls / "需求包-02-步骤拆分要求.md", pack / "02-步骤拆分要求.md", created, skipped)
    for f in sorted(refs.glob("*.md")):
        copy_new(f, pack / "规则" / f.name, created, skipped)
    for f in sorted(tpls.glob("*.md")):
        if not f.name.startswith("需求包-"):
            copy_new(f, pack / "模板" / f.name, created, skipped)
    copy_new(SCRIPT, pack / "工具" / "project2doc.py", created, skipped)
    # 规则版本只写进本次新建的文件；已有文件不动，工程始终使用它归档的那一版规则。
    for target in (notes / "_工作区" / "_勘察结果.md", pack / "00-任务说明.md"):
        if str(target) in created:
            body = read(target)
            if "{{规则版本}}" in body:
                with target.open("w", encoding="utf-8", newline="\n") as stream:
                    stream.write(body.replace("{{规则版本}}", RULES_VERSION))
    data = {"project": str(proj), "repo_name": a.repo_name, "rules_version": RULES_VERSION,
            "created": created, "skipped_existing": skipped}
    lines = [f"笔记工程：{proj}", f"规则版本：{RULES_VERSION}（写入新建的 _勘察结果.md 与 00-任务说明.md）",
             f"新建 {len(created)} 项，已存在而跳过 {len(skipped)} 项。"] + [f"  + {c}" for c in created] + [f"  = {s}" for s in skipped]
    lines.append("下一步：U-勘察，填写 笔记/_工作区/_勘察结果.md。资料仓 docs/AI dev docs/ 由 ruan-dev-skills 初始化时创建。")
    emit(data, a.json, lines)
    return 0


# ---------- 篇目工具 ----------

def note_files(notes: Path) -> dict[str, Path]:
    out = {}
    for f in sorted(notes.glob("*.md")):
        m = re.match(r"^(\d{2})-", f.name)
        if m:
            out.setdefault(m.group(1), f)
    return out


def planned_articles(notes: Path) -> list[str]:
    text = read(notes / "_工作区" / "_规划方案.md")
    t = table_after(section(text, r"篇目") or text, r"篇号")
    nums = []
    for row in t[1:]:
        m = re.match(r"^\D*(\d{1,2})\b", row[0]) if row else None
        if m:
            nums.append(f"{int(m.group(1)):02d}")
    return nums


def article_nums_in_00(notes: Path) -> list[str]:
    files = note_files(notes)
    f = files.get("00")
    if not f:
        return []
    t = table_after(section(read(f), r"篇目") or read(f), r"篇号")
    out = []
    for row in t[1:]:
        m = re.match(r"^\D*(\d{1,2})\b", row[0]) if row else None
        if m:
            out.append(f"{int(m.group(1)):02d}")
    return out


# ---------- progress ----------

def cmd_progress(a: argparse.Namespace) -> int:
    notes, vdir = Path(a.notes).resolve(), Path(a.version_dir).resolve()
    fails, warns, ok = [], [], []
    if git_root(notes) != notes:
        fails.append(f"笔记仓不是独立 Git 根：{notes}")
    overview = read(vdir / "步骤总览.md")
    if not overview:
        fails.append(f"找不到 {vdir / '步骤总览.md'}")
    done_lines = [ln for ln in overview.splitlines() if re.search(r"\bS\d{3}\b", ln) and "已完成" in ln]
    files = note_files(notes)
    work = notes / "_工作区"
    for ln in done_lines:
        sid = re.search(r"\b(S\d{3})\b", ln).group(1)
        hs = hashes_in(ln)
        if not hs:
            warns.append(f"{sid} 标为已完成，但这一行没有提交 hash（可能记在步骤文件里，请人工核对）")
        for h in hs:
            if git(notes, "cat-file", "-e", f"{h}^{{commit}}").returncode == 0:
                ok.append(f"{sid}：提交 {h} 在笔记仓中")
            else:
                fails.append(f"{sid}：提交 {h} 不在笔记仓中")
        kind = re.search(r"(研读|成文|审读|收束)", ln)
        num = re.search(r"(?<!\d)(\d{2})(?!\d)", ln[kind.end():]) if kind and kind.group(1) != "收束" else None
        if kind and kind.group(1) == "收束":
            for need in ("00", "99"):
                if need not in files:
                    fails.append(f"{sid} 收束已完成，但缺少 {need}-*.md")
            if not list(notes.glob("修改已有笔记-*.md")):
                fails.append(f"{sid} 收束已完成，但缺少 修改已有笔记-*.md")
        elif kind and num:
            nn = num.group(1)
            need = {"研读": work / "_研读" / f"{nn}.md", "成文": files.get(nn), "审读": work / "_审读记录" / f"{nn}.md"}[kind.group(1)]
            if not need or not Path(need).is_file():
                fails.append(f"{sid}（{kind.group(1)} {nn}）已完成，但产物不存在")
            else:
                ok.append(f"{sid}（{kind.group(1)} {nn}）产物存在")
        elif sid != "S001":
            warns.append(f"{sid} 已完成，但无法从这一行自动判断单元类型和篇号，请人工核对产物")
    state = read(vdir / "当前状态.md")
    m = re.search(r"上一步代码 checkpoint[：:]\s*(.+)", state)
    if m:
        for h in hashes_in(m.group(1)):
            if git(notes, "cat-file", "-e", f"{h}^{{commit}}").returncode != 0:
                fails.append(f"《当前状态》的上一步 checkpoint {h} 不在笔记仓中")
    for nn in planned_articles(notes):
        have = [n for n, p in (("理解稿", work / "_研读" / f"{nn}.md"), ("正文", files.get(nn)), ("审读", work / "_审读记录" / f"{nn}.md")) if p and Path(p).is_file()]
        ok.append(f"第 {nn} 篇现有产物：{'、'.join(have) or '无'}")
    data = {"notes": str(notes), "version_dir": str(vdir), "fail": fails, "warn": warns, "ok": ok}
    lines = [f"失败 {len(fails)}，警告 {len(warns)}"] + [f"FAIL {x}" for x in fails] + [f"WARN {x}" for x in warns] + [f"OK   {x}" for x in ok]
    emit(data, a.json, lines)
    return 1 if fails else 0


# ---------- consistency ----------

def code_names(text: str) -> set[str]:
    names = set()
    for _, line in strip_code(text):
        for n in re.findall(r"`([^`\n]{2,80})`", line):
            names.add(n.strip())
    return names


def article_number(value: str) -> str | None:
    match = re.search(r"(?<!\d)(\d{1,2})(?!\d)", value)
    return f"{int(match.group(1)):02d}" if match else None


def cell(row: list[str], index: int | None) -> str:
    return re.sub(r"[`*]", "", row[index]).strip() if index is not None and index < len(row) else ""


def filled(value: str) -> bool:
    value = value.strip()
    return bool(value and value not in {"-", "—", "待填", "待确认", "待核对", "待审读"}
                and not re.fullmatch(r"<[^>]+>|\{\{.*?\}\}", value))


def planned_questions(text: str) -> dict[str, dict[str, dict]]:
    questions: dict[str, dict[str, dict]] = {}
    for table in md_tables(text):
        qi, ni = col(table, r"题号|追问编号"), col(table, r"^篇号")
        pi, ci = col(table, r"^问题$|^追问$"), col(table, r"核心题")
        bi = col(table, r"^必答")
        if None in (qi, ni, pi):
            continue
        for row in table[1:]:
            number, qid = article_number(cell(row, ni)), cell(row, qi)
            if number and filled(qid):
                yes = r"^(是|核心|必答|yes|true)$"
                questions.setdefault(number, {})[qid] = {
                    "question": cell(row, pi),
                    # 必答题（整体复述、子流程复述、用户指定）与核心题同样要求全部答得出且正确。
                    "core": bool(re.search(yes, cell(row, ci), re.I) or re.search(yes, cell(row, bi), re.I)),
                }
    return questions


def check_review(text: str, expected: dict[str, dict]) -> list[str]:
    """核对审读记录是否齐全；正确性由审读者回源码判断，本函数不判语义。"""
    problems = []
    for label, pattern in (("阶段 A（骨架复述）", r"阶段\s*A|骨架复述"),
                           ("阶段 B（通读复述与初读障碍）", r"阶段\s*B|通读复述"),
                           ("阶段 C（逐题作答）", r"阶段\s*C|逐题作答")):
        block = section(text, pattern)
        if not block:
            problems.append(f"缺少{label}区块")
        elif label != "阶段 C（逐题作答）" and not block_has_content(block):
            problems.append(f"{label}区块没有保留原答内容")
    answers: dict[str, dict] = {}
    for table in md_tables(text):
        qi, ji = col(table, r"题号|追问编号"), col(table, r"^判定")
        ai, si, vi = col(table, r"答案"), col(table, r"正文出处"), col(table, r"核对")
        if qi is None or ji is None:
            continue
        for row in table[1:]:
            qid = cell(row, qi)
            if not filled(qid):
                continue
            if qid in answers:
                problems.append(f"G1 题号重复：{qid}")
            answer, source, verified = cell(row, ai), cell(row, si), cell(row, vi)
            judgement = cell(row, ji)
            if not all(filled(v) for v in (answer, source, verified)):
                problems.append(f"G1 {qid} 缺答案、正文出处或正确性核对")
            if judgement not in {"答得出", "部分", "答不出"}:
                problems.append(f"G1 {qid} 判定应为 答得出/部分/答不出")
            # 只读开头的核对结论；后面的业务说明可能包含“错误密码”等正常描述。
            correct = bool(re.match(r"^(?:正确|一致|核对无误)(?=$|[\s；;，,。.!！?？：:（(])", verified))
            answers[qid] = {"answered": judgement == "答得出", "correct": correct}
    if not answers:
        problems.append("缺少 G1 逐题作答表")
    for qid, question in expected.items():
        result = answers.get(qid)
        if result is None:
            problems.append(f"G1 漏了规划中的追问 {qid}")
        elif question["core"] and not (result["answered"] and result["correct"]):
            problems.append(f"G1 核心题 {qid} 尚未记录为答得出且正确")
    other = [qid for qid, question in expected.items() if not question["core"]]
    passed = sum(1 for qid in other if answers.get(qid, {}).get("answered") and answers[qid]["correct"])
    if other and passed / len(other) < NONCORE_PASS_RATIO:
        problems.append(f"G1 其余题目答得出且正确 {passed}/{len(other)}，低于默认 {NONCORE_PASS_RATIO:.0%}")
    gates = {}
    for table in md_tables(text):
        gi, ji, ei = col(table, r"质量门"), col(table, r"结论"), col(table, r"依据")
        if None in (gi, ji, ei):
            continue
        for row in table[1:]:
            match = re.match(r"^(G[1-6])\b", cell(row, gi))
            if match:
                gate = match.group(1)
                if gate in gates:
                    problems.append(f"质量门 {gate} 重复")
                gates[gate] = (cell(row, ji), cell(row, ei))
    for gate in (f"G{i}" for i in range(1, 7)):
        if gate not in gates:
            problems.append(f"缺少 {gate} 结论与依据")
        else:
            judgement, evidence = gates[gate]
            if not re.match(r"^通过(?:$|[（(：:；;，, ])", judgement) or not filled(evidence):
                problems.append(f"{gate} 尚未记录通过及具体依据")
    return problems


def cmd_consistency(a: argparse.Namespace) -> int:
    notes = Path(a.notes).resolve()
    if not notes.is_dir():
        print(f"笔记目录不存在：{notes}", file=sys.stderr)
        return 2
    work = notes / "_工作区"
    fails, warns, ok = [], [], []
    files = note_files(notes)
    articles = {k: v for k, v in files.items() if k not in ("00", "99")}
    bodies = {nn: read(path) for nn, path in articles.items()}
    plan = read(work / "_规划方案.md")
    planned = planned_articles(notes)
    listed = article_nums_in_00(notes)
    questions = planned_questions(plan)

    # 计划可以先于成文存在；最终收束才要求全部计划篇完成。
    for nn in files:
        duplicates = list(notes.glob(f"{nn}-*.md"))
        if len(duplicates) > 1:
            fails.append(f"篇号 {nn} 有多个正文文件：{', '.join(p.name for p in duplicates)}")
    if len(planned) != len(set(planned)):
        fails.append("_规划方案.md 篇目表有重复篇号")
    if len(listed) != len(set(listed)):
        fails.append("00 篇目清单有重复篇号")
    if articles and not planned:
        fails.append("已有正文，但 _规划方案.md 没有有效篇目表")
    if "00" in files:
        missing = [nn for nn in listed if nn not in articles]
        extra = [nn for nn in articles if nn not in listed]
        if missing:
            (fails if a.final else warns).append(f"00 列出的篇目尚无正文：{', '.join(missing)}")
        if extra:
            fails.append(f"正文存在，但 00 篇目清单没有列：{', '.join(extra)}")
        if planned and set(listed) != set(planned):
            fails.append("00 篇目清单与 _规划方案.md 的篇目表不一致")
    elif articles:
        fails.append("已有正文，但缺少 00 总览")
    for nn in articles:
        if nn not in planned:
            fails.append(f"第 {nn} 篇不在 _规划方案.md 的篇目表中")
    if a.final:
        for name in ("_勘察结果.md", "_规划方案.md", "_术语表.md", "_衔接约定.md", "_问题台账.md"):
            if not read(work / name).strip():
                fails.append(f"最终收束缺少 _工作区/{name}")
        for nn in ("00", "99", *planned):
            if nn not in files:
                fails.append(f"最终收束缺少第 {nn} 篇")
        if not planned:
            fails.append("最终收束没有有效的规划篇目")
        if not list(notes.glob("修改已有笔记-*.md")):
            fails.append("最终收束缺少修改提示词文档")

    # 核心机制必须有一个主讲篇；没有写出的计划篇不会被误认作丢失。
    for table in md_tables(plan):
        mi, li, pi = col(table, r"^机制$|^机制名称$"), col(table, r"^级别$"), col(table, r"主讲篇")
        if None in (mi, li, pi):
            continue
        for row in table[1:]:
            name, level = cell(row, mi), cell(row, li)
            if not filled(name) or level != "核心":
                continue
            mains = re.findall(r"(?<!\d)(\d{1,2})(?!\d)", cell(row, pi))
            if len(mains) != 1:
                fails.append(f"核心机制“{name}”必须有一个主讲篇")
            elif f"{int(mains[0]):02d}" not in planned:
                fails.append(f"核心机制“{name}”的主讲篇不在规划篇目中")

    # 理解稿是段落式交接物。只核对结构，逐条来源和讲解质量仍须人工审读。
    study_sections = ("流程走查", "机制卡", "关键数据", "追问", "意图", "取证材料|核验材料|核对材料", "细节去向", "讲述方案")
    for nn in articles:
        study = read(work / "_研读" / f"{nn}.md")
        review = read(work / "_审读记录" / f"{nn}.md")
        if not study.strip():
            fails.append(f"第 {nn} 篇缺少理解稿 _研读/{nn}.md")
        else:
            for heading in study_sections:
                if not section(study, heading):
                    fails.append(f"_研读/{nn}.md 缺少“{heading}”部分")
            plan_block = section(study, r"讲述方案")
            if plan_block:
                problem = narrative_plan_problem(plan_block)
                if problem:
                    fails.append(f"_研读/{nn}.md 的讲述方案{problem}")
        if not questions.get(nn):
            fails.append(f"第 {nn} 篇没有规划追问")
        if not review.strip():
            fails.append(f"第 {nn} 篇缺少审读记录 _审读记录/{nn}.md")
        else:
            fails += [f"_审读记录/{nn}.md：{message}" for message in check_review(review, questions.get(nn, {}))]
        if study.strip() and review.strip():
            ok.append(f"第 {nn} 篇理解稿与审读记录均存在（内容仍需人工核对）")

    # 术语候选只提醒读者可能混淆的叫法，不要求每个源码名都收入术语表。
    gloss = read(work / "_术语表.md")
    usage: dict[str, set[str]] = {}
    for nn, body in bodies.items():
        body = re.split(r"^##\s+代码地图", body, maxsplit=1, flags=re.M)[0]
        for name in code_names(body):
            if not re.search(r"[/\\]|\.\w+\b", name):
                usage.setdefault(name, set()).add(nn)
    for name, numbers in sorted(usage.items()):
        if len(numbers) > 1 and name not in gloss:
            warns.append(f"源码名 `{name}` 跨第 {', '.join(sorted(numbers))} 篇出现；请判断是否需要收入混淆术语表")

    # 业务交接写在小结和下一篇开头；机制之间的阅读关联不伪装成执行交接。
    links = read(work / "_衔接约定.md")
    for table in md_tables(links):
        ui, di, oi = col(table, r"上一篇"), col(table, r"下一篇"), col(table, r"交接物")
        if None in (ui, di, oi):
            continue
        for row in table[1:]:
            up, down, name = article_number(cell(row, ui)), article_number(cell(row, di)), cell(row, oi)
            if not (up and down and filled(name)):
                continue
            if up in bodies and name not in section(bodies[up], r"本篇小结"):
                fails.append(f"交接物“{name}”没有出现在第 {up} 篇小结")
            if down in bodies:
                opening = re.split(r"^##\s+", bodies[down], maxsplit=2, flags=re.M)
                if name not in "\n".join(opening[:2]):
                    fails.append(f"交接物“{name}”没有出现在第 {down} 篇开头")

    ledger = table_after(read(work / "_问题台账.md"), r"状态")
    sti = col(ledger, r"^状态")
    opens = [row[0] for row in ledger[1:] if cell(row, sti).lower() == "open"]
    if opens:
        (fails if a.final else warns).append(f"_问题台账.md 还有 {len(opens)} 个 open：{', '.join(opens[:20])}")

    # 规则版本：新建工程由 scaffold 写入；缺失报告为“未标注”，按警告处理，不自行推定。
    version_sources = {}
    for label, path in (("_工作区/_勘察结果.md", work / "_勘察结果.md"),
                        ("需求包/00-任务说明.md", notes.parent / "需求包" / "00-任务说明.md")):
        text = read(path)
        if text.strip():
            value = rules_version_of(text)
            if value:
                version_sources[label] = value
    values = sorted(set(version_sources.values()))
    if not values:
        rules_version = "未标注（早于 1.6）"
        warns.append(f"规则版本：{rules_version}；继续该工程前先向用户说明，不混用两版规则")
    elif len(values) > 1:
        rules_version = "不一致"
        warns.append("规则版本不一致：" + "；".join(f"{k} = {v}" for k, v in sorted(version_sources.items())))
    else:
        rules_version = values[0]
    note = "只检查结构和候选；不能证明 G1–G6 的语义质量已通过。"
    data = {"notes": str(notes), "rules_version": rules_version, "fail": fails, "warn": warns, "ok": ok, "scope": note}
    lines = [note, f"失败 {len(fails)}，警告 {len(warns)}"] + [f"FAIL {x}" for x in fails] + [f"WARN {x}" for x in warns] + [f"OK   {x}" for x in ok]
    emit(data, a.json, lines)
    return 1 if fails else 0


# ---------- lint ----------

def cmd_lint(a: argparse.Namespace) -> int:
    path = Path(a.file)
    text = read(path)
    if not text:
        print(f"读不到文件：{path}", file=sys.stderr)
        return 2
    words = AI_WORDS + (a.words or [])
    hits: list[dict] = []
    cross_references = []
    headings, in_map, version_block = 0, False, False
    labels = {"【推导】": 0, "【未确认】": 0}
    supplement_blocks: list[int] = []
    count_claims: dict[str, dict] = {}
    context: list[str] = []
    label_line = 1

    def add(kind: str, no: int, match: str, line: str) -> None:
        hits.append({"id": kind, "line": no, "match": match, "text": line.strip()[:160]})

    for no, line in strip_code(text):
        s = line.strip()
        heading = re.match(r"^(#{1,6})\s+(.*)$", s)
        if heading:
            headings += 1
            if re.search(r"代码地图", heading.group(2)):
                in_map = True
            elif len(heading.group(1)) <= 2:
                in_map = False
            if len(heading.group(1)) <= 3:
                context = []
            title = re.sub(r"^([一二三四五六七八九十百]+、|\d+(\.\d+)*[.、]?\s*|NN\s*·\s*)", "", heading.group(2)).strip()
            if SALES_TITLE.match(title):
                add("G6-推销式标题", no, title[:12], line)
        if in_map:
            for match in SOURCE_LINE.findall(line):
                add("G5-行号引用", no, match, line)
            continue
        for phrase in EDIT_PHRASES:
            if phrase in line:
                add("G6-修改痕迹", no, phrase, line)
        for word in words:
            if word in line and not heading:
                add("G6-用词", no, word, line)
        for phrase in TRANSITIONS:
            if phrase in line:
                add("G6-模板转场", no, phrase, line)
        supplement = re.match(r"^>\s*\*\*([^*]{2,12})\*\*[：:]", s)
        if supplement:
            supplement_blocks.append(no)
            version_block = supplement.group(1) == "版本演进"
            if supplement.group(1) not in SUPPLEMENT_LABELS:
                add("G6-补充标签", no, supplement.group(1), line)
        elif s and not s.startswith(">"):
            version_block = False
        for match in SOURCE_LINE.findall(line):
            add("G5-行号引用", no, match, line)
        for match in TEST_NAME.findall(line):
            add("G5-测试名称", no, match, line)
        for match in PROCESS_NOTE.findall(line):
            add("G5-取证过程", no, match, line)
        for label in labels:
            count = line.count(label)
            labels[label] += count
            if count:
                label_line = no
        versions = re.findall(r"\bV\d+(?:[._]\d+)*\b|\bv?\d+\.\d+(?:\.\d+)?\b", line)
        if len(versions) >= 2 and (not version_block or not re.search(r"因为|为了|解决|避免|改为|原先|旧.{0,12}新|问题", line)):
            add("G5-迁移版本列举", no, "、".join(versions), line)
        for count in COUNT_CLAIM.finditer(line):
            prefix, number = count.group(1), count.group(2)
            before = line[: count.start(2)].rstrip()
            # 序数、频率、区间和约数不是数量声明：第 3 步、每 20 行、三到五个、约 5 个、1.5 个。
            if before and before[-1] in "第每到至~–—-或约.．":
                continue
            after = line[count.end(): count.end() + 3]
            if after.startswith(("以上", "以内", "以下", "左右", "有余", "多")):
                continue
            # “43 个字符”“3 个小时”是度量，不是需要配清单的数量声明。
            if count.group(3) == "个" and after.startswith(("字符", "字节", "字", "小时", "月", "工作日", "百分点", "星期", "季度", "数量级", "像素")):
                continue
            value = cn_number(number)
            # 有“共/合计”前缀时核对两条起；否则三条起，避免把“一个/两个”当数量声明。
            if value is None or (value < 2 if prefix else value < 3):
                continue
            # 同一声明（数量 + 量词 + 紧跟的两个字）全篇只列一次，另记出现次数，核对一次清单即可。
            tail = re.match(r"[一-鿿A-Za-z]{0,2}", line[count.end():]).group(0)
            claim = re.sub(r"\s+", "", count.group(0)) + tail
            if claim in count_claims:
                count_claims[claim]["occurrences"] += 1
                continue
            add("G5-数量声明", no, claim, line)
            hits[-1]["occurrences"] = 1
            count_claims[claim] = hits[-1]
        for match in CROSS_REFERENCE.findall(line):
            nearby = "\n".join(context + [line])[-1800:]
            signals = {
                "problem": bool(re.search(r"为了|避免|防止|否则|减少|不必|不再|降低|没有.{0,12}(会|就)|每个请求", nearby)),
                "steps": bool(re.search(r"先.{1,100}(再|后)|读取|查询|写入|删除|计数|回填|命中|返回|校验|比较|同步|加载", nearby)),
                "failure": bool(re.search(r"失败|故障|异常|不可用|超时|拒绝|超限|丢失|出错", nearby)),
            }
            cross_references.append({"line": no, "match": match, "nearby_signals": signals,
                                     "note": "词语信号只供定位；即使齐全，也须人工确认够用讲解。"})
            if not all(signals.values()):
                missing = "、".join({"problem": "作用", "steps": "工作顺序", "failure": "失败行为"}[key]
                                  for key, present in signals.items() if not present)
                add("G5-指路代讲", no, f"{match}；附近缺少{missing}的词语信号", line)
        if s:
            context.append(line)
            context = context[-20:]
    total_labels = sum(labels.values())
    if total_labels > TAG_THRESHOLD:
        add("G5-标签密集", label_line, f"合计 {total_labels} 处，默认提示阈值 {TAG_THRESHOLD}", "检查解释能否改写成效果型，或把核验材料移到理解稿和 99。")
    total_lines = len(text.splitlines())
    spacing = round(total_lines / len(supplement_blocks), 1) if supplement_blocks else None
    if len(supplement_blocks) >= 2 and spacing < SUPPLEMENT_SPACING:
        add("G5-补充块过密", supplement_blocks[0],
            f"共 {len(supplement_blocks)} 个补充块，全文 {total_lines} 行，平均每 {spacing} 行一个（默认提示线每 {SUPPLEMENT_SPACING} 行一个）",
            "检查主线是否被切碎、主次是否倒置。")
    for item in figure_legend_hits(text):
        add("G3-图例不符", item["line"], item["match"], item["text"])
    extras = lint_extra_signals(text)
    for item in extras["dense_paragraphs"]:
        add("G6-名称密集", item["line"], f"本段 {item['count']} 个反引号名称（默认提示超过 {NAME_PARAGRAPH_LIMIT} 个）", item["text"])
    density = extras["name_density"]
    if density["per_10_lines"] > NAME_DENSITY_REFERENCE and density["body_lines"] >= 30:
        add("G6-名称密集", 1, f"全篇正文每 10 行 {density['per_10_lines']} 个名称（参考线每 10 行 {NAME_DENSITY_REFERENCE} 个）",
            "参考线是默认值；表格、代码块和代码地图不计。")
    for item in extras["long_sentences"]:
        add("G6-长并列句", item["line"], f"{item['chars']} 字、{item['separators']} 处分号或顿号", item["text"])
    if len(extras["negatives"]) > NEGATIVE_THRESHOLD:
        for item in extras["negatives"]:
            add("G6-否定限定", item["line"], item["match"], item["text"])
        add("G6-否定限定", extras["negatives"][-1]["line"],
            f"合计 {len(extras['negatives'])} 处，超过默认提示阈值 {NEGATIVE_THRESHOLD}",
            "逐句判断：改写为对现状的直接陈述，或把不影响理解的未知移到 99。")
    note = "候选仅是线索，不能自动判定 G3/G5/G6 通过；事实堆叠、一句话机制、补充主次和组织仍需人工阅读。"
    data = {"file": str(path), "headings": headings, "hits": hits,
            "label_counts": {**labels, "total": total_labels, "threshold": TAG_THRESHOLD},
            "cross_references": cross_references,
            "supplement_blocks": {"count": len(supplement_blocks), "lines": total_lines, "spacing": spacing,
                                  "threshold": SUPPLEMENT_SPACING},
            "name_density": density,
            "negative_constraints": {"count": len(extras["negatives"]), "threshold": NEGATIVE_THRESHOLD,
                                     "positions": extras["negatives"]},
            "scope": note}
    lines = [f"{path}：候选 {len(hits)} 处；标题 {headings} 个。", note,
             f"解释标签合计 {total_labels} 处（默认提示阈值 {TAG_THRESHOLD}）。",
             f"正文名称密度：每 10 行 {density['per_10_lines']} 个（参考线 {NAME_DENSITY_REFERENCE}）；"
             f"否定限定句式 {len(extras['negatives'])} 处（提示阈值 {NEGATIVE_THRESHOLD}）；"
             f"补充块 {len(supplement_blocks)} 个。"]
    lines += [f"{hit['id']}  第 {hit['line']} 行  [{hit['match']}]"
              + (f"（同一声明共 {hit['occurrences']} 处）" if hit.get("occurrences", 1) > 1 else "")
              + f"  {hit['text']}" for hit in hits]
    emit(data, a.json, lines)
    return 0


# ---------- skeleton ----------

def cmd_skeleton(a: argparse.Namespace) -> int:
    path = Path(a.file)
    text = read(path)
    if not text:
        print(f"读不到文件：{path}", file=sys.stderr)
        return 2
    if a.out and Path(a.out).resolve() == path.resolve():
        print("--out 不能覆盖源文件。", file=sys.stderr)
        return 2
    lines = text.splitlines()
    headings = parse_headings(text)
    figures = []
    fence, kind = None, ""
    for no, line in enumerate(lines, 1):
        s = line.strip()
        if fence:
            if s.startswith(fence):
                if kind in FIGURE_LANGS:
                    figures.append({"line": no, "kind": kind})
                fence, kind = None, ""
            continue
        m = FENCE_LINE.match(s) if s.startswith(("```", "~~~")) else None
        if m:
            fence, kind = m.group(1)[0] * 3, m.group(2).lower()
            continue
        if IMG_LINE.search(line):
            figures.append({"line": no, "kind": "image"})
    if not headings:
        skeleton = text.rstrip("\n") + "\n"
        title = ""
        lead = skeleton
        first_title = ""
        outline_rows: list[tuple[int, int, str, str | None]] = []
    else:
        title_idx, _, title = headings[0]
        rest = headings[1:]
        if not rest:
            skeleton = "\n".join(lines).rstrip("\n") + "\n"
            lead, first_title, outline_rows = "\n".join(lines[title_idx + 1:]), "", []
        else:
            chapter_level = min(level for _, level, _ in rest)
            first_pos = next(i for i, (_, level, _) in enumerate(rest) if level == chapter_level)
            first_idx = rest[first_pos][0]
            first_end = len(lines)
            for idx, level, _ in rest[first_pos + 1:]:
                if level <= chapter_level:
                    first_end = idx
                    break
            lead = "\n".join(lines[title_idx + 1: rest[0][0]]).strip("\n")
            first_title = rest[first_pos][2]
            outline_rows = []
            for pos, (idx, level, item) in enumerate(rest):
                if first_idx <= idx < first_end:
                    continue  # 全貌等第一个一级章节已全文输出
                if level > chapter_level + 2:
                    continue
                if re.search(r"代码地图", item):
                    outline_rows.append((idx, level, item, None))
                    continue
                stop = rest[pos + 1][0] if pos + 1 < len(rest) else len(lines)
                outline_rows.append((idx, level, item, first_paragraph_after(lines, idx + 1, stop)))
            parts = [lines[title_idx], ""]
            if lead:
                parts += [lead, ""]
            parts += ["\n".join(lines[first_idx:first_end]).rstrip("\n"), ""]
            for idx, level, item, para in outline_rows:
                parts += ["#" * level + " " + item, ""]
                if para:
                    parts += [para, ""]
            skeleton = "\n".join(parts).rstrip("\n") + "\n"
    header ="<!-- 骨架视图（skeleton）：篇首块 + 第一个一级章节全文 + 其余一至三级标题及其下第一段；不是完整正文。 -->\n\n"
    output = header + skeleton
    if a.out:
        out_path = Path(a.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(output)
    scope = "骨架视图只供阶段 A 复述与成文自查；完整内容以正文为准。"
    data = {"file": str(path), "title": title, "out": str(Path(a.out).resolve()) if a.out else None,
            "headings": [{"line": i + 1, "level": level, "title": item} for i, level, item in headings],
            "figures": figures, "skeleton": output, "scope": scope}
    emit(data, a.json, ([f"已写出骨架视图：{a.out}", f"标题 {len(headings)} 个；图 {len(figures)} 处。", scope]
                        if a.out else output.splitlines() + ["", scope]))
    return 0


# ---------- render-revise ----------

def embed(md: str) -> str:
    out, fence = [], False
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("```"):
            fence = not fence
        if not fence:
            if re.match(r"^#\s", line) or s.startswith("**何时读本文件**"):
                continue
            m = re.match(r"^(#{2,6})(\s.*)$", line)
            if m:
                line = "#" * min(6, len(m.group(1)) + 2) + m.group(2)
        out.append(line)
    return "\n".join(out).strip()


def cmd_render_revise(a: argparse.Namespace) -> int:
    notes = Path(a.notes).resolve()
    refs, tpls = resource_dirs()
    target = notes / f"修改已有笔记-{a.repo_name}.md"
    if target.exists():
        print(f"{target} 已存在，拒绝覆盖（里面可能有用户追加的要求）。", file=sys.stderr)
        return 1
    survey = read(notes / "_工作区" / "_勘察结果.md")
    m_path = re.search(r"\|\s*仓库路径\s*\|\s*([^|]+?)\s*\|", survey)
    m_base = re.search(r"\|\s*源码基准提交\s*\|\s*([^|]+?)\s*\|", survey)
    version = rules_version_of(survey) or "未标注（早于 1.6）"
    text = read(tpls / "修改已有笔记.md")
    text = text.replace("{{仓库名}}", a.repo_name)
    text = text.replace("{{源码仓}}", (a.source_repo or (m_path.group(1) if m_path else "<填写>")).strip())
    text = text.replace("{{基准}}", (a.base or (m_base.group(1) if m_base else "<填写>")).strip())
    text = text.replace("{{规则版本}}", version)
    text = text.replace("{{讲解规范}}", embed(read(refs / "讲解规范.md")))
    text = text.replace("{{表达规范}}", embed(read(refs / "表达规范.md")))
    with target.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    emit({"created": str(target), "rules_version": version}, a.json,
         [f"已生成：{target}", f"规则版本：{version}", "下一步：填写「二、项目口径区」里仍是 <填写> 的项。"])
    return 0


# ---------- main ----------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ruan-project2doc 辅助脚本")
    p.add_argument("--version", action="version", version=RULES_VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("deps", help="检查依赖（只读）")
    s.add_argument("--skills-dir", action="append", help="额外的 Skill 根目录，可多次给出")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_deps)

    s = sub.add_parser("survey", help="勘察源码仓与 project-map（只读）")
    s.add_argument("--repo", required=True)
    s.add_argument("--map")
    s.add_argument("--reader-check", help="ruan-project-reader 的 check.py 路径")
    s.add_argument("--skills-dir", action="append")
    s.add_argument("--no-check", action="store_true", help="不运行 reader 的 check.py")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_survey)

    s = sub.add_parser("scaffold", help="建笔记工程骨架（只新建，不覆盖）")
    s.add_argument("--project", required=True)
    s.add_argument("--repo-name", required=True)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_scaffold)

    s = sub.add_parser("progress", help="核对步骤总览与笔记仓产物（只读）")
    s.add_argument("--notes", required=True)
    s.add_argument("--version-dir", required=True)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_progress)

    s = sub.add_parser("consistency", help="跨篇一致性检查（只读）")
    s.add_argument("--notes", required=True)
    s.add_argument("--final", action="store_true", help="U-收束时使用：要求计划篇目和交接物齐全，问题台账无 open")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_consistency)

    s = sub.add_parser("lint", help="讲解与表达候选扫描（只读）")
    s.add_argument("--file", required=True)
    s.add_argument("--words", nargs="*", help="项目追加的 AI 味词")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_lint)

    s = sub.add_parser("skeleton", help="输出骨架视图（只读；--out 另写一个文件）")
    s.add_argument("--file", required=True)
    s.add_argument("--out", help="把骨架视图写到这个文件（不能是源文件本身）")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_skeleton)

    s = sub.add_parser("render-revise", help="生成修改提示词文档（只新建，不覆盖）")
    s.add_argument("--notes", required=True)
    s.add_argument("--repo-name", required=True)
    s.add_argument("--source-repo")
    s.add_argument("--base")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_render_revise)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
