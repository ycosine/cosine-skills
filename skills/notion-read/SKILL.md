---
name: notion-read
description: >-
  Read Notion content via the official API — fetch any page as markdown, list a
  database's schema, query database rows (e.g. the Reah "Bug Report" / "UI
  Review" databases), and search shared pages. Read-only. Use when the user
  pastes a Notion URL, asks what's in a Notion page/database/table, or wants
  bug-report / spec content pulled from Notion.
---

# notion-read

One read-only CLI over the Notion v1 API. Stdlib Python only; no venv.
JSON out; failures print `{"ok": false, "error": "..."}` with non-zero exit —
read `error` and fix inputs rather than retrying blindly.

## Running the CLI

```
<skill-dir>/scripts/notion-read <command> [flags]
```

## Setup

Token resolution order (first found wins):

1. `NOTION_TOKEN` env var
2. `$NOTION_ENV_FILE` (explicit path to a .env)
3. `<skill-dir>/.env`
4. `~/.config/notion-skill/.env`

Copy `<skill-dir>/.env.example` to `~/.config/notion-skill/.env` and fill in
`NOTION_TOKEN=ntn_...` (an internal-integration token; key spellings
`token` / `notion_api_key` also work). Verify with `notion-read verify`.
The integration must be **connected to** the target page/database in Notion
(page ⋯ menu → Connections), otherwise the API returns "Could not find …".

## Commands

- `verify` — check the token works; prints bot + workspace name.
- `get <url|id>` — auto-detects what the ID is:
  - **page** → prints a JSON header (title, flattened properties) then the
    full body as markdown (recursive blocks, tables, images).
  - **database** → prints the schema (property name → type) and a ready-made
    `db` command hint. A `?v=` param in a Notion URL means it's a database
    view, but you don't need to care — `get` figures it out.
- `db <url|id> [--limit 25] [--filter '<json>'] [--sorts '<json>']` — query
  database rows, newest first by default. Rows come back flattened:
  `{id, url, created, <PropName>: value, ...}`. `--filter`/`--sorts` take raw
  Notion API JSON (property names must match the schema exactly — some Reah
  DB property names have leading spaces, e.g. `" Priority"`; check with `get`
  first).
- `search <query> [--limit 15]` — title search across everything shared with
  the integration; good for finding a database ID when you only know its name.

## URL / ID handling

Accepts full Notion URLs (`notion.so`, `app.notion.com/p/...`, with or without
`?v=...&source=...` junk), dashed UUIDs, or bare 32-hex IDs — the last 32-hex
run in the URL path is the ID.

## Gotchas

- Image/file URLs in output are **signed S3 URLs that expire** (~1h) — use
  them immediately, re-fetch if they 403.
- `ConnectTimeoutError` to `api.notion.com` is usually a cold network path —
  retry once after a few seconds.
- Read-only by design: no create/update/delete endpoints are wired up.
- Known Reah IDs: **Bug Report** DB `29c80c5b5b4d801f8a48df5e7a7cfc06`
  (props: Name / Status / ` Priority` / Server / Serverity / Env / Owner /
  Proj Moudle — sic).
