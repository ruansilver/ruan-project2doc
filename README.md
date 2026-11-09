# ruan-project2doc

`ruan-project2doc` 这个 Agent Skill 的开发仓库。仓库按「设计、开发、交付」三个目录组织，方便跨设备、跨 AI 会话长期维护。

## 目录

| 路径 | 内容 |
|---|---|
| `design/` | 各版本的设计文档，目标版本以其中最新的已确认（`approved`）版本为准 |
| `src/` | 开发源码（`src/ruan-project2doc/`）、长期测试（`src/tests/`） |
| `install/` | 当前正式发布的、可直接复制安装的 Skill；未发布时为空 |
| `AGENTS.md` | AI 维护约定，规则以它为准 |

## 开始开发

1. 新建 `design/versions/<版本号>.md`，开头写 frontmatter（`version: <版本号>`、`status: draft`），写下这一版要做什么；经你确认后把 `status` 改为 `approved`。详细规则见 `AGENTS.md` 第 3 节，格式可参考 `design/versions/1.4.0.md`。
2. 让 AI 助手阅读 `AGENTS.md`，再说「按最新设计版本开始开发」。它会先核对设计、源码和成品的状态再动手。
3. 验收通过后，AI 助手才会从 `src/` 构建 `install/`。

## 安装成品

`install/ruan-project2doc/` 出现后，把整个目录复制到你的 AI 工具的 Skills 目录即可。`install/` 为空说明尚未正式发布，不要安装 `src/` 中的内容。

## 用 GitHub 同步

这个仓库已准备好直接纳入 Git。关联远程仓库、推送和打 Tag 由你自己决定，AI 助手需要你明确授权才会执行。
