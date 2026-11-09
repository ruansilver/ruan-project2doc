"""发布一致性检查：install/.release.json 与当前设计文档、成品是否一致（AGENTS.md 第 6 节的哈希算法）。

install/ 为空（尚未发布）时跳过。
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "install" / ".release.json"


def norm(data: bytes) -> bytes:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return data.replace(b"\r\n", b"\n")


def artifact_sha(base: Path) -> str:
    acc = b""
    files = sorted((p for p in base.rglob("*") if p.is_file()), key=lambda p: p.relative_to(base).as_posix())
    for f in files:
        rel = f.relative_to(base).as_posix()
        acc += rel.encode("utf-8") + b"\0" + hashlib.sha256(norm(f.read_bytes())).hexdigest().encode() + b"\n"
    return hashlib.sha256(acc).hexdigest()


@unittest.skipUnless(RELEASE.is_file(), "install/ 尚未发布")
class Release(unittest.TestCase):
    def setUp(self) -> None:
        self.rel = json.loads(RELEASE.read_text(encoding="utf-8"))

    def test_design_hash(self) -> None:
        design = ROOT / self.rel["design_document"]
        self.assertEqual(design.name, f"{self.rel['version']}.md")
        text = design.read_text(encoding="utf-8")
        self.assertIn(f"version: {self.rel['version']}", text.split("---")[1])
        self.assertIn("status: approved", text.split("---")[1])
        self.assertEqual(hashlib.sha256(norm(design.read_bytes())).hexdigest(), self.rel["design_sha256"])

    def test_artifact_hash(self) -> None:
        base = ROOT / "install" / self.rel["skill_name"]
        self.assertEqual(artifact_sha(base), self.rel["artifact_sha256"], "install/ 成品被改动，或 .release.json 过期")

    def test_no_dev_files_in_artifact(self) -> None:
        base = ROOT / "install" / self.rel["skill_name"]
        bad = [p for p in base.rglob("*") if p.name in {"tests", ".work", ".gitkeep", "__pycache__"} or p.suffix == ".pyc"]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
