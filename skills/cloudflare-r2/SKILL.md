---
name: cloudflare-r2
description: Manage Cloudflare R2 object storage — list/create/delete buckets, and upload (multipart for big files, per-part retries), download (with sha256 verification), list, size up, inspect, delete, and presign objects. Use when the user wants to put a file or backup into R2, fetch something from R2, check what's in a bucket or how big it is, create an R2 bucket, or share an R2 object via a temporary link.
---

# cloudflare-r2

One CLI that prints JSON. Success → `{"ok": true, ...}`. Failure →
`{"ok": false, "error": "..."}` with a non-zero exit — read `error` and fix
the inputs rather than retrying blindly. Stdlib Python only; no venv, no
aws-cli/rclone needed (SigV4 is implemented in the script).

## Running the CLI

```
<skill-dir>/scripts/cf-r2 <command> [flags]
```

## Setup

Credentials come from the environment or a `.env` (first found wins):
`$CLOUDFLARE_R2_ENV_FILE`, `<skill-dir>/.env`, `~/.config/cloudflare-r2-skill/.env`.
Copy `<skill-dir>/.env.example`. Needed:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_R2_API_TOKEN` — a token with R2 read/write (dashboard → R2 →
  Manage API tokens → Create Account API token → Admin Read & Write). The S3
  key pair is derived from it, so it covers everything.

The DNS skill's token does **not** have R2 permissions — this skill has its
own credentials. If a command fails with "CLOUDFLARE_R2_API_TOKEN missing",
ask the user for the token. Check with `cf-r2 verify`.

`cf-r2 selftest` needs no credentials: it checks the request signer against
AWS's documented SigV4 example.

## Commands

- `verify` — token status, can it list buckets, do the S3 keys work.
- `buckets` — list buckets.
- `create-bucket <bucket> [--location apac|wnam|enam|weur|eeur|oc]`
- `delete-bucket <bucket>` — bucket must be empty. **Irreversible; confirm
  with the user first.**
- `ls <bucket> [--prefix P] [--delimiter /]` — list objects (all pages).
- `du <bucket> [--prefix P]` — object count and total bytes.
- `put <bucket> <key> <file> [--content-type T] [--no-sha256]` — upload.
  Files over 100 MiB go multipart (64 MiB parts, each retried on network
  errors / 5xx; a failed upload is aborted, not left dangling). By default
  the file's SHA-256 is stored as `x-amz-meta-sha256`.
- `get <bucket> <key> --out FILE [--verify]` — download to `FILE.part`, then
  rename; `--verify` checks the stored SHA-256.
- `head <bucket> <key>` — size, etag, last-modified, custom metadata.
- `rm <bucket> <key>` — **irreversible; confirm with the user first.**
- `presign <bucket> <key> [--expires 3600]` — time-limited GET URL (max 7 days).

## Example — back up a file

```
cf-r2 put backups daily/2026-09-27.db.zst /path/2026-09-27.db.zst
cf-r2 get backups daily/2026-09-27.db.zst --out /tmp/check.zst --verify
```

Report `bytes`, `parts` and `mb_per_s` from the upload result.

## Notes

- Endpoint: `https://<account_id>.r2.cloudflarestorage.com` (path-style).
- Behind the GFW, set `HTTPS_PROXY=http://host:port` (urllib supports HTTP
  proxies, not SOCKS).
- R2 egress is free; storage is billed per GB-month (10 GB free).
- Never print the token or secret key, or commit a `.env`.
