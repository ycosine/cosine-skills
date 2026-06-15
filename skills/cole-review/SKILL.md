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

## Known limitation: Cole ignores `bot_id` messages

Cole drops any message carrying a `bot_id`. Posts from this `slack` skill use the
"Sine" app's user token, which Slack stamps with that app's `bot_id`
(app_id `A0APG0P0C7Q`, bot_id `B0ATPQB914L`) — so Cole currently does **not**
respond to `cole`-triggered messages, only to manually-typed ones. Verified by
diffing a manual post (no bot_id, Cole responds) vs our API post (has bot_id,
ignored).

The correct fix is on **Cole's side**: ask Cole's maintainer to whitelist our
app/user (app_id `A0APG0P0C7Q` or user `U09KQ7H9DDM`) or relax the bot_id filter.
Once whitelisted, this skill works as-is with no changes. (The browser-session
`xoxc/xoxd` workaround that the team's MCP uses is deliberately avoided here.)

## Notes

- Posts as **the user** (the team triggers Cole as themselves), never as a bot.
- This is fire-and-forget: it does not wait for or read Cole's review.
- Do not paste extra prose into the URL argument — pass a clean PR link.
