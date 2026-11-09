"""ruan-project2doc 辅助脚本 project2doc.py 的回归测试。

运行：python -m unittest discover -s src/tests -v
只用标准库和 git；所有夹具建在临时目录里，不依赖本机其他项目。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "ruan-project2doc"
SCRIPT = SKILL / "scripts" / "project2doc.py"
ENV = {**os.environ, "PYTHONUTF8": "1", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=ENV)


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", env=ENV)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


def commit(repo: Path, msg: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="p2d-测试-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


class SkillLayout(unittest.TestCase):
    def test_frontmatter_and_resources(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: ruan-project2doc\n"))
        desc = next(l for l in text.splitlines() if l.startswith("description:"))
        self.assertLessEqual(len(desc) - len("description: "), 500)
        for ref in ["project-map借鉴", "编排与交接物", "写作规范", "约束取舍表", "校对协议", "修改协议",
                    "自检清单", "概念定义", "问题清单", "需求包规格"]:
            self.assertTrue((SKILL / "references" / f"{ref}.md").is_file(), ref)
            self.assertIn(f"references/{ref}.md", text, f"SKILL.md 没有指向 {ref}")
        for tpl in ["单篇笔记", "00-总览与主线地图", "99-复核说明", "修改已有笔记", "_勘察结果", "_拆分方案",
                    "_术语表", "_衔接约定", "_事实", "_校对记录", "_问题台账", "需求包-00-任务说明", "需求包-02-步骤拆分要求"]:
            self.assertTrue((SKILL / "templates" / f"{tpl}.md").is_file(), tpl)

    def test_problem_list_ids_complete(self) -> None:
        text = (SKILL / "references" / "问题清单.md").read_text(encoding="utf-8")
        ids = [f"R{i:02d}" for i in [*range(1, 18), *range(20, 30), *range(30, 39), 40, 41, 42, 50, 51, 52]]
        ids += [f"F{i:02d}" for i in [*range(1, 9), *range(10, 21), 30, 31, 32]] + [f"M0{i}" for i in range(1, 9)]
        for i in ids:
            self.assertIn(f"| {i} |", text, i)
        defs = (SKILL / "references" / "概念定义.md").read_text(encoding="utf-8")
        for i in range(1, 20):
            self.assertIn(f"| K{i:02d} |", defs)
        cons = (SKILL / "references" / "约束取舍表.md").read_text(encoding="utf-8")
        for i in range(1, 24):
            self.assertIn(f"| C{i} |", cons)

    def test_rules_are_stack_neutral(self) -> None:
        """通用性原则：规则正文不出现特定框架名（真实例句与映射表除外）。"""
        for name in ["project-map借鉴", "编排与交接物", "校对协议", "修改协议", "自检清单", "需求包规格"]:
            text = (SKILL / "references" / f"{name}.md").read_text(encoding="utf-8")
            for word in ["Spring", "@Scheduled", "RocketMQ", "MinIO", "MyBatis", "Controller"]:
                self.assertNotIn(word, text, f"{name} 含技术栈专用词 {word}")


class Deps(unittest.TestCase):
    def test_json(self) -> None:
        r = run("deps", "--json")
        data = json.loads(r.stdout)
        self.assertIn("git", data)
        self.assertEqual(r.returncode, 0 if data["ruan_dev_skills"] and data["git"] else 1)


class Survey(Base):
    def make(self, same: bool) -> Path:
        repo = self.tmp / "demo"
        repo.mkdir()
        git(repo, "init", "-q")
        write(repo / "pom.xml", "<project/>")
        write(repo / "src" / "App.java", "class App {}")
        base = commit(repo, "c1")
        if not same:
            write(repo / "src" / "Order.java", "class Order {}")
            commit(repo, "c2")
        m = self.tmp / "project-map"
        write(m / "README.md", f"""
            # 项目执行流程导航

            项目：demo；源码 `demo` @ `{base}`
            整体读者内容指纹：deadbeef12345678
            """)
        write(m / "COVERAGE.md", """
            # 发现与覆盖

            范围：demo
            本轮发现暂时收敛：否
            本轮范围整体完成：否
            """)
        write(m / "STATE.md", """
            规范版本：2.4
            梳理中模块数：1
            待验收模块数：0
            本层完成模块数：1
            已证叶子模块数：0
            待办数：3
            阻塞数：0
            入口数：2
            汇点数：1
            覆盖记录数：5
            """)
        write(m / "modules" / "00-总览.md", "# 总览\n状态：本层完成\n限制：无\n")
        write(m / "modules" / "01-下单.md", "# 下单\n状态：梳理中\n限制：有\n")
        return repo

    def test_base_same(self) -> None:
        repo = self.make(same=True)
        r = run("survey", "--repo", str(repo), "--no-check", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        pm = json.loads(r.stdout)["project_map"]
        self.assertEqual(pm["state"]["待办数"], "3")
        self.assertEqual({m["file"]: m["status"] for m in pm["modules"]}["01-下单.md"], "梳理中")
        self.assertEqual(len(pm["base_compare"]), 1, "指纹行不应当成基准提交")
        self.assertTrue(pm["base_compare"][0]["same"])

    def test_base_outdated(self) -> None:
        repo = self.make(same=False)
        pm = json.loads(run("survey", "--repo", str(repo), "--no-check", "--json").stdout)["project_map"]
        c = pm["base_compare"][0]
        self.assertFalse(c["same"])
        self.assertEqual(c["behind"], 1)
        self.assertEqual(c["changed_files"], ["src/Order.java"])

    def test_no_map(self) -> None:
        repo = self.tmp / "solo"
        repo.mkdir()
        git(repo, "init", "-q")
        write(repo / "main.py", "print(1)")
        commit(repo, "c1")
        data = json.loads(run("survey", "--repo", str(repo), "--json").stdout)
        self.assertIsNone(data["project_map"])
        self.assertEqual(len(data["git_repos"]), 1)


class Scaffold(Base):
    def test_create_and_idempotent(self) -> None:
        proj = self.tmp / "demo-笔记工程"
        r = run("scaffold", "--project", str(proj), "--repo-name", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((proj / "笔记" / ".git").exists())
        for p in ["笔记/_工作区/_拆分方案.md", "需求包/00-任务说明.md", "需求包/02-步骤拆分要求.md",
                  "需求包/规则/问题清单.md", "需求包/模板/单篇笔记.md", "需求包/工具/project2doc.py"]:
            self.assertTrue((proj / p).is_file(), p)
        self.assertFalse((proj / "需求包" / "模板" / "需求包-00-任务说明.md").exists())
        (proj / "笔记" / "_工作区" / "_拆分方案.md").write_text("用户内容", encoding="utf-8")
        run("scaffold", "--project", str(proj), "--repo-name", "demo")
        self.assertEqual((proj / "笔记" / "_工作区" / "_拆分方案.md").read_text(encoding="utf-8"), "用户内容")

    def test_refuse_inside_git_repo(self) -> None:
        git(self.tmp, "init", "-q")
        r = run("scaffold", "--project", str(self.tmp / "x-笔记工程"), "--repo-name", "x")
        self.assertEqual(r.returncode, 2)

    def test_copied_script_works_from_package(self) -> None:
        proj = self.tmp / "p"
        run("scaffold", "--project", str(proj), "--repo-name", "demo")
        r = subprocess.run([sys.executable, str(proj / "需求包" / "工具" / "project2doc.py"), "render-revise",
                            "--notes", str(proj / "笔记"), "--repo-name", "demo"], capture_output=True, text=True,
                           encoding="utf-8", env=ENV)
        self.assertEqual(r.returncode, 0, r.stderr)


class NotesFixture(Base):
    def notes(self, good: bool = True) -> Path:
        n = self.tmp / "笔记"
        n.mkdir()
        git(n, "init", "-q")
        write(n / "00-总览与主线地图.md", """
            # 00 · demo 总览
            ## 三、篇目清单与衔接
            | 篇号 | 标题 | 起点 | 终点 | 下一篇 |
            |---|---|---|---|---|
            | 01 | 下单 | POST /orders | 待支付订单 | 待支付订单 |
            | 02 | 支付 | 支付回调 | 已支付 | — |
            ## 四、一句话结论
            """)
        write(n / "01-订单创建.md", """
            # 01 · 订单创建
            > 覆盖：POST /orders → 待支付订单
            ## 一、链路全貌
            下单时 `OrderService` 先锁库存。
            ## 本篇终点与下一篇的接口
            留下一笔待支付订单。
            ## 证据索引
            - `src/order.py#create`
            """)
        head2 = "待支付订单" if good else "订单"
        write(n / "02-订单支付.md", f"""
            # 02 · 订单支付
            > 覆盖：{head2} → 已支付
            ## 一、链路全貌
            回调到达后 `OrderService` 改状态。
            ## 本篇终点与下一篇的接口
            订单已支付。
            """)
        w = n / "_工作区"
        write(w / "_术语表.md", f"""
            | 术语（直观叫法） | 本项目中指什么 | 首次出现 | 源码名 | 别名 |
            |---|---|---|---|---|
            | 订单服务 | 处理订单 | 01 | {'`OrderService`' if good else '—'} | |
            """)
        write(w / "_衔接约定.md", """
            ## 一、相邻篇交接
            | 上一篇 | 下一篇 | 交接物（同一个名字） | 交接时的状态 |
            |---|---|---|---|
            | 01 | 02 | 待支付订单 | pending |
            """)
        write(w / "_拆分方案.md", """
            ## 二、篇目
            | 篇号 | 标题 |
            |---|---|
            | 01 | 订单创建 |
            | 02 | 订单支付 |
            """)
        rows = "\n            ".join(f"| F{i:02d} | 无 |" for i in [*range(1, 9), *range(10, 21)])
        if not good:
            rows = rows.replace("| F12 | 无 |", "| F12 | 已检查 |")
        fid = "E-01-001" if good else "E-02-001"
        src = "源码直取" if good else "看过代码"
        write(w / "_事实" / "01.md", f"""
            ## 一、事实条目（K15）
            | 编号 | 一句话事实 | 来源 | 核对状态 | 涉及的数字或状态名 |
            |---|---|---|---|---|
            | {fid} | 下单先锁库存 | {src} | 已核实 | pending |
            ## 七、自查结果（附录 B 的 B1、B2）
            | ID | 结果 |
            |---|---|
            {rows}
            """)
        write(w / "_问题台账.md", """
            | 编号 | 清单 ID | 优先级 | 篇 | 问题 | 代码依据 | 状态 | 处理说明 |
            |---|---|---|---|---|---|---|---|
            | Q-001 | F10 | P1 | 01 | 夸大 | x | open | |
            """)
        return n


class Consistency(NotesFixture):
    def test_good(self) -> None:
        r = run("consistency", "--notes", str(self.notes(True)), "--json")
        data = json.loads(r.stdout)
        self.assertEqual(data["fail"], [], data)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(any("open" in w for w in data["warn"]))

    def test_final_open_ledger_fails(self) -> None:
        r = run("consistency", "--notes", str(self.notes(True)), "--final", "--json")
        self.assertEqual(r.returncode, 1)

    def test_bad(self) -> None:
        r = run("consistency", "--notes", str(self.notes(False)), "--json")
        data = json.loads(r.stdout)
        joined = "\n".join(data["fail"] + data["warn"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("第 02 篇篇首", joined)
        self.assertIn("篇号与文件名不一致", joined)
        self.assertIn("来源不是规定的三种之一", joined)
        self.assertIn("F12 只写了“已检查”", joined)
        self.assertIn("`OrderService`", joined)


class Lint(Base):
    def test_hits(self) -> None:
        f = self.tmp / "01.md"
        write(f, """
            # 01 · 下单
            ## 二、为什么必须先锁库存
            修正补充：此前理解有误。
            1. **锁定库存**：先把库存钉死。
            **并发情况**：两个请求同时到达。
            **注意事项**：别忘了。
            明确了上述机制之后，本节继续。
            ```
            钉死 修正补充
            ```
            """)
        data = json.loads(run("lint", "--file", str(f), "--words", "抓牢", "--json").stdout)
        ids = sorted({h["id"] for h in data["hits"]})
        self.assertEqual(ids, ["M01", "R07", "R23", "R33", "R40"])
        self.assertEqual(sum(1 for h in data["hits"] if h["id"] == "R07"), 1, "代码块内不计")
        self.assertEqual([h["match"] for h in data["hits"] if h["id"] == "R23"], ["注意事项"])


class RenderRevise(NotesFixture):
    def test_render(self) -> None:
        n = self.notes()
        write(n / "_工作区" / "_勘察结果.md", "| 仓库路径 | D:/demo |\n| 源码基准提交 | abc1234def |\n")
        r = run("render-revise", "--notes", str(n), "--repo-name", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (n / "修改已有笔记-demo.md").read_text(encoding="utf-8")
        self.assertNotIn("{{", text)
        self.assertIn("`D:/demo` @ `abc1234def`", text)
        self.assertIn("| C23 |", text)
        self.assertIn("| M08 |", text)
        self.assertIn("#### 附录 A", text)
        self.assertIn("## 三、用户追加区", text)
        self.assertEqual(run("render-revise", "--notes", str(n), "--repo-name", "demo").returncode, 1)


class Progress(NotesFixture):
    def test_progress(self) -> None:
        n = self.notes()
        h = commit(n, "S002 取证 01")
        v = self.tmp / "v"
        write(v / "步骤总览.md", f"""
            | S-ID | 目标 | 状态 | checkpoint |
            |---|---|---|---|
            | S001 | 环境确认 | 已完成 | {h} |
            | S002 | U-取证 01 | 已完成 | {h} |
            | S003 | U-成文 02 | 已完成 | {h} |
            | S004 | U-校对 01 | 已完成 | 1234567abcdef |
            | S005 | U-收束 | 未开始 | |
            """)
        write(v / "当前状态.md", f"上一步代码 checkpoint：{h}\n")
        data = json.loads(run("progress", "--notes", str(n), "--version-dir", str(v), "--json").stdout)
        joined = "\n".join(data["fail"])
        self.assertIn("S004：提交 1234567abcdef 不在笔记仓中", joined)
        self.assertIn("S004（校对 01）已完成，但产物不存在", joined)
        self.assertNotIn("S002", joined)
        self.assertNotIn("S003", joined)


if __name__ == "__main__":
    unittest.main()
