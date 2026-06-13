---
name: slack
description: >-
  Read and write Slack as yourself (User Token). Post messages, @mention people,
  reply in threads, read channel history, search, react. Use when the user wants
  to send/post a Slack message, mention someone in a channel, check or read a
  Slack channel or thread, or search Slack — including private channels they have
  access to.
---

# Slack

Operate Slack through one CLI that prints JSON. Two identities are supported,
chosen per write-command with `--as`:

- `--as user` (**default**) — acts via the `xoxp-` User Token; messages appear as
  **you** (your name/avatar, no APP badge). This is the normal case.
- `--as bot` — acts via the `xoxb-` Bot Token; messages appear as the **app/bot**.
  Only use this when the user explicitly asks to post as the bot. A bot can only
  edit/delete messages **it** sent, and can't see private channels it wasn't
  invited to.

Default to `user`. Never send `--as bot` unless the user asked for the bot identity.

## Running the CLI

Invoke the wrapper (resolves the skill's venv automatically):

```
<skill-dir>/scripts/slack <command> [flags]
```

Every command prints a JSON object. Success → `{"ok": true, ...}`. Failure →
`{"ok": false, "error": "..."}` with a non-zero exit code — read `error` and fix
the inputs rather than retrying blindly.

## First-time setup

If any command returns `"No Slack token found"`, the user must create a Slack App
with **User Token Scopes** and install it, then save the token:

```
slack setup --token xoxp-...            # user identity
slack setup --bot-token xoxb-...        # bot identity (optional; can pass both)
```

Required **user** scopes: `chat:write`, `channels:read`, `groups:read`,
`users:read`, `users:read.email`, `channels:history`, `groups:history`,
`im:write`, `im:history`, `mpim:write`, `search:read`, `reactions:write`. For the
optional **bot** identity, add the matching Bot Token Scopes (at least
`chat:write`). Tokens are stored at `~/.config/slack-skill/config.json` (chmod
600). `$SLACK_USER_TOKEN` / `$SLACK_BOT_TOKEN` also work.

## Commands

- `whoami` — confirm who the token authenticates as.
- `post --channel <#name|ID> --text "..." [--mention <name|email|ID> ...] [--thread <ts>]`
  Post a message. `--mention` is repeatable and is resolved to `<@U...>` and
  prepended to the text. `--thread` replies inside a thread.
- `dm --to <name|email|ID> [--to ...] --text "..." [--mention ...] [--thread <ts>]`
  Send a direct message; repeat `--to` for a group DM.
- `edit --channel <#name|ID> --ts <ts> --text "..."` — edit your own message.
- `delete --channel <#name|ID> --ts <ts>` — delete your own message. **Irreversible —
  confirm with the user before running, and never guess the `ts`.**
- `read --channel <#name|ID> [--limit N]` — recent channel history.
- `thread --channel <#name|ID> --ts <parent_ts>` — replies in a thread.
- `channels [--name X] [--types public_channel,private_channel,mpim,im]` — list or find.
- `users [--name X] [--email X]` — list or resolve a person to a user ID.
- `people [--add name=U...] [--remove name]` — manage the local alias table; with
  no args, lists it.
- `search --query "..." [--limit N]` — search messages.
- `activity [--days N] [--limit N] [--dms] [--context N] [--unread-only]` — recent
  messages that @-mention the user (and DMs with `--dms`). Each match is annotated
  `unread: true|false` (vs. the channel's `last_read`; `--unread-only` filters to
  unread). `--context N` attaches the N thread messages that preceded a mention.
  Always runs as the user (search/read state are user-scoped). Read-only — does
  not mark anything as read. Needs the `search:read` user scope.
- `react --channel <#name|ID> --ts <ts> --emoji thumbsup` — add a reaction.

`--channel` and `--mention` accept a name (resolved automatically; exact match
wins, otherwise first substring match) or a raw ID. For people, prefer an email
when you need an exact match.

### Resolving people (important for `--as bot`)

`--mention` / `--to` resolve in this order: **local alias table → user ID →
email → name search**. The alias table (`~/.config/slack-skill/people.json`,
`name → U...`) is checked first with **no API call** — fast, free, and the
preferred way to refer to frequent contacts.

Both identities (`user` and `bot`) have `users:read` + `users:read.email`, so
alias / ID / email / name all work either way. Still prefer aliases for people you
mention often. When the user gives you a new "name: U..." pairing, persist it:
`slack people --add name=U0XXXX`.

Write commands (`post`, `dm`, `edit`, `delete`, `react`) take `--as user|bot`
(default `user`). The response of `post`/`dm` echoes `sent_as` so you can confirm
which identity was used.

## Example — the core scenario

Post into a private channel and @mention someone:

```
slack post --channel "team-secret" --mention "alice@corp.com" --text "ping — can you review the PR?"
```

The response includes the message `ts` and a `permalink`. Report the permalink
back to the user so they can verify.

## Notes

- Messages are sent **as the user**, not a bot.
- Mentions in Slack use `<@USERID>`, never literal `@name` — always resolve via
  `users`/`--mention`; do not type `@name` into `--text`.
- On a large workspace, name resolution paginates the full user/channel list and
  can be slow; pass an ID directly when you already have one.
- Read output (`read`/`thread`/`search`/`activity`) is humanized: Slack markup
  like `<@U..>` → `@Name`, `<#C..|x>` → `#x`, `<url|label>` → `label`, and HTML
  entities are un-escaped. Message text is for reading, not for re-sending.
