# cosine-skills

个人常用的 Claude Code skills 集合，附带安装脚本。

## 安装

```bash
./install.sh
```

`install.sh` 会（可反复运行，幂等、不覆盖已有配置）：
1. 把 `skills/<name>/` 软链接到 `~/.claude/skills/<name>`（改代码即时生效）；
2. 为声明了 `requirements.txt` 的 skill 建独立 `.venv` 装依赖；
3. 若 `~/.config/slack-skill/{config.json,people.json}` 不存在，从仓库模板铺一份
   （token 留空待填），并打印下一步指引。

环境变量：`CLAUDE_SKILLS_DIR`（软链接目标）、`SLACK_SKILL_DIR`（配置目录）可覆盖。

## 新电脑配置

```bash
git clone <repo-url> && cd cosine-skills
./install.sh
# 填入 Slack token（二选一）：
$EDITOR ~/.config/slack-skill/config.json          # 直接改模板里的 user_token / bot_token
slack setup --token xoxp-... [--bot-token xoxb-...] # 或用命令写入
slack whoami                                        # 验证
```

> 仓库**不含 token**（`config.json` 在 .gitignore 里）。新机器上重新填一次即可；
> token 是 workspace 级的，和旧机器一样。通讯录 `people.json` 会从模板预置
> `xianjun`/`workbench`，可继续 `slack people --add`。

需要 `python3`、`git`。所有频道/用户 ID 等默认值是 workspace 级的，换机器不变。

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

### cole-review（Workbench）
触发 Workbench（原 Cole review 机器人）在 `#dev-review` 审 PR。只发触发消息，不参与 review。
详见 [`skills/cole-review/SKILL.md`](skills/cole-review/SKILL.md)。

```bash
cole https://github.com/ReahPlatform/reah-agent/pull/313         # 请求 review
cole --re https://github.com/ReahPlatform/reah-agent/pull/313    # 在原 thread 里请求 re-review
cole --loop https://github.com/ReahPlatform/reah-agent/pull/313  # review loop（少用）
```
`workbench` 也可作为 `cole` 的命令别名使用。`--re` 会按 `<repo>/pull/<号>` 找到该
PR 的既有 review thread，在其中回复 re-review；`--loop` 是让 Workbench 审完还
自己修问题，一般不需要，仅在明确要求时使用。

### cloudflare-dns
操作 Cloudflare DNS：列 zone、增删改查 DNS 记录（A/AAAA/CNAME/TXT/MX…）、导出
BIND 文件。纯 Python 标准库，无需 venv。详见
[`skills/cloudflare-dns/SKILL.md`](skills/cloudflare-dns/SKILL.md)。

首次使用前：
```bash
cp skills/cloudflare-dns/.env.example skills/cloudflare-dns/.env
$EDITOR skills/cloudflare-dns/.env   # 填 CLOUDFLARE_API_TOKEN（和可选的 ACCOUNT_ID）
cf-dns verify                        # 验证 token
```
Token 在 https://dash.cloudflare.com/profile/api-tokens 创建，权限至少
**Zone/Zone/Read + Zone/DNS/Edit**。`.env` 已在 .gitignore 里，不会入库。

核心场景（幂等，把子域指到新 IP）：
```bash
cf-dns upsert --zone example.com --type A --name app --content 203.0.113.7 --proxied
```

### cloudflare-r2
操作 Cloudflare R2 对象存储：列/建/删 bucket，上传（大文件自动分片、每片失败重试，默认存 SHA-256）、
下载（可校验 SHA-256）、列目录、统计大小、看元数据、删除、生成限时下载链接。纯 Python 标准库，
SigV4 签名自己实现，不需要 aws-cli / rclone。详见 [`skills/cloudflare-r2/SKILL.md`](skills/cloudflare-r2/SKILL.md)。

首次使用前：
```bash
cp skills/cloudflare-r2/.env.example ~/.config/cloudflare-r2-skill/.env
$EDITOR ~/.config/cloudflare-r2-skill/.env   # 填 CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_R2_API_TOKEN
cf-r2 selftest                               # 不需要凭证：校验签名算法
cf-r2 verify                                 # 验证 token 与 S3 密钥
```
Token 在控制台 R2 → Manage API tokens → Create Account API token 创建，权限 **Admin Read & Write**。
S3 密钥由 token 推导（Access Key ID = token id，Secret = token 值的 SHA-256），一个 token 就够。
**DNS skill 的 token 没有 R2 权限**，两者分开配置。

核心场景：
```bash
cf-r2 put backups daily/2026-09-27.db.zst ./2026-09-27.db.zst
cf-r2 get backups daily/2026-09-27.db.zst --out /tmp/x.zst --verify
```

### chrome-access
用 Chrome DevTools Protocol（CDP）驱动本地 Chrome：读 DOM、跑 JS、抓无障碍树、
点击/填表/导航、截图。纯指令 skill（无脚本依赖）。详见
[`skills/chrome-access/SKILL.md`](skills/chrome-access/SKILL.md)。

### wt
配合 [wt](https://github.com/ycosine/wt) CLI 管理 git worktree：建工作区
（`wt new`）、读状态（`wt list --json`）、归档/恢复/删除、跑仓库配置的 run 钩子。
纯指令 skill（无脚本依赖），需要先安装 wt 二进制（`cargo install --path .`）。
详见 [`skills/wt/SKILL.md`](skills/wt/SKILL.md)。

### notion-read
只读 Notion API 通用 CLI：`get`（page→markdown / database→schema，自动识别）、
`db`（查数据库行，属性拍平）、`search`。纯 Python 标准库，无需 venv。详见
[`skills/notion-read/SKILL.md`](skills/notion-read/SKILL.md)。

首次使用前：
```bash
mkdir -p ~/.config/notion-skill
cp skills/notion-read/.env.example ~/.config/notion-skill/.env
$EDITOR ~/.config/notion-skill/.env   # 填 NOTION_TOKEN（internal integration token）
notion-read verify                    # 验证 token
```
Integration 需要在 Notion 里被「连接」到目标页面/数据库才能读到。

### reah-bugs
Reah「Bug Report」数据库（Notion）的领域 CLI，复用 notion-read 底层：
`mine`（指派给我的活跃 bug）、`list`（按 status/priority/module/env 筛）、
`show`（属性+复现步骤+截图）、`stats`、`comments`/`comment`（唯一写命令，
自动加【本人名】前缀）。需在 `~/.config/notion-skill/.env` 额外配
`NOTION_ME=<自己的 Notion user uuid>`，用 `reah-bugs whoami` 验证。详见
[`skills/reah-bugs/SKILL.md`](skills/reah-bugs/SKILL.md)。
