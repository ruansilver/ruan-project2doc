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
        self.assertIn('version: "1.5.0"', text.split("---")[1])
        desc = next(line for line in text.splitlines() if line.startswith("description:"))
        self.assertLessEqual(len(desc) - len("description: "), 1024)
        for ref in ["定位与标杆", "讲解规范", "表达规范", "篇目规划", "生产流程与交接物", "质量门",
                    "project-map借鉴", "修改协议", "需求包规格"]:
            self.assertTrue((SKILL / "references" / f"{ref}.md").is_file(), ref)
            self.assertIn(f"references/{ref}.md", text, f"SKILL.md 没有指向 {ref}")
        for tpl in ["链路篇", "机制专题篇", "00-系统总览与阅读路线", "99-复核说明", "修改已有笔记",
                    "_勘察结果", "_规划方案", "_术语表", "_衔接约定", "_研读", "_审读记录", "_问题台账",
                    "需求包-00-任务说明", "需求包-02-步骤拆分要求"]:
            self.assertTrue((SKILL / "templates" / f"{tpl}.md").is_file(), tpl)

    def test_retired_files_are_absent(self) -> None:
        for name in ["写作规范", "问题清单", "自检清单", "校对协议", "约束取舍表", "概念定义", "编排与交接物"]:
            self.assertFalse((SKILL / "references" / f"{name}.md").exists(), name)
        for name in ["单篇笔记", "_拆分方案", "_事实", "_校对记录", "00-总览与主线地图"]:
            self.assertFalse((SKILL / "templates" / f"{name}.md").exists(), name)

    def test_operational_rules_are_stack_neutral(self) -> None:
        for name in ["project-map借鉴", "生产流程与交接物", "修改协议", "需求包规格"]:
            text = (SKILL / "references" / f"{name}.md").read_text(encoding="utf-8")
            for word in ["@Scheduled", "RocketMQ", "MinIO", "MyBatis", "Controller"]:
                self.assertNotIn(word, text, f"{name} 含技术栈专用规则 {word}")


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
        for p in ["笔记/00-系统总览与阅读路线.md", "笔记/99-复核说明.md", "笔记/_工作区/_规划方案.md", "需求包/00-任务说明.md", "需求包/02-步骤拆分要求.md",
                  "需求包/规则/讲解规范.md", "需求包/规则/质量门.md", "需求包/模板/链路篇.md",
                  "需求包/模板/机制专题篇.md", "需求包/模板/_研读.md", "需求包/模板/_审读记录.md",
                  "需求包/模板/00-系统总览与阅读路线.md", "需求包/工具/project2doc.py"]:
            self.assertTrue((proj / p).is_file(), p)
        for name in ["_研读", "_审读记录"]:
            directory = proj / "笔记" / "_工作区" / name
            self.assertTrue(directory.is_dir())
            self.assertEqual(list(directory.iterdir()), [], "脚手架不能冒充已经研读或审读")
        for p in ["笔记/_工作区/_拆分方案.md", "笔记/_工作区/_事实", "笔记/_工作区/_校对记录",
                  "需求包/模板/单篇笔记.md", "需求包/规则/问题清单.md", "需求包/模板/需求包-00-任务说明.md"]:
            self.assertFalse((proj / p).exists(), p)
        plan = proj / "笔记" / "_工作区" / "_规划方案.md"
        plan.write_text("用户内容", encoding="utf-8")
        overview = proj / "笔记" / "00-系统总览与阅读路线.md"
        overview.write_text("用户总览", encoding="utf-8")
        second = run("scaffold", "--project", str(proj), "--repo-name", "demo", "--json")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(plan.read_text(encoding="utf-8"), "用户内容")
        self.assertEqual(overview.read_text(encoding="utf-8"), "用户总览")
        self.assertEqual(json.loads(second.stdout)["created"], [])

    def test_refuse_inside_git_repo(self) -> None:
        git(self.tmp, "init", "-q")
        proj = self.tmp / "x-笔记工程"
        r = run("scaffold", "--project", str(proj), "--repo-name", "x")
        self.assertEqual(r.returncode, 2)
        self.assertFalse(proj.exists())

    def test_copied_script_works_from_package(self) -> None:
        proj = self.tmp / "p"
        r = run("scaffold", "--project", str(proj), "--repo-name", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([sys.executable, str(proj / "需求包" / "工具" / "project2doc.py"), "render-revise",
                            "--notes", str(proj / "笔记"), "--repo-name", "demo"], capture_output=True, text=True,
                           encoding="utf-8", env=ENV)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("七问", (proj / "笔记" / "修改已有笔记-demo.md").read_text(encoding="utf-8"))


class NotesFixture(Base):
    def notes(self) -> Path:
        n = self.tmp / "笔记"
        n.mkdir()
        git(n, "init", "-q")
        write(n / "00-系统总览与阅读路线.md", """
            # 00 · demo 总览
            ## 阅读路线与篇目清单
            | 篇号 | 类型 | 标题 |
            |---|---|---|
            | 01 | 链路 | 订单创建 |
            | 02 | 链路 | 订单支付 |
            """)
        write(n / "01-订单创建.md", """
            # 01 · 订单创建
            > 本篇回答：下单请求如何留下待支付订单？
            ## 一、锁定库存后创建订单
            订单服务（`OrderService`）先锁库存，成功后写订单。
            ## 本篇小结
            留下一笔待支付订单，由后续支付请求接手。
            ## 代码地图
            - `src/order.py`：创建订单。
            """)
        write(n / "02-订单支付.md", """
            # 02 · 订单支付
            > 本篇回答：待支付订单怎样变为已支付？
            ## 一、接收支付结果
            订单服务（`OrderService`）处理回调，改变状态。
            ## 本篇小结
            订单已支付。
            """)
        write(n / "99-复核说明.md", "# 99 · 复核说明\n源码基准和未展开入口见本页。\n")
        w = n / "_工作区"
        write(w / "_勘察结果.md", "| 仓库路径 | D:/demo |\n| 源码基准提交 | abc1234def |\n")
        write(w / "_术语表.md", """
            | 术语 | 本项目含义 | 源码名 |
            |---|---|---|
            | 订单服务 | 处理订单 | `OrderService` |
            """)
        write(w / "_衔接约定.md", """
            | 上一篇 | 下一篇 | 交接物 | 状态 |
            |---|---|---|---|
            | 01 | 02 | 待支付订单 | pending |
            """)
        write(w / "_规划方案.md", """
            确认状态：用户已确认
            ## 机制清单
            | 机制 | 级别 | 主讲篇 |
            |---|---|---|
            | 库存锁 | 核心 | 01 |
            | 支付幂等 | 核心 | 02 |
            ## 篇目表
            | 篇号 | 类型 | 标题 |
            |---|---|---|
            | 01 | 链路 | 订单创建 |
            | 02 | 链路 | 订单支付 |
            ## 追问清单
            | 题号 | 篇号 | 机制或判断 | 层次 | 问题 | 核心题 |
            |---|---|---|---|---|---|
            | 01-1 | 01 | 库存锁 | L2 | 哪一步先发生？ | 是 |
            | 02-1 | 02 | 支付幂等 | L2 | 回调怎样改变订单？ | 是 |
            """)
        for nn in ("01", "02"):
            write(w / "_研读" / f"{nn}.md", """
                ## 一、流程走查
                请求进入处理器；执行顺序和来源在 src/order.py 的 create_order 中。
                ## 二、机制卡
                锁定库存后再创建订单，避免并发读取后一起扣减。
                ## 三、关键数据去向
                订单编号由服务生成，交给支付请求使用。
                ## 四、追问与答案草稿
                先锁库存，再创建订单。
                ## 五、设计意图出处
                无意图断言；使用效果型解释。
                ## 六、核对材料
                此夹具只用于检查机械交接，不证明真实业务。
                ## 七、细节去向
                日志字段未展开，留在这里。
                """)
            write(w / "_审读记录" / f"{nn}.md", f"""
                ## G1 追问测试
                | 题号 | 仅凭正文的答案 | 判定 | 正文出处 | 对照理解稿和源码的核对 |
                |---|---|---|---|---|
                | {nn}-1 | 先完成前置检查，再改变订单状态。 | 答得出 | 第一节 | 正确；与夹具的顺序一致。 |
                ## 六道质量门
                | 质量门 | 结论 | 依据 |
                |---|---|---|
                | G1 | 通过 | 上面的逐题结果。 |
                | G2 | 通过 | 第一节机制解释。 |
                | G3 | 通过 | 第一节至小结的数据去向。 |
                | G4 | 通过 | 已在源码位置核对顺序。 |
                | G5 | 通过 | 候选均已人工检查。 |
                | G6 | 通过 | 第一节和小结表达检查。 |
                """)
        write(w / "_问题台账.md", """
            | 编号 | 质量门 | 优先级 | 篇 | 问题 | 源码依据 | 状态 | 处理说明 |
            |---|---|---|---|---|---|---|---|
            | Q-1 | G4 | P1 | 01 | 数字夸大 | src/order.py | closed | 已核对并修正。 |
            """)
        return n


class Consistency(NotesFixture):
    def check(self, notes: Path, *args: str) -> tuple[int, dict]:
        r = run("consistency", "--notes", str(notes), *args, "--json")
        return r.returncode, json.loads(r.stdout)

    def test_good_new_handoffs(self) -> None:
        code, data = self.check(self.notes())
        self.assertEqual(code, 0, data)
        self.assertEqual(data["fail"], [])
        self.assertIn("不能证明", data["scope"])

    def test_real_overview_template_article_table(self) -> None:
        n = self.notes()
        template = (SKILL / "templates" / "00-系统总览与阅读路线.md").read_text(encoding="utf-8")
        rows = template.splitlines()
        placeholders = [i for i, row in enumerate(rows) if row.startswith("| <NN> |")]
        self.assertEqual(len(placeholders), 1, "总览模板应只有一行篇目占位")
        rows[placeholders[0]] = "| 01 | 链路 | 订单创建 | 讲清如何下单 |\n| 02 | 链路 | 订单支付 | 讲清回调 |"
        (n / "00-系统总览与阅读路线.md").write_text("\n".join(rows), encoding="utf-8")
        code, data = self.check(n)
        self.assertEqual(code, 0, data)

    def test_final_requires_all_deliverables(self) -> None:
        n = self.notes()
        code, data = self.check(n, "--final")
        self.assertEqual(code, 1, data)
        self.assertTrue(any("修改提示词" in message for message in data["fail"]))
        write(n / "修改已有笔记-demo.md", "项目修改要求。")
        code, data = self.check(n, "--final")
        self.assertEqual(code, 0, data)

    def test_unwritten_plan_is_allowed_until_final(self) -> None:
        n = self.notes()
        (n / "02-订单支付.md").unlink()
        code, data = self.check(n)
        self.assertEqual(code, 0, data)
        self.assertTrue(any("02" in message for message in data["warn"]))
        code, data = self.check(n, "--final")
        self.assertEqual(code, 1, data)
        self.assertTrue(any("02" in message for message in data["fail"]))

    def test_existing_article_requires_study_and_review(self) -> None:
        n = self.notes()
        (n / "_工作区" / "_研读" / "01.md").unlink()
        (n / "_工作区" / "_审读记录" / "02.md").unlink()
        code, data = self.check(n)
        self.assertEqual(code, 1, data)
        joined = "\n".join(data["fail"])
        self.assertIn("_研读/01.md", joined)
        self.assertIn("_审读记录/02.md", joined)

    def test_review_checks_each_question_and_all_gates(self) -> None:
        n = self.notes()
        f = n / "_工作区" / "_审读记录" / "01.md"
        text = f.read_text(encoding="utf-8")
        text = text.replace("| 01-1 |", "| other |")
        text = "\n".join(line for line in text.splitlines() if not line.startswith("| G6 |"))
        f.write_text(text, encoding="utf-8")
        code, data = self.check(n)
        self.assertEqual(code, 1, data)
        self.assertIn("追问 01-1", "\n".join(data["fail"]))
        self.assertIn("缺少 G6", "\n".join(data["fail"]))

    def test_answered_but_wrong_core_question_fails(self) -> None:
        n = self.notes()
        f = n / "_工作区" / "_审读记录" / "01.md"
        f.write_text(f.read_text(encoding="utf-8").replace("正确；与夹具的顺序一致。", "错误；正文颠倒了顺序。"), encoding="utf-8")
        code, data = self.check(n)
        self.assertEqual(code, 1, data)
        self.assertIn("核心题 01-1", "\n".join(data["fail"]))

    def test_correctness_verdict_ignores_business_explanation(self) -> None:
        n = self.notes()
        review = n / "_工作区" / "_审读记录" / "01.md"
        original = review.read_text(encoding="utf-8")
        for verdict in [
            "正确；错误密码时返回401，与源码一致。",
            "一致：业务状态不一致时拒绝更新。",
            "核对无误（错误由请求处理器接住）。",
            "正确",
            "一致",
            "核对无误",
        ]:
            with self.subTest(verdict=verdict):
                review.write_text(original.replace("正确；与夹具的顺序一致。", verdict), encoding="utf-8")
                code, data = self.check(n)
                self.assertEqual(code, 0, data)

    def test_correctness_verdict_requires_explicit_positive_prefix(self) -> None:
        n = self.notes()
        review = n / "_工作区" / "_审读记录" / "01.md"
        original = review.read_text(encoding="utf-8")
        for verdict in [
            "错误；正文顺序需要修正。",
            "不正确；解释与行为不符。",
            "不一致；返回值有差异。",
            "待核对；还不能确认正确。",
            "待验证；目前看起来与源码一致。",
            "正确性待核对",
            "正确性未知",
            "一致性尚未确认",
        ]:
            with self.subTest(verdict=verdict):
                review.write_text(original.replace("正确；与夹具的顺序一致。", verdict), encoding="utf-8")
                code, data = self.check(n)
                self.assertEqual(code, 1, data)
                self.assertIn("核心题 01-1", "\n".join(data["fail"]))

    def test_noncore_eighty_percent_threshold(self) -> None:
        n = self.notes()
        p = n / "_工作区" / "_规划方案.md"
        plan = p.read_text(encoding="utf-8")
        plan += "".join(f"| 01-extra-{i} | 01 | 日志 | L2 | 日志的去向{i}？ | 否 |\n" for i in range(5))
        p.write_text(plan, encoding="utf-8")
        r = n / "_工作区" / "_审读记录" / "01.md"
        review = r.read_text(encoding="utf-8")
        extra = "".join(f"| 01-extra-{i} | 日志交给输出端。 | {'部分' if i == 0 else '答得出'} | 第一节 | 正确；与源码一致。 |\n" for i in range(5))
        review = review.replace("## 六道质量门", extra + "\n## 六道质量门")
        r.write_text(review, encoding="utf-8")
        code, data = self.check(n)
        self.assertEqual(code, 0, data)
        r.write_text(review.replace("| 01-extra-1 | 日志交给输出端。 | 答得出", "| 01-extra-1 | 日志交给输出端。 | 部分"), encoding="utf-8")
        code, data = self.check(n)
        self.assertEqual(code, 1, data)
        self.assertIn("低于默认 80%", "\n".join(data["fail"]))

    def test_core_mechanism_needs_planned_main_article(self) -> None:
        n = self.notes()
        p = n / "_工作区" / "_规划方案.md"
        p.write_text(p.read_text(encoding="utf-8").replace("| 库存锁 | 核心 | 01 |", "| 库存锁 | 核心 | 09 |"), encoding="utf-8")
        code, data = self.check(n)
        self.assertEqual(code, 1, data)
        self.assertIn("主讲篇不在规划", "\n".join(data["fail"]))

    def test_ledger_and_handoffs(self) -> None:
        n = self.notes()
        l = n / "_工作区" / "_问题台账.md"
        l.write_text(l.read_text(encoding="utf-8").replace("closed", "open"), encoding="utf-8")
        code, data = self.check(n)
        self.assertEqual(code, 0, data)
        self.assertTrue(any("open" in message for message in data["warn"]))
        code, data = self.check(n, "--final")
        self.assertEqual(code, 1, data)
        self.assertTrue(any("open" in message for message in data["fail"]))
        f = n / "02-订单支付.md"
        f.write_text(f.read_text(encoding="utf-8").replace("待支付订单", "订单"), encoding="utf-8")
        code, data = self.check(n)
        self.assertEqual(code, 1, data)
        self.assertIn("第 02 篇开头", "\n".join(data["fail"]))


class Lint(Base):
    def scan(self, text: str) -> dict:
        f = self.tmp / "01.md"
        write(f, text)
        r = run("lint", "--file", str(f), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_g5_source_test_and_process_signals(self) -> None:
        data = self.scan("""
            # 01 · 缓存
            `src/cache.py:42` 和 `src/app.ts#L12`。
            CacheTest、test_refresh、shouldRejectMissingToken。
            本次均未运行；尚无真实容器证据。
            ```python
            # src/cache.py:99 test_ignored 本次未运行
            ```
            <!-- src/cache.py:100 test_comment 本次未运行 -->
            ## 代码地图
            - `src/map.py:12`：这里仍不应带行号。
            """)
        ids = {hit["id"] for hit in data["hits"]}
        self.assertTrue({"G5-行号引用", "G5-测试名称", "G5-取证过程"} <= ids)
        self.assertEqual(sum(hit["id"] == "G5-行号引用" for hit in data["hits"]), 3)
        self.assertEqual(sum(hit["id"] == "G5-测试名称" for hit in data["hits"]), 3)
        self.assertIn("人工阅读", data["scope"])

    def test_tag_count_threshold_and_code_exclusion(self) -> None:
        data = self.scan("# 01\n" + "【推导】" * 3 + "【未确认】" * 2)
        self.assertEqual(data["label_counts"]["total"], 5)
        self.assertNotIn("G5-标签密集", {hit["id"] for hit in data["hits"]})
        data = self.scan("# 01\n" + "【推导】" * 3 + "【未确认】" * 3 + "\n```\n" + "【推导】" * 10 + "\n```\n")
        self.assertEqual(data["label_counts"]["total"], 6)
        self.assertIn("G5-标签密集", {hit["id"] for hit in data["hits"]})

    def test_cross_reference_is_only_a_nearby_signal(self) -> None:
        data = self.scan("""
            # 01 · 登录
            ## 只有参数
            有效期60秒，见第 02 篇。
            ## 有够用讲解的候选
            为了减少读取，先查询本地，再查询共享缓存，查到后回填。
            共享缓存故障时继续读取存储，代价是存储压力增大。
            其他使用点见第 03 篇。
            """)
        hits = [hit for hit in data["hits"] if hit["id"] == "G5-指路代讲"]
        self.assertEqual(len(hits), 1, data)
        self.assertIn("02", hits[0]["match"])
        self.assertEqual(len(data["cross_references"]), 2)
        self.assertTrue(all(data["cross_references"][1]["nearby_signals"].values()))
        self.assertIn("人工确认", data["cross_references"][1]["note"])

    def test_expression_signals_and_migration_context(self) -> None:
        data = self.scan("""
            # 01 · 下单
            ## 必须这样写
            修正补充：此前理解有误，先把库存钉死。
            > **注意事项**：别忘了。
            明确了上述机制之后，本节继续。
            V1、V2、V3。
            > **版本演进**：原先 V1、V2 分别提交数据，为了避免只写一半，现改为一起提交。
            """)
        ids = {hit["id"] for hit in data["hits"]}
        self.assertTrue({"G6-修改痕迹", "G6-用词", "G6-补充标签", "G6-推销式标题", "G6-模板转场"} <= ids)
        self.assertEqual(sum(hit["id"] == "G5-迁移版本列举" for hit in data["hits"]), 1)


class RenderRevise(NotesFixture):
    def test_render_and_preserve_user_append(self) -> None:
        n = self.notes()
        r = run("render-revise", "--notes", str(n), "--repo-name", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        target = n / "修改已有笔记-demo.md"
        text = target.read_text(encoding="utf-8")
        self.assertNotIn("{{", text)
        self.assertIn("D:/demo", text)
        self.assertIn("abc1234def", text)
        self.assertIn("七问", text)
        self.assertIn("面试", text)
        for heading in ["固定规范区", "项目口径区", "用户追加区", "变更记录"]:
            self.assertIn(heading, text)
        target.write_text(text + "\n用户新要求：补讲失败情形。\n", encoding="utf-8")
        before = target.read_bytes()
        self.assertEqual(run("render-revise", "--notes", str(n), "--repo-name", "demo").returncode, 1)
        self.assertEqual(target.read_bytes(), before)


class Progress(NotesFixture):
    def test_new_units_and_checkpoint_validation(self) -> None:
        n = self.notes()
        (n / "_工作区" / "_审读记录" / "01.md").unlink()
        h = commit(n, "S002 研读 01")
        v = self.tmp / "v"
        write(v / "步骤总览.md", f"""
            | S-ID | 目标 | 状态 | checkpoint |
            |---|---|---|---|
            | S001 | 环境确认 | 已完成 | {h} |
            | S002 | U-研读 01 | 已完成 | {h} |
            | S003 | U-成文 02 | 已完成 | {h} |
            | S004 | U-审读 01 | 已完成 | 1234567abcdef |
            | S005 | U-收束 | 未开始 | |
            """)
        write(v / "当前状态.md", f"上一步代码 checkpoint：{h}\n")
        data = json.loads(run("progress", "--notes", str(n), "--version-dir", str(v), "--json").stdout)
        joined = "\n".join(data["fail"])
        self.assertIn("S004：提交 1234567abcdef 不在笔记仓中", joined)
        self.assertIn("S004（审读 01）已完成，但产物不存在", joined)
        self.assertNotIn("S002", joined)
        self.assertNotIn("S003", joined)


if __name__ == "__main__":
    unittest.main()
