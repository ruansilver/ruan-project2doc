# 子代理 t7-continue

## 1. 启动（2026-11-11T19:03:43.968Z）

- description：T7 旧工程继续生成 开工说明

````text
你是一个加载了 `ruan-project2doc` Skill 的助手。这个 Skill 的文件在 `D:/AI workspace/program/ruan-project2doc/src/ruan-project2doc/`：先完整读 `SKILL.md`，再按它的指引读这次调用需要的 references（至少读它为这种调用类型指明的那几份）。严格按这个 Skill 的规则行事，不凭印象。

用户对你说：

> 继续生成笔记。工程在 `C:/Users/17144/AppData/Local/Temp/p2d-1.6-T7/旧工程-继续生成场景/emg数据平台`。

请只做到“开工检查，并向用户说明你将怎样继续”这一步为止：

- 可以读这个工程里的文件，可以运行 Skill 脚本里的只读命令（`deps`、`consistency`、`progress`；用 `python -X utf8 "D:/AI workspace/program/ruan-project2doc/src/ruan-project2doc/scripts/project2doc.py" <命令>`）。
- **不要推进任何生产步骤**（不研读、不成文、不审读），**不要在这个工程里新建、修改、移动或删除任何文件**，不要运行 `scaffold` 或 `render-revise`，不要 git 提交。
- 把你此刻要对用户说的话，原样写入 `D:/AI workspace/program/ruan-project2doc/src/.work/1.6-验收/T7-规则版本/开工说明-原话.md`（这是你对用户的开工回复全文）。
- 另写 `D:/AI workspace/program/ruan-project2doc/src/.work/1.6-验收/T7-规则版本/开工检查-过程.md`：你读了哪些文件、运行了哪些命令及其关键输出、依据 Skill 的哪条规则得出了开工说明里的每个结论。

最后只回报：两份文件已写好，以及你开工说明的要点（三句话以内）。
````
