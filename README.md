# Personal Skills

个人常用的 Claude Code skills 集合，附带安装脚本。

## 安装

```bash
./install.sh
```

会把 `skills/<name>/` 软链接到 `~/.claude/skills/<name>`（改代码即时生效），
并为声明了 `requirements.txt` 的 skill 创建独立的 `.venv` 安装依赖。

环境变量 `CLAUDE_SKILLS_DIR` 可覆盖目标目录。

## Skills

### slack
读写 Slack：发消息、@某人、私信、编辑/删除、回线程、读频道历史、搜索、加表情。
默认以**你本人**身份（User Token, `xoxp-`）发言；写命令可加 `--as bot` 改用
**bot** 身份（Bot Token, `xoxb-`）。详见 [`skills/slack/SKILL.md`](skills/slack/SKILL.md)。

首次使用前：
1. 在 Slack 建一个 App → **OAuth & Permissions** → 加 **User Token Scopes**
   （`chat:write`, `channels:read`, `groups:read`, `users:read`,
   `users:read.email`, `channels:history`, `groups:history`, `im:write`,
   `im:history`, `mpim:write`, `search:read`, `reactions:write`）
   → Install to Workspace（可能需管理员批准）。
2. 复制 `User OAuth Token`（`xoxp-...`）。
3. `~/.claude/skills/slack/scripts/slack setup --token xoxp-...`

可选：若想保留「以 bot 身份发」的能力，在同一个 App 里配好 Bot Token Scopes
（至少 `chat:write`），复制 `Bot User OAuth Token`（`xoxb-...`），追加保存：
`... slack setup --bot-token xoxb-...`（可与 `--token` 同时传）。发送时用
`--as bot` 切换，默认 `--as user`。

核心场景：
```bash
slack post --channel "team-secret" --mention alice@corp.com --text "ping"
```

查最近谁 @ 我（需 user token 有 `search:read`）：
```bash
slack activity --days 7         # 近 7 天 @ 我的消息
slack activity --days 7 --dms   # 再带上发给我的私信
```

### notify-me
建立在 `slack` 之上的便利层：固定好「通知谁、发到哪」，一句话就能在 Slack 上
@提醒你。用于「通知我 / ping 我 / 把这条记到 Slack」等场景。详见
[`skills/notify-me/SKILL.md`](skills/notify-me/SKILL.md)。

```bash
notify-me 夜间迁移完成，更新了 1204 行
notify-me --no-mention 已开始长任务，完成后再 @ 你   # 只记录、不 @
```
默认发到 `#mole-tasks` 并 @ 你；可用 `NOTIFY_CHANNEL` / `NOTIFY_USER_ID` /
`NOTIFY_AS` 覆盖。

### cole-review（cole）
触发 Cole（review 机器人）在 `#dev-review` 审 PR。只发触发消息，不参与 review。
详见 [`skills/cole-review/SKILL.md`](skills/cole-review/SKILL.md)。

```bash
cole https://github.com/ReahPlatform/reah-agent/pull/313        # 请求 review
cole --re https://github.com/ReahPlatform/reah-agent/pull/313   # 在原 thread 里请求 re-review
```
re-review 会按 `<repo>/pull/<号>` 找到该 PR 的既有 review thread，在其中回复。
