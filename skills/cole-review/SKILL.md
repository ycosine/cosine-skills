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

Sends the message that makes Cole start a review, and (optionally) watches the
thread for Cole's result. Built on the `slack` skill.

## Usage

```
<skill-dir>/scripts/cole <pr-url>          # request a review
<skill-dir>/scripts/cole --re <pr-url>     # request a RE-review
<skill-dir>/scripts/cole watch ...         # poll for Cole's result (see below)
```

- **review** → posts a top-level `@Cole review <pr-url>` in #dev-review. Cole
  claims it and posts results back in the thread.
- **re-review** (`--re` / `--re-review`) → finds the PR's existing review thread
  in the channel and posts `@Cole re-review` **inside that thread** (matching how
  the team does it). Errors if no prior review thread is found — in that case do a
  plain review instead.

Both trigger commands print JSON with `channel`, `ts`, `thread_ts`, `since` (the
trigger ts), a `permalink`, and a ready-to-run `watch_cmd`. Report the permalink
so the user can watch Cole's response.

## Watching for the result (the standard flow)

After triggering, **launch the watcher in the background** so the agent is
re-invoked with Cole's review once it lands — don't block the turn:

1. Run the trigger in the foreground; capture `channel`, `thread_ts`, `since`,
   `permalink`. Report the permalink to the user.
2. Run the printed `watch_cmd` (or build it) **with `run_in_background: true`**:

   ```
   <skill-dir>/scripts/cole watch --channel <ch> --thread <thread_ts> \
     --since <since_ts> --github <pr-url> --timeout 600 --interval 30
   ```

   It polls the Slack thread for replies from Cole (`U0AKFDZUYKH`) newer than
   `--since`, and — with `--github` — also the PR's reviews/comments (Cole's
   GitHub login is `cole-reahai`). It exits as soon as Cole responds on either
   channel, or after `--timeout` seconds.
3. When the background command exits, read its JSON and summarize Cole's
   findings/suggestions for the user.

The watcher's exit JSON:

- `status: "responded"` → `slack_replies` (Cole's thread messages) and
  `github_new` (reviews/comments newer than when the watch started). Summarize
  these into actionable suggestions.
- `status: "timeout"` → Cole hasn't answered within the window. Surface that and
  offer to keep watching (re-run with a longer `--timeout`).

`watch` is read-only — it never posts, so it's safe to run/re-run freely (unlike
the triggers). Tune `--delay` to wait before the first poll, `--interval` for
poll cadence, `--timeout` for how long to wait.

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
- The trigger is fire-and-forget; use `cole watch` (above) to read back Cole's
  result. Run the watcher in the background so it doesn't block the turn.
- Do not paste extra prose into the URL argument — pass a clean PR link.
