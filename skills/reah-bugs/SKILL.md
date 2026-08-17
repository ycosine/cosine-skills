---
name: reah-bugs
description: >-
  Query the Reah "Bug Report" Notion database — find bugs assigned to me, list
  open bugs by status/priority/module/env, show a bug's full detail (incl.
  downloadable screenshots), read/post comments, and count bugs by field. Use
  when the user asks "指派给我的 bug" / "my bugs", "open bugs", "有哪些 bug",
  bug counts/stats, wants a specific Reah bug report's content, or wants to
  comment on a bug.
---

# reah-bugs

Domain wrapper over the sibling `notion-read` skill, hard-wired to the Reah
**Bug Report** database (`29c80c5b5b4d801f8a48df5e7a7cfc06`). JSON out;
failures print `{"ok": false, "error": "..."}` with non-zero exit. All
commands are read-only except `comment`.

## Running the CLI

```
<skill-dir>/scripts/reah-bugs <command> [flags]
```

Requires the `notion-read` skill to sit next to this one (same repo — it
imports its request/token code) and the same token setup
(`~/.config/notion-skill/.env`). "me" additionally needs `NOTION_ME=<uuid>` in
that file (xianjun = `292d872b-594c-81eb-868a-00022c1e0165`). Sanity-check
with `reah-bugs whoami`.

## Commands

- `mine` — bugs assigned to me. **Default = active only**: excludes every
  status in the Notion "Complete" group (Verified / Closed / Duplicated /
  Postpone / Cannot reproduce / Confirm won't fix / Work as intended — read
  live from the schema, so regrouping in Notion just works). Add `--all` to
  include completed, or `--status Verified` etc. for one exact status.
  Status groups: To-do = Open, Re-open; In progress = Fixed, Fixing,
  Stg Verified.
- `list [--owner me|uuid] [--status S] [--priority P] [--severity S]
  [--module M] [--env E] [--limit 50] [--all]` — filtered query, newest first.
- `show <url|id>` — one bug in full: flattened properties + page body as
  markdown (steps to reproduce, screenshots). Screenshot links are live signed
  URLs — `curl -o` them and view the image directly when the bug needs visual
  context.
- `stats [--by status|priority|severity|module|owner|env] [--all]` — counts
  grouped by a field (active-only by default; `--all` = whole DB, ~1000 rows),
  sorted descending.
- `whoami` — verify `NOTION_ME` resolves to the right Notion account.
- `comments <url|id>` — read a bug's comment thread.
- `comment <url|id> "<text>"` — **writes.** Posts as the " Bug Management"
  integration, so the text is auto-prefixed with `【<my name>】` (resolved
  from NOTION_ME) to show who's actually speaking; `--no-prefix` posts
  verbatim. Visible to the whole team and the API cannot delete comments —
  always confirm the exact text with the user before posting unless they
  dictated it verbatim.

## Answering common asks

- "指派给我的 bug / my open bugs" → `mine`
- "我所有的 bug 包括已关闭" → `mine --all`
- "线上(Prd)还有什么 bug" → `list --env Prd`
- "这个 bug 具体什么问题" (with a URL) → `show <url>`; download the screenshot
  if the description alone is ambiguous
- "bug 按模块分布" → `stats --by module`
- "在这个 bug 下回复/评论 X" → confirm wording, then `comment <url> "X"`
- Filtering by reporter (` Created by`) isn't supported server-side — pull
  `list --all --limit 100` and filter the JSON locally.

## Gotchas

- Real property names in this DB are messy — leading spaces and misspellings
  (` Priority`, ` Created by`, `Serverity`, `Proj Moudle`). The CLI already
  maps them; only relevant if you hand-write `notion-read db --filter` JSON.
- Filter values must match the select options exactly (`Open`, `Re-open`,
  `Closed`; `Low/Medium/High`; `Stg/Prd`…). An unknown value returns zero rows,
  not an error — if a filter unexpectedly returns nothing, check spelling via
  `stats --by <field> --all`.
- Screenshot URLs in `show` output are signed S3 links that expire (~1h).
