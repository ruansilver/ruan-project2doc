"""把本会话发给子代理的提示词（Agent 调用与 SendMessage）按代理名导出成 Markdown，作为“读者输入范围”的留档。

用法：python -X utf8 导出子代理提示词.py <会话记录.jsonl> <输出目录>
只读会话记录；每次运行整体重写输出目录里的 *.md。
"""
import json
import sys
from collections import OrderedDict
from pathlib import Path


def tool_uses(node):
    """在一条记录里递归找出所有 tool_use 块。"""
    if isinstance(node, dict):
        if node.get("type") == "tool_use" and isinstance(node.get("input"), dict):
            yield node
        for value in node.values():
            yield from tool_uses(value)
    elif isinstance(node, list):
        for value in node:
            yield from tool_uses(value)


def main():
    source = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    agents = OrderedDict()   # 名称 -> 条目列表
    seen = set()
    with source.open(encoding="utf-8") as stream:
        for raw in stream:
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if record.get("isSidechain"):
                continue
            stamp = record.get("timestamp", "")
            for block in tool_uses(record):
                if block.get("id") in seen:
                    continue
                seen.add(block.get("id"))
                data = block["input"]
                if block.get("name") == "Agent":
                    name = data.get("name") or data.get("description") or "未命名"
                    agents.setdefault(name, []).append({
                        "kind": "启动",
                        "time": stamp,
                        "meta": {k: data.get(k) for k in ("description", "subagent_type", "model") if data.get(k)},
                        "text": data.get("prompt", ""),
                    })
                elif block.get("name") == "SendMessage":
                    name = data.get("to") or "未知"
                    message = data.get("message")
                    if not isinstance(message, str):
                        message = json.dumps(message, ensure_ascii=False)
                    agents.setdefault(name, []).append({
                        "kind": "续发消息",
                        "time": stamp,
                        "meta": {"summary": data.get("summary")} if data.get("summary") else {},
                        "text": message,
                    })

    index = ["# 子代理提示词导出", "",
             "从会话记录导出的原始提示词：每个子代理一份文件，按时间顺序列出启动提示词和之后的续发消息。",
             "独立读者能接触到的输入，就是这里的提示词所指明的文件。", "",
             "| 子代理 | 启动 | 续发消息 | 模型 | 文件 |", "|---|---|---|---|---|"]
    for name, items in agents.items():
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
        lines = [f"# 子代理 {name}", ""]
        for no, item in enumerate(items, 1):
            lines.append(f"## {no}. {item['kind']}（{item['time']}）")
            lines.append("")
            for key, value in item["meta"].items():
                lines.append(f"- {key}：{value}")
            if item["meta"]:
                lines.append("")
            lines.append("````text")
            lines.append(item["text"].rstrip())
            lines.append("````")
            lines.append("")
        (out_dir / f"{safe}.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
        starts = sum(1 for item in items if item["kind"] == "启动")
        models = sorted({item["meta"].get("model") for item in items if item["meta"].get("model")})
        index.append(f"| {name} | {starts} | {len(items) - starts} | {'、'.join(models) or '继承主会话'} | `{safe}.md` |")
    (out_dir / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(agents)} 个子代理，{sum(len(v) for v in agents.values())} 条提示词 -> {out_dir}")


if __name__ == "__main__":
    main()
