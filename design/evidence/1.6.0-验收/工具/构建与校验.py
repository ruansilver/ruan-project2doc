"""从已验证的 src 构建 install 成品并写入 install/.release.json（AGENTS.md 第 6 节的哈希算法）。

用法：python -X utf8 构建与校验.py            # 构建 + 写清单 + 回读校验
      python -X utf8 构建与校验.py --check    # 只回读校验，不改任何文件
构建前确认：验收判据满足、回归通过。构建失败或哈希不符时保留原有 install/ 成品。
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path("D:/AI workspace/program/ruan-project2doc")
SRC = ROOT / "src" / "ruan-project2doc"
INSTALL = ROOT / "install"
VERSION = "1.6.0"
DESIGN = ROOT / "design" / "versions" / f"{VERSION}.md"


def norm(data: bytes) -> bytes:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return data.replace(b"\r\n", b"\n")


def design_sha() -> str:
    return hashlib.sha256(norm(DESIGN.read_bytes())).hexdigest()


def artifact_sha(base: Path) -> str:
    acc = b""
    files = sorted((p for p in base.rglob("*") if p.is_file()), key=lambda p: p.relative_to(base).as_posix())
    for f in files:
        rel = f.relative_to(base).as_posix()
        acc += rel.encode("utf-8") + b"\0" + hashlib.sha256(norm(f.read_bytes())).hexdigest().encode() + b"\n"
    return hashlib.sha256(acc).hexdigest()


def check() -> dict:
    rel = json.loads((INSTALL / ".release.json").read_text(encoding="utf-8"))
    base = INSTALL / rel["skill_name"]
    problems = []
    if rel["version"] != VERSION:
        problems.append(f"版本不符：{rel['version']}")
    if rel["design_document"] != f"design/versions/{VERSION}.md":
        problems.append(f"设计文档路径不符：{rel['design_document']}")
    if design_sha() != rel["design_sha256"]:
        problems.append("design_sha256 不符")
    if artifact_sha(base) != rel["artifact_sha256"]:
        problems.append("artifact_sha256 不符")
    bad = [p for p in base.rglob("*") if p.name in {"tests", ".work", ".gitkeep", "__pycache__"} or p.suffix == ".pyc"]
    if bad:
        problems.append(f"成品混入开发文件：{bad}")
    return {"release": rel, "problems": problems}


if "--check" in sys.argv:
    result = check()
    print(json.dumps(result, ensure_ascii=False, indent=1))
    sys.exit(1 if result["problems"] else 0)

# 构建：先构建到临时目录，成功后再替换 install/ruan-project2doc；清单最后才写，失败时原样恢复。
manifest = INSTALL / ".release.json"
old_manifest = manifest.read_bytes() if manifest.exists() else None
staging = INSTALL / f".{VERSION}-staging"
if staging.exists():
    shutil.rmtree(staging)
shutil.copytree(SRC, staging)
for junk in list(staging.rglob("__pycache__")):
    shutil.rmtree(junk)
for junk in list(staging.rglob("*.pyc")):
    junk.unlink()
target = INSTALL / "ruan-project2doc"
backup = INSTALL / "ruan-project2doc.bak-1.5"
if backup.exists():
    shutil.rmtree(backup)


def restore(reason: str) -> None:
    print(f"构建失败：{reason}。恢复原有成品，不更新清单。", file=sys.stderr)
    if target.exists():
        shutil.rmtree(target)
    if backup.exists():
        backup.rename(target)
    if old_manifest is None:
        manifest.unlink(missing_ok=True)
    else:
        manifest.write_bytes(old_manifest)
    sys.exit(1)


try:
    if target.exists():
        target.rename(backup)
    staging.rename(target)
except OSError as error:
    # 替换目录失败（例如文件被占用）：把原成品放回去，不留半成品。
    if not target.exists() and backup.exists():
        backup.rename(target)
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    print(f"构建失败：替换成品目录时出错（{error}）。原有成品已保留，未更新清单。", file=sys.stderr)
    sys.exit(1)
dev_files = [p for p in target.rglob("*") if p.name in {"tests", ".work", ".gitkeep", "__pycache__"} or p.suffix == ".pyc"]
if dev_files:
    restore(f"成品混入开发文件 {dev_files}")
src_files = sorted(p.relative_to(SRC).as_posix() for p in SRC.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
out_files = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
if src_files != out_files:
    restore("成品文件清单与 src 不一致")
if any((SRC / rel).read_bytes() != (target / rel).read_bytes() for rel in src_files):
    restore("成品内容与 src 不一致")
release = {
    "version": VERSION,
    "design_document": f"design/versions/{VERSION}.md",
    "skill_name": "ruan-project2doc",
    "design_sha256": design_sha(),
    "artifact_sha256": artifact_sha(target),
}
manifest.write_text(json.dumps(release, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
result = check()
print(json.dumps(result, ensure_ascii=False, indent=1))
if result["problems"]:
    restore("回读校验不通过：" + "；".join(result["problems"]))
if backup.exists():
    shutil.rmtree(backup)
print(f"构建完成，校验通过：{len(out_files)} 个文件。")
