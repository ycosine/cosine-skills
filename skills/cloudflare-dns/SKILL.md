---
name: cloudflare-dns
description: >-
  Manage Cloudflare DNS via the Cloudflare API — list zones, list/add/update/
  upsert/delete DNS records (A, AAAA, CNAME, TXT, MX, ...), and export a zone as
  a BIND file. Use when the user wants to point a domain/subdomain at an IP or
  host, add/change/remove a DNS record, check current DNS records, or otherwise
  operate Cloudflare DNS.
---

# cloudflare-dns

One CLI over the Cloudflare v4 API that prints JSON. Success → `{"ok": true, ...}`.
Failure → `{"ok": false, "error": "..."}` with a non-zero exit — read `error`
and fix the inputs rather than retrying blindly. Stdlib Python only; no venv.

## Running the CLI

```
<skill-dir>/scripts/cf-dns <command> [flags]
```

## Setup

Credentials come from a `.env` file (first found wins), or env vars
`CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`:

1. `$CLOUDFLARE_ENV_FILE` (explicit path)
2. `<skill-dir>/.env`
3. `~/.config/cloudflare-skill/.env`

Copy `<skill-dir>/.env.example` to `.env` and fill in the token. Key spellings
are lenient (`api_token`, `accountId`, `CF_API_TOKEN`, ... all work). Only the
token is required; the account ID just scopes `zones` listing. If a command
fails with "No Cloudflare API token found", ask the user for their `.env`. The
token needs **Zone/Zone/Read + Zone/DNS/Edit** permissions. Verify with
`cf-dns verify` → `"status": "active"`.

## Commands

- `verify` — check the token works.
- `zones [--name example.com]` — list zones (`id`, `name`, `status`).
- `records --zone <name|ID> [--type A] [--name www] [--content 1.2.3.4]` —
  list records, optionally filtered.
- `add --zone Z --type A --name www --content 1.2.3.4 [--ttl 300] [--proxied]
  [--priority 10] [--comment "..."]` — create a record.
- `upsert --zone Z --type A --name www --content 1.2.3.4 [...]` — update the
  single record matching type+name, else create it. **Prefer this for "point X
  at Y"** requests — idempotent, no duplicate records. Errors if multiple
  records match (fall back to `update --id`).
- `update --zone Z --id <record_id> [--content ...] [--ttl ...] [--proxied |
  --no-proxied] [--name ...] [--type ...] [--comment ...]` — patch one record
  by ID (get IDs from `records`).
- `delete --zone Z --id <record_id>` (or `--type A --name www` when exactly one
  matches) — **irreversible; confirm with the user before running.**
- `export --zone Z` — full zone as a BIND file (in the `bind` field).

Flag conventions:

- `--zone` accepts a zone name (`example.com`) or a 32-hex zone ID.
- `--name` accepts a relative name (`www`), an FQDN (`www.example.com`), or `@`
  for the zone apex — relative names are auto-qualified against the zone.
- `--ttl 1` (the default) means "automatic". Proxied records always behave as
  automatic TTL.
- `--proxied` routes through Cloudflare (orange cloud) — only meaningful for
  A/AAAA/CNAME. Omit to keep Cloudflare's default (DNS-only on create).

## Example — the core scenario

Point `app.example.com` at a new server IP:

```
cf-dns upsert --zone example.com --type A --name app --content 203.0.113.7 --proxied
```

The response echoes `action` (`created`/`updated`) and the resulting record —
report both back to the user.

## Notes

- DNS changes propagate fast on Cloudflare itself but cached resolvers honor
  the old TTL — mention this when the user asks "why isn't it live yet".
- MX/SRV records need `--priority`; TXT content with spaces must be quoted.
- CNAME at the apex is fine on Cloudflare (flattened automatically).
- Never print the API token in output or commit a `.env` file.
