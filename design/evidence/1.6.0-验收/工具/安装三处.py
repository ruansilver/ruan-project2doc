"""本机重新安装 ruan-project2doc 1.6.0 到三处：先备份旧目录，再整体替换，最后逐字节核对。

用法：python -X utf8 安装三处.py [--check]
  （无参数）执行备份 + 替换 + 核对；--check 只核对三处与成品一致，不改任何文件。
失败时从备份恢复该处，不留下半成品。
"""
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path("D:/AI workspace/program/ruan-project2doc")
ARTIFACT = ROOT / "install" / "ruan-project2doc"
RELEASE = json.loads((ROOT / "install" / ".release.json").read_text(encoding="utf-8"))
BACKUP_ROOT = ROOT / "design" / "evidence" / "1.6.0-验收" / "本机留档（不入库）" / "安装备份-1.5.0"
TARGETS = {
    "claude": Path("C:/Users/17144/.claude/skills/ruan-project2doc"),
    "codex": Path("C:/Users/17144/.codex/skills/ruan-project2doc"),
    "agents": Path("C:/Users/17144/.agents/skills/ruan-project2doc"),
}
CHECK_ONLY = "--check" in sys.argv


def listing(base: Path) -> dict:
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(base.rglob("*")) if p.is_file()}


def norm(data: bytes) -> bytes:
    """AGENTS.md 第 6 节：文本文件先把 \\r\\n 换成 \\n 再取哈希。"""
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return data.replace(b"\r\n", b"\n")


def artifact_sha(base: Path) -> str:
    acc = b""
    files = sorted((p for p in base.rglob("*") if p.is_file()), key=lambda p: p.relative_to(base).as_posix())
    for path in files:
        rel = path.relative_to(base).as_posix()
        acc += rel.encode("utf-8") + b"\0" + hashlib.sha256(norm(path.read_bytes())).hexdigest().encode() + b"\n"
    return hashlib.sha256(acc).hexdigest()


def is_link(path: Path) -> bool:
    st = os.lstat(path)
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def version_of(base: Path) -> str:
    for line in (base / "SKILL.md").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version:"):
            return line.split(":", 1)[1].strip().strip('"')
    return "（没有 version 行）"


def junk_of(base: Path) -> list:
    return [p.relative_to(base).as_posix() for p in base.rglob("*")
            if p.name in {"__pycache__", ".gitkeep"} or p.suffix == ".pyc"]


report = {"artifact": {"files": len(listing(ARTIFACT)), "artifact_sha256": artifact_sha(ARTIFACT),
                       "release_sha256": RELEASE["artifact_sha256"]}, "targets": {}}
assert report["artifact"]["artifact_sha256"] == RELEASE["artifact_sha256"], "成品本身与发布清单不符"
if not CHECK_ONLY:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)

for name, target in TARGETS.items():
    item = {"path": str(target)}
    try:
        assert target.is_dir(), "目标目录不存在"
        assert not is_link(target), "目标目录是链接或联接，停止"
        assert (target / "SKILL.md").is_file(), "目标目录里没有 SKILL.md"
        item["old_version"] = version_of(target)
        old = listing(target)
        item["old_files"] = len(old)
        if CHECK_ONLY:
            new = listing(target)
            item["new_version"] = version_of(target)
            item["identical_to_artifact"] = new == listing(ARTIFACT)
            item["artifact_sha256"] = artifact_sha(target)
            item["junk"] = junk_of(target)
            item["ok"] = (item["identical_to_artifact"] and item["artifact_sha256"] == RELEASE["artifact_sha256"]
                          and item["new_version"] == "1.6.0" and not item["junk"])
            report["targets"][name] = item
            continue
        backup = BACKUP_ROOT / name
        assert not backup.exists(), f"备份已存在，先处理：{backup}"
        shutil.copytree(target, backup)
        assert listing(backup) == old, "备份与旧目录不一致"
        item["backup"] = str(backup)
        item["old_artifact_sha256"] = artifact_sha(target)
        try:
            shutil.rmtree(target)
            shutil.copytree(ARTIFACT, target)
            new = listing(target)
            assert new == listing(ARTIFACT), "替换后文件清单与成品不一致"
            assert artifact_sha(target) == RELEASE["artifact_sha256"], "替换后成品哈希与发布清单不符"
            assert version_of(target) == "1.6.0", "替换后版本不是 1.6.0"
            assert not junk_of(target), "替换后混入开发文件"
        except BaseException:
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(backup, target)
            assert listing(target) == old, "恢复后与备份不一致"
            item["restored"] = True
            raise
        item.update({"new_version": version_of(target), "new_files": len(new),
                     "identical_to_artifact": True, "artifact_sha256": artifact_sha(target),
                     "junk": [], "ok": True})
    except BaseException as error:  # noqa: BLE001  报告并继续下一处
        item["ok"] = False
        item["error"] = f"{type(error).__name__}: {error}"
    report["targets"][name] = item

print(json.dumps(report, ensure_ascii=False, indent=1))
sys.exit(0 if all(t.get("ok") for t in report["targets"].values()) else 1)
