---
name: notify-me
description: >-
  Notify the user (xianjun) on Slack — post a message to their notification
  channel and @-mention them so they get a real ping. Use whenever you need to
  record or flag information for the user, send a status/result/heads-up, surface
  something that needs their attention, or report that a long task finished —
  including when the user says "notify me", "ping me", "tell me on Slack", "let me
  know on Slack", or "log this to Slack".
---

# notify-me

A thin convenience layer over the `slack` skill with the target pre-wired, so a
notification is a single call — no need to look up channels or user IDs.

## Usage

```
<skill-dir>/scripts/notify-me <message>
```

By default it posts to the user's notification channel **as the bot** and
**@-mentions the user** so it actually pings. Pass `--no-mention` for a quiet
note (logged, no ping):

```
notify-me The nightly migration finished — 1,204 rows updated.
notify-me --no-mention Heads-up: I started the long backfill, will ping when done.
```

The underlying call prints JSON; a `"ok": true` with a `permalink` means it
landed. Surface the permalink to the user only if they ask.

## Defaults & overrides

- Channel: `C0APEL4986R` (#mole-tasks) — override with `NOTIFY_CHANNEL`.
- Mentions: `U09KQ7H9DDM` (xianjun) — override with `NOTIFY_USER_ID`.
- Identity: `bot` (mole) — override with `NOTIFY_AS=user`.

## When to use this vs. the `slack` skill directly

- Use **notify-me** when the goal is simply *"tell/ping me"* — one message to the
  user. It owns the where/who.
- Use the **slack** skill when you need to target a specific channel/person,
  read, search, reply in a thread, edit, or delete.

## Notes

- Keep messages short and self-contained — they're a ping, not a report. Lead
  with the outcome.
- This is fire-and-forget: it does not wait for or read the user's reply.
