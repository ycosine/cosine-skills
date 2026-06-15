---
name: cole-review
description: >-
  Trigger Cole (the code-review bot) on a GitHub PR in the #dev-review Slack
  channel. Use when the user wants Cole to review or re-review a pull request —
  e.g. "let Cole review this PR", "找 cole review", "ask cole to re-review
  <PR>", "re-review". This skill only sends the trigger message; it does NOT
  perform the review itself.
---

# cole-review (cole)

Sends the message that makes Cole start a review. Built on the `slack` skill.

## Usage

```
<skill-dir>/scripts/cole <pr-url>          # request a review
<skill-dir>/scripts/cole --re <pr-url>     # request a RE-review
```

- **review** → posts a top-level `@Cole review <pr-url>` in #dev-review. Cole
  claims it and posts results back in the thread.
- **re-review** (`--re` / `--re-review`) → finds the PR's existing review thread
  in the channel and posts `@Cole re-review` **inside that thread** (matching how
  the team does it). Errors if no prior review thread is found — in that case do a
  plain review instead.

The command prints JSON with the message `ts`/`thread_ts` and a `permalink`.
Report the permalink so the user can watch Cole's response.

## How it identifies the PR / thread

A PR is keyed by `<repo>/pull/<number>` parsed from the URL (so `/pull/310/changes`
and `/pull/310` match the same PR). For re-review it scans the channel's recent
top-level messages (default 200) for that key and uses the newest match as the
thread root.

## Defaults & overrides

- Channel: `C0AL1106NJJ` (#dev-review) — `COLE_CHANNEL`.
- Reviewer: `U0AKFDZUYKH` (Cole) — `COLE_MENTION` (ID or alias).
- Scan depth for re-review: 200 — `COLE_HISTORY_LIMIT`.

## Requires a bot-less token (important)

Cole ignores any message that carries a `bot_id`. A user token from a Slack app
that has a **bot user** (like the "Sine" app used by the `slack` skill) stamps
`bot_id` on every post, so Cole silently drops it — even though the message is
"from you". Verified by diffing a working manual post vs an API post.

The fix: post with a `trigger_token` — a user token (`xoxp-`) from a **separate
app that has ONLY User Token Scopes and no bot user**. Such posts carry `app_id`
but no `bot_id`, so Cole responds (this is how the team's own sending tool works).
Set it in `~/.config/slack-skill/config.json` → `trigger_token` (or `COLE_TOKEN`
env). Required scopes on that app: `chat:write`, `groups:read`, `groups:history`,
`channels:read`, `channels:history`. Without it, `cole` warns and Cole will
ignore the message.

## Notes

- Posts as **the user** (the team triggers Cole as themselves), never as a bot.
- This is fire-and-forget: it does not wait for or read Cole's review.
- Do not paste extra prose into the URL argument — pass a clean PR link.
