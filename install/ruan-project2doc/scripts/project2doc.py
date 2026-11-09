#!/usr/bin/env python3
"""ruan-project2doc 的机械辅助脚本（只用标准库 + git）。

命令：
  deps           检查依赖（只读）
  survey         勘察源码仓与 project-map（只读）
  scaffold       建笔记工程骨架（只新建，不覆盖）
  progress       核对步骤总览与笔记仓产物（只读）
  consistency    跨篇一致性检查（只读）
  lint           可读性候选扫描（只读，命中只是线索）
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
SOURCE_PREFIXES = ("源码直取", "借鉴 project-map")
CHECK_STATES = {"已核实", "推断", "待核实"}
SUPPLEMENT_LABELS = {"补充说明", "版本差异", "实现限制", "并发情况", "异常情况", "测试证据", "当前限制"}
M01_PHRASES = ["修正补充", "代码核验说明", "此前理解有误", "重新确认后", "更正：", "更正:", "经核实后发现", "之前写错", "此前写错", "（已修正）"]
R07_WORDS = ["钉死", "拓扑", "抓手", "闭环", "赋能", "打通", "底层逻辑", "颗粒度", "边界", "兜底逻辑", "心智"]
R33_PREFIX = re.compile(r"^(为什么|必须|真正|关键是|只需要)")
R40_PHRASES = ["明确了", "回到正题", "接下来我们", "下面我们来看", "让我们", "综上所述", "值得注意的是", "需要注意的是", "如前所述", "不难看出"]


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
        if s.startswith("<!--") and "-->" not in s:
            comment = True
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
    for name in ("_勘察结果.md", "_拆分方案.md", "_术语表.md", "_衔接约定.md", "_问题台账.md"):
        copy_new(tpls / name, notes / "_工作区" / name, created, skipped)
    pack = proj / "需求包"
    copy_new(tpls / "需求包-00-任务说明.md", pack / "00-任务说明.md", created, skipped)
    copy_new(tpls / "需求包-02-步骤拆分要求.md", pack / "02-步骤拆分要求.md", created, skipped)
    for f in sorted(refs.glob("*.md")):
        copy_new(f, pack / "规则" / f.name, created, skipped)
    for f in sorted(tpls.glob("*.md")):
        if not f.name.startswith("需求包-"):
            copy_new(f, pack / "模板" / f.name, created, skipped)
    copy_new(SCRIPT, pack / "工具" / "project2doc.py", created, skipped)
    data = {"project": str(proj), "repo_name": a.repo_name, "created": created, "skipped_existing": skipped}
    lines = [f"笔记工程：{proj}", f"新建 {len(created)} 项，已存在而跳过 {len(skipped)} 项。"] + [f"  + {c}" for c in created] + [f"  = {s}" for s in skipped]
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
    text = read(notes / "_工作区" / "_拆分方案.md")
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
    t = table_after(section(read(f), r"篇目清单") or "", r"篇号")
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
        kind = re.search(r"(取证|成文|校对|收束)", ln)
        num = re.search(r"(?<!\d)(\d{2})(?!\d)", ln[kind.end():]) if kind and kind.group(1) != "收束" else None
        if kind and kind.group(1) == "收束":
            for need in ("00", "99"):
                if need not in files:
                    fails.append(f"{sid} 收束已完成，但缺少 {need}-*.md")
            if not list(notes.glob("修改已有笔记-*.md")):
                fails.append(f"{sid} 收束已完成，但缺少 修改已有笔记-*.md")
        elif kind and num:
            nn = num.group(1)
            need = {"取证": work / "_事实" / f"{nn}.md", "成文": files.get(nn), "校对": work / "_校对记录" / f"{nn}.md"}[kind.group(1)]
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
        have = [n for n, p in (("事实", work / "_事实" / f"{nn}.md"), ("正文", files.get(nn)), ("校对", work / "_校对记录" / f"{nn}.md")) if p and Path(p).is_file()]
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


def cmd_consistency(a: argparse.Namespace) -> int:
    notes = Path(a.notes).resolve()
    work = notes / "_工作区"
    fails, warns, ok = [], [], []
    files = note_files(notes)
    articles = {k: v for k, v in files.items() if k not in ("00", "99")}

    # 1. 00 篇目清单与实际文件
    listed = article_nums_in_00(notes)
    if "00" in files:
        missing = [n for n in listed if n not in articles]
        extra = [n for n in articles if n not in listed]
        if missing:
            fails.append(f"00 篇目清单列了，但文件不存在：{', '.join(missing)}")
        if extra:
            fails.append(f"文件存在，但 00 篇目清单没有列：{', '.join(extra)}")
        if not missing and not extra:
            ok.append(f"00 篇目清单与文件一致（{len(listed)} 篇）")
    planned = planned_articles(notes)
    if planned and articles:
        not_planned = [n for n in articles if n not in planned]
        if not_planned:
            warns.append(f"这些篇不在 _拆分方案.md 的篇目表里：{', '.join(not_planned)}")

    # 2. 术语：跨篇出现的源码名应进术语表（K14）
    gloss = read(work / "_术语表.md")
    gt = table_after(gloss, r"术语")
    gloss_text = "\n".join(" ".join(r) for r in gt[1:])
    gloss_terms = []
    ti = col(gt, r"^术语")
    for row in gt[1:]:
        if ti is not None and ti < len(row) and row[ti]:
            gloss_terms.append(re.sub(r"[`*]", "", row[ti]).strip())
    usage: dict[str, set[str]] = {}
    bodies = {nn: read(p) for nn, p in articles.items()}
    for nn, body in bodies.items():
        evidence_cut = body.split("## 证据索引")[0]
        for n in code_names(evidence_cut):
            if re.search(r"[/\\]|\.(java|py|ts|js|go|kt|rs|vue|tsx|jsx|sql|xml|ya?ml)\b", n):
                continue
            usage.setdefault(n, set()).add(nn)
    cross = sorted(n for n, s in usage.items() if len(s) >= 2)
    for n in cross:
        if n not in gloss_text:
            warns.append(f"源码名 `{n}` 出现在第 {', '.join(sorted(usage[n]))} 篇（跨篇），但不在 _术语表.md（K14）")
    if bodies and gloss_terms:
        all_text = "\n".join(bodies.values())
        for t in gloss_terms:
            if t and t not in all_text:
                warns.append(f"术语表词条“{t}”没有出现在任何一篇正文里")
    if cross and not any("跨篇" in w for w in warns):
        ok.append(f"跨篇源码名 {len(cross)} 个，都已进术语表")

    # 3. 衔接约定：交接物名出现在上一篇终点节和下一篇篇首
    link = read(work / "_衔接约定.md")
    lt = table_after(section(link, r"相邻篇") or link, r"上一篇")
    up_i, down_i, obj_i = col(lt, r"上一篇"), col(lt, r"下一篇"), col(lt, r"交接物")
    for row in lt[1:]:
        if None in (up_i, down_i, obj_i) or max(up_i, down_i, obj_i) >= len(row):
            continue
        mu, md = re.search(r"(\d{1,2})", row[up_i]), re.search(r"(\d{1,2})", row[down_i])
        name = re.sub(r"[`*]", "", row[obj_i]).strip()
        if not (mu and md and name):
            continue
        up, down = f"{int(mu.group(1)):02d}", f"{int(md.group(1)):02d}"
        if up in bodies:
            end_sec = section(bodies[up], r"本篇终点")
            if name not in end_sec:
                fails.append(f"交接物“{name}”没有出现在第 {up} 篇的“本篇终点与下一篇的接口”一节")
            else:
                ok.append(f"第 {up} 篇终点节含交接物“{name}”")
        if down in bodies:
            head = bodies[down].split("\n## ")[0]
            if name not in head:
                fails.append(f"交接物“{name}”没有出现在第 {down} 篇篇首（覆盖行或一句话主线之前）")
            else:
                ok.append(f"第 {down} 篇篇首含交接物“{name}”")

    # 4. 事实摘要
    for f in sorted((work / "_事实").glob("*.md")) if (work / "_事实").is_dir() else []:
        nn = f.stem
        text = read(f)
        ids, last = set(), 0
        ft = table_after(text, r"编号")
        si, ci = col(ft, r"来源"), col(ft, r"核对")
        for row in ft[1:]:
            fid = row[0] if row else ""
            if not fid or fid.startswith("E-NN"):
                continue
            m = re.fullmatch(r"E-(\d{2})-(\d{3})", fid)
            if not m:
                fails.append(f"_事实/{f.name}：编号格式不对：{fid}")
                continue
            if m.group(1) != nn:
                fails.append(f"_事实/{f.name}：编号 {fid} 的篇号与文件名不一致")
            if fid in ids:
                fails.append(f"_事实/{f.name}：编号重复 {fid}")
            seq = int(m.group(2))
            if seq <= last:
                warns.append(f"_事实/{f.name}：编号 {fid} 没有单调递增")
            ids.add(fid)
            last = max(last, seq)
            if si is not None and (si >= len(row) or not row[si].startswith(SOURCE_PREFIXES)):
                fails.append(f"_事实/{f.name}：{fid} 的来源不是规定的三种之一")
            if ci is not None and (ci >= len(row) or row[ci] not in CHECK_STATES):
                fails.append(f"_事实/{f.name}：{fid} 的核对状态不是 已核实/推断/待核实")
        check = table_after(section(text, r"自查结果") or "", r"ID")
        fails += [f"_事实/{f.name}：{x}" for x in idcheck(check, [f"F{i:02d}" for i in list(range(1, 9)) + list(range(10, 21))])]
        ok.append(f"_事实/{f.name}：{len(ids)} 条事实")

    # 5. 校对记录
    for f in sorted((work / "_校对记录").glob("*.md")) if (work / "_校对记录").is_dir() else []:
        rows = [r for t in md_tables(read(f)) if t and re.search(r"^ID$", t[0][0]) for r in t[1:]]
        need = [f"R{i:02d}" for i in list(range(1, 18)) + list(range(20, 30)) + list(range(30, 39)) + [40, 41, 42, 50, 51, 52]]
        fails += [f"_校对记录/{f.name}：{x}" for x in idcheck([["ID", "x"]] + rows, need)]

    # 6. 问题台账
    ledger = table_after(read(work / "_问题台账.md"), r"状态")
    sti = col(ledger, r"^状态")
    opens = [r[0] for r in ledger[1:] if sti is not None and sti < len(r) and r[sti].strip().lower() == "open"]
    if opens:
        (fails if a.final else warns).append(f"_问题台账.md 还有 {len(opens)} 个 open：{', '.join(opens[:20])}")

    data = {"notes": str(notes), "fail": fails, "warn": warns, "ok": ok}
    lines = [f"失败 {len(fails)}，警告 {len(warns)}"] + [f"FAIL {x}" for x in fails] + [f"WARN {x}" for x in warns] + [f"OK   {x}" for x in ok]
    emit(data, a.json, lines)
    return 1 if fails else 0


def idcheck(table: list[list[str]], need: list[str]) -> list[str]:
    """逐 ID 落盘检查：每个 ID 一行，结果不能为空，也不能只写“已检查”。"""
    problems = []
    seen = {}
    for row in table[1:]:
        if row and re.fullmatch(r"[RFM]\d{2}", row[0]):
            seen[row[0]] = " ".join(row[1:]).strip()
    if not seen:
        return []  # 模板尚未开始填写
    for i in need:
        v = seen.get(i)
        if v is None:
            problems.append(f"缺少 {i} 这一行")
        elif not v or v in {"-", "—"}:
            problems.append(f"{i} 没有填写结果")
        elif re.fullmatch(r"(已检查|已查|通过|OK|ok|无问题)[。.]?", v):
            problems.append(f"{i} 只写了“{v}”，必须写命中位置或“无”")
    return problems


# ---------- lint ----------

def cmd_lint(a: argparse.Namespace) -> int:
    path = Path(a.file)
    text = read(path)
    if not text:
        print(f"读不到文件：{path}", file=sys.stderr)
        return 2
    words = R07_WORDS + (a.words or [])
    hits = []
    headings = 0
    for no, line in strip_code(text):
        s = line.strip()
        for p in M01_PHRASES:
            if p in line:
                hits.append(("M01", no, p, s))
        for w in words:
            if w in line and not s.startswith("#"):
                hits.append(("R07", no, w, s))
        for p in R40_PHRASES:
            if p in line:
                hits.append(("R40", no, p, s))
        hm = re.match(r"^(#{1,6})\s+(.*)$", s)
        if hm:
            headings += 1
            title = re.sub(r"^([一二三四五六七八九十百]+、|\d+(\.\d+)*[.、]?\s*|NN\s*·\s*)", "", hm.group(2)).strip()
            if R33_PREFIX.match(title):
                hits.append(("R33", no, title[:6], s))
        lm = re.match(r"^(?:>\s*)?\*\*([^*]{2,8})\*\*[：:]", s)
        if lm and lm.group(1) not in SUPPLEMENT_LABELS:
            hits.append(("R23", no, lm.group(1), s))
    data = {"file": str(path), "headings": headings, "hits": [{"id": h[0], "line": h[1], "match": h[2], "text": h[3][:160]} for h in hits]}
    r33 = sum(1 for h in hits if h[0] == "R33")
    lines = [f"{path}：候选 {len(hits)} 处（只是线索，是否真有问题逐条判断）；标题 {headings} 个，其中推销式开头 {r33} 个"]
    for h in hits:
        lines.append(f"{h[0]}  第 {h[1]} 行  [{h[2]}]  {h[3][:120]}")
    emit(data, a.json, lines)
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
    text = read(tpls / "修改已有笔记.md")
    text = text.replace("{{仓库名}}", a.repo_name)
    text = text.replace("{{源码仓}}", (a.source_repo or (m_path.group(1) if m_path else "<填写>")).strip())
    text = text.replace("{{基准}}", (a.base or (m_base.group(1) if m_base else "<填写>")).strip())
    text = text.replace("{{约束取舍表}}", embed(read(refs / "约束取舍表.md")))
    text = text.replace("{{问题清单}}", embed(read(refs / "问题清单.md")))
    target.write_text(text, encoding="utf-8", newline="\n")
    emit({"created": str(target)}, a.json, [f"已生成：{target}", "下一步：填写「二、项目口径区」里仍是 <填写> 的项。"])
    return 0


# ---------- main ----------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ruan-project2doc 辅助脚本")
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
    s.add_argument("--final", action="store_true", help="U-收束时使用：问题台账有 open 即失败")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_consistency)

    s = sub.add_parser("lint", help="可读性候选扫描（只读）")
    s.add_argument("--file", required=True)
    s.add_argument("--words", nargs="*", help="项目追加的 AI 味词")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_lint)

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
