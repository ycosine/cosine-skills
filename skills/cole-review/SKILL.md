---
name: cole-review
description: >-
  Trigger Workbench, formerly Cole, on a GitHub PR in the #dev-review Slack
  channel. Use when the user wants Workbench/Cole to review, review-loop, or
  re-review a pull request — e.g. "let Workbench review this PR", "找 cole
  review", "ask Workbench to re-review <PR>", "re-review". This skill only sends
  the trigger message; it does NOT perform the review itself.
---

# cole-review (Workbench)

Sends the message that makes Workbench start a review, and (optionally) watches
the thread for Workbench's result. Built on the `slack` skill.

## Usage

```
<skill-dir>/scripts/cole <pr-url>          # request a review (the default)
<skill-dir>/scripts/cole --re <pr-url>     # request a RE-review (same thread)
<skill-dir>/scripts/cole --loop <pr-url>   # review loop — rarely needed
<skill-dir>/scripts/cole watch ...         # poll for Workbench's result (see below)
```

- **review** → posts a top-level `@Workbench review <pr-url>` in #dev-review.
  This is the default; use it unless the user asks for something else.
- **re-review** (`--re` / `--re-review`) → replies
  `@Workbench re-review <pr-url>` **inside the PR's existing review thread**
  (located by scanning the channel for the PR link), so Workbench keeps the
  context of the earlier review. Errors if no prior review thread exists — run
  a plain review in that case.
- **review loop** (`--loop`) → posts a top-level
  `@Workbench review loop <pr-url>`. A loop asks Workbench to review **and fix
  the findings itself** (remediate, then re-review). Generally NOT needed —
  only use when the user explicitly asks for a loop / for Workbench to fix the
  issues.

All trigger commands print JSON with `channel`, `ts`, `thread_ts` (the thread
root — for re-review this is the original review's root, not the new reply),
`since` (the trigger ts), a `permalink`, and a ready-to-run `watch_cmd`. Report
the permalink so the user can watch Workbench's response.

The executable is still named `cole` for compatibility with existing habits. A
`workbench` alias may also be used when installed.

## Watching for the result (the standard flow)

After triggering, **launch the watcher in the background** so the agent is
re-invoked with Workbench's review once it lands — don't block the turn:

1. Run the trigger in the foreground; capture `channel`, `thread_ts`, `since`,
   `permalink`. Report the permalink to the user.
2. Run the printed `watch_cmd` (or build it) **with `run_in_background: true`**:

   ```
   <skill-dir>/scripts/cole watch --channel <ch> --thread <thread_ts> \
     --since <since_ts> --github <pr-url> --timeout 600 --interval 30
   ```

   It polls the Slack thread for replies from Workbench (`U0B4LQPNMKQ`) newer
   than `--since`, and — with `--github` — also watches for new PR
   reviews/comments after its baseline. It exits as soon as Workbench responds on
   either channel, or after `--timeout` seconds.
3. When the background command exits, read its JSON and summarize Workbench's
   findings/suggestions for the user.

The watcher's exit JSON:

- `status: "responded"` → `slack_replies` (Workbench's thread messages) and
  `github_new` (reviews/comments newer than when the watch started). Summarize
  these into actionable suggestions.
- `status: "timeout"` → Workbench hasn't answered within the window. Surface
  that and offer to keep watching (re-run with a longer `--timeout`).

`watch` is read-only — it never posts, so it's safe to run/re-run freely (unlike
the triggers). Tune `--delay` to wait before the first poll, `--interval` for
poll cadence, `--timeout` for how long to wait.

## How it identifies the PR / thread

A PR is keyed by `<repo>/pull/<number>` parsed from the URL (so `/pull/310/changes`
and `/pull/310` match the same PR). For `watch` without `--thread`, it scans the
channel's recent top-level messages (default 200) for that key and uses the
newest match as the thread root.

## Defaults & overrides

- Channel: `C0AL1106NJJ` (#dev-review) — `WORKBENCH_CHANNEL`.
- Reviewer: `U0B4LQPNMKQ` (Workbench) — `WORKBENCH_MENTION` (ID or alias).
- Reply detector: `U0B4LQPNMKQ` (Workbench) — `WORKBENCH_USER_ID`.
- Scan depth for watch thread lookup: 200 — `WORKBENCH_HISTORY_LIMIT`.

Legacy `COLE_CHANNEL`, `COLE_MENTION`, `COLE_USER_ID`, and
`COLE_HISTORY_LIMIT` env vars still work as fallbacks.

## Notes

- Posts as **the user** (the team triggers Workbench as themselves), never as a
  bot.
- The trigger is fire-and-forget; use `cole watch` (above) to read back
  Workbench's result. Run the watcher in the background so it doesn't block the
  turn.
- Do not paste extra prose into the URL argument — pass a clean PR link.
