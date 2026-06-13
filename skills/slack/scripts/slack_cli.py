#!/usr/bin/env python3
"""Slack CLI — operate Slack as yourself via a User Token (xoxp-).

All commands print a JSON object to stdout so the result is easy to parse.
On success: {"ok": true, ...}. On failure: {"ok": false, "error": "..."} with a
non-zero exit code.

Two identities are supported and chosen per-command with `--as user|bot`
(default: user). Each maps to its own token:
  user -> xoxp- User Token  (messages appear as you)
  bot  -> xoxb- Bot Token    (messages appear as the app/bot)

Token resolution per identity:
  1. --token CLI flag (raw override, ignores --as)
  2. $SLACK_USER_TOKEN / $SLACK_BOT_TOKEN env var
  3. ~/.config/slack-skill/config.json -> {"user_token": "...", "bot_token": "..."}
     (legacy {"token": "..."} is treated as the user token)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError:
    print(
        json.dumps(
            {
                "ok": False,
                "error": "slack_sdk not installed. Run the repo install.sh, or: "
                "pip install slack_sdk",
            }
        )
    )
    sys.exit(1)

CONFIG_PATH = Path.home() / ".config" / "slack-skill" / "config.json"
PEOPLE_PATH = Path.home() / ".config" / "slack-skill" / "people.json"


# --------------------------------------------------------------------------- #
# output helpers
# --------------------------------------------------------------------------- #
def emit(obj: dict, code: int = 0) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    sys.exit(code)


def fail(msg: str, code: int = 1, **extra) -> None:
    emit({"ok": False, "error": msg, **extra}, code)


def clean(text) -> str:
    """Un-escape Slack's HTML entities (&amp; &lt; &gt;) for readable text."""
    return html.unescape(text) if text else text


_RE_USER = re.compile(r"<@([UW][A-Z0-9]+)(?:\|([^>]+))?>")
_RE_CHAN = re.compile(r"<#C[A-Z0-9]+(?:\|([^>]+))?>")
_RE_SUBTEAM = re.compile(r"<!subteam\^[A-Z0-9]+(?:\|([^>]+))?>")
_RE_SPECIAL = re.compile(r"<!(here|channel|everyone)>")
_RE_LINK = re.compile(r"<(https?://[^>|]+)(?:\|([^>]+))?>")


class Humanizer:
    """Render raw Slack message text into readable text: resolve <@ID> to @Name,
    <#C..|name> to #name, links to their label, then un-escape HTML entities.

    Parses the <...> markup BEFORE html.unescape so literal &lt;/&gt; in the body
    are not mistaken for markup. Caches user lookups for the run.
    """

    def __init__(self, client: WebClient):
        self.client = client
        self.cache = {}  # user_id -> display name
        # Reverse the local alias table so known people resolve with no API call.
        for name, uid in load_people().items():
            self.cache.setdefault(uid, name)

    def user_name(self, uid: str) -> str:
        if uid in self.cache:
            return self.cache[uid]
        resp, _ = api_safe(self.client.users_info, user=uid)
        name = uid
        if resp:
            p = resp["user"].get("profile", {})
            name = p.get("display_name") or p.get("real_name") or resp["user"].get("name") or uid
        self.cache[uid] = name
        return name

    def render(self, text):
        if not text:
            return text
        text = _RE_USER.sub(lambda m: "@" + (m.group(2) or self.user_name(m.group(1))), text)
        text = _RE_CHAN.sub(lambda m: "#" + (m.group(1) or "channel"), text)
        text = _RE_SUBTEAM.sub(lambda m: "@" + (m.group(1) or "group"), text)
        text = _RE_SPECIAL.sub(lambda m: "@" + m.group(1), text)
        text = _RE_LINK.sub(lambda m: m.group(2) or m.group(1), text)
        return html.unescape(text)


PERMALINK_RE = re.compile(r"/archives/([A-Z0-9]+)/p\d+.*?thread_ts=([0-9.]+)")


def parse_thread(permalink: str):
    """Return (channel_id, thread_ts) if the permalink points into a thread."""
    m = PERMALINK_RE.search(permalink or "")
    return (m.group(1), m.group(2)) if m else (None, None)


# --------------------------------------------------------------------------- #
# token / client
# --------------------------------------------------------------------------- #
def load_tokens() -> dict:
    """Collect {'user': ..., 'bot': ...} from config file then env (env wins)."""
    tokens: dict = {}
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            if data.get("user_token"):
                tokens["user"] = data["user_token"]
            if data.get("bot_token"):
                tokens["bot"] = data["bot_token"]
            if data.get("token") and "user" not in tokens:  # legacy
                tokens["user"] = data["token"]
        except (json.JSONDecodeError, OSError):
            pass
    if os.environ.get("SLACK_USER_TOKEN"):
        tokens["user"] = os.environ["SLACK_USER_TOKEN"]
    if os.environ.get("SLACK_BOT_TOKEN"):
        tokens["bot"] = os.environ["SLACK_BOT_TOKEN"]
    return tokens


def select_identity(args) -> str:
    return getattr(args, "as_identity", None) or "user"


def get_client(args) -> WebClient:
    raw = getattr(args, "token", None)
    if raw:
        return WebClient(token=raw)
    identity = select_identity(args)
    token = load_tokens().get(identity)
    if not token:
        flag = "--token" if identity == "user" else "--bot-token"
        fail(
            f"No {identity} token configured. Run `slack setup {flag} ...`, "
            f"or set $SLACK_{identity.upper()}_TOKEN.",
            code=2,
        )
    return WebClient(token=token)


def api(fn, **kwargs):
    """Call a slack_sdk method, converting SlackApiError into a clean failure."""
    try:
        return fn(**kwargs)
    except SlackApiError as e:
        err = e.response.get("error", str(e))
        fail(f"Slack API error: {err}", code=1, slack_error=err)


def api_safe(fn, **kwargs):
    """Like api() but returns (response, None) or (None, error_str) instead of exiting."""
    try:
        return fn(**kwargs), None
    except SlackApiError as e:
        return None, e.response.get("error", str(e))


def paginate(fn, key: str, **kwargs):
    """Yield every item across paginated cursor responses."""
    cursor = None
    while True:
        resp = api(fn, cursor=cursor, limit=200, **kwargs)
        yield from resp.get(key, [])
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break


# --------------------------------------------------------------------------- #
# resolvers
# --------------------------------------------------------------------------- #
ID_CHANNEL = re.compile(r"^[CGD][A-Z0-9]{6,}$")
ID_USER = re.compile(r"^[UW][A-Z0-9]{6,}$")


def resolve_channel(client: WebClient, ref: str) -> dict:
    """Accept a channel ID or a (case-insensitive) #name and return the channel."""
    ref = ref.lstrip("#")
    if ID_CHANNEL.match(ref):
        resp = api(client.conversations_info, channel=ref)
        return resp["channel"]
    target = ref.lower()
    fallback = None
    for ch in paginate(
        client.conversations_list,
        "channels",
        types="public_channel,private_channel,mpim,im",
        exclude_archived=True,
    ):
        name = (ch.get("name") or "").lower()
        if name == target:
            return ch
        if fallback is None and target in name:
            fallback = ch
    if fallback:
        return fallback
    fail(f"Channel not found: {ref!r}. Check the name or use the channel ID.")


def load_people() -> dict:
    """Local alias table: {name_lower: user_id}. Underscore keys are ignored."""
    if not PEOPLE_PATH.exists():
        return {}
    try:
        data = json.loads(PEOPLE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        k.lower(): v
        for k, v in data.items()
        if not k.startswith("_") and isinstance(v, str)
    }


def resolve_user(client: WebClient, ref: str) -> dict:
    """Accept a local alias, a user ID, an email, or a name (display/real/handle).

    The alias table is checked first so `@xianjun` resolves to an ID with no API
    call — this is the only path that works for a bot token lacking users:read.
    """
    ref = ref.lstrip("@")
    alias = load_people().get(ref.lower())
    if alias:
        ref = alias
    if ID_USER.match(ref):
        # Enrich with name/profile when the token allows it; otherwise the bare
        # ID is enough to build a <@ID> mention (works without users:read).
        resp, _ = api_safe(client.users_info, user=ref)
        return resp["user"] if resp else {"id": ref}
    if "@" in ref and "." in ref:
        return api(client.users_lookupByEmail, email=ref)["user"]
    target = ref.lower()
    fallback = None
    for u in paginate(client.users_list, "members"):
        if u.get("deleted"):
            continue
        prof = u.get("profile", {})
        names = {
            (u.get("name") or "").lower(),
            (prof.get("display_name") or "").lower(),
            (prof.get("real_name") or "").lower(),
        }
        if target in names:
            return u
        if fallback is None and any(target in n for n in names if n):
            fallback = u
    if fallback:
        return fallback
    fail(f"User not found: {ref!r}. Try their email for an exact match.")


def mention(user: dict) -> str:
    return f"<@{user['id']}>"


def user_brief(u: dict) -> dict:
    p = u.get("profile", {})
    return {
        "id": u["id"],
        "handle": u.get("name"),
        "display_name": p.get("display_name"),
        "real_name": p.get("real_name"),
        "email": p.get("email"),
    }


def channel_brief(c: dict) -> dict:
    return {
        "id": c["id"],
        "name": c.get("name"),
        "is_private": c.get("is_private"),
        "is_member": c.get("is_member"),
    }


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_setup(args):
    if not args.token and not args.bot_token:
        fail("Provide --token xoxp-... and/or --bot-token xoxb-...")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    if "token" in data and "user_token" not in data:  # migrate legacy key
        data["user_token"] = data.pop("token")
    result = {"ok": True, "saved_to": str(CONFIG_PATH), "identities": {}}
    if args.token:
        who = api(WebClient(token=args.token).auth_test)
        data["user_token"] = args.token
        result["identities"]["user"] = {
            "authenticated_as": who.get("user"),
            "user_id": who.get("user_id"),
            "team": who.get("team"),
        }
    if args.bot_token:
        who = api(WebClient(token=args.bot_token).auth_test)
        data["bot_token"] = args.bot_token
        result["identities"]["bot"] = {
            "authenticated_as": who.get("user"),
            "bot_id": who.get("bot_id"),
            "team": who.get("team"),
        }
    CONFIG_PATH.write_text(json.dumps(data, indent=2))
    CONFIG_PATH.chmod(0o600)
    emit(result)


def cmd_whoami(args):
    who = api(get_client(args).auth_test)
    emit(
        {
            "ok": True,
            "identity": select_identity(args),
            "user": who.get("user"),
            "user_id": who.get("user_id"),
            "bot_id": who.get("bot_id"),
            "team": who.get("team"),
            "url": who.get("url"),
        }
    )


def cmd_channels(args):
    client = get_client(args)
    if args.name:
        emit({"ok": True, "channel": channel_brief(resolve_channel(client, args.name))})
    types = args.types or "public_channel,private_channel"
    chans = [
        channel_brief(c)
        for c in paginate(
            client.conversations_list, "channels", types=types, exclude_archived=True
        )
    ]
    emit({"ok": True, "count": len(chans), "channels": chans})


def cmd_users(args):
    client = get_client(args)
    ref = args.name or args.email
    if ref:
        emit({"ok": True, "user": user_brief(resolve_user(client, ref))})
    users = [user_brief(u) for u in paginate(client.users_list, "members") if not u.get("deleted")]
    emit({"ok": True, "count": len(users), "users": users})


def cmd_people(args):
    PEOPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if PEOPLE_PATH.exists():
        try:
            data = json.loads(PEOPLE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    changed = False
    for pair in args.add or []:
        if "=" not in pair:
            fail(f"--add expects name=USERID, got {pair!r}")
        name, uid = pair.split("=", 1)
        if not ID_USER.match(uid.strip()):
            fail(f"{uid.strip()!r} is not a Slack user ID (expected U... / W...)")
        data[name.strip()] = uid.strip()
        changed = True
    for name in args.remove or []:
        data.pop(name, None)
        changed = True
    if changed:
        PEOPLE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        PEOPLE_PATH.chmod(0o600)
    people = {k: v for k, v in data.items() if not k.startswith("_")}
    emit({"ok": True, "path": str(PEOPLE_PATH), "count": len(people), "people": people})


def cmd_post(args):
    client = get_client(args)
    channel = resolve_channel(client, args.channel)
    mentions = []
    for ref in args.mention or []:
        mentions.append(resolve_user(client, ref))
    prefix = " ".join(mention(u) for u in mentions)
    text = f"{prefix} {args.text}".strip() if prefix else args.text
    resp = api(
        client.chat_postMessage,
        channel=channel["id"],
        text=text,
        thread_ts=args.thread,
    )
    emit(
        {
            "ok": True,
            "sent_as": select_identity(args),
            "channel": channel_brief(channel),
            "mentioned": [user_brief(u) for u in mentions],
            "ts": resp["ts"],
            "text": text,
            "permalink": api(
                client.chat_getPermalink, channel=channel["id"], message_ts=resp["ts"]
            ).get("permalink"),
        }
    )


def cmd_dm(args):
    client = get_client(args)
    recipients = [resolve_user(client, ref) for ref in args.to]
    opened = api(client.conversations_open, users=",".join(u["id"] for u in recipients))
    channel_id = opened["channel"]["id"]
    mentions = [resolve_user(client, ref) for ref in args.mention or []]
    prefix = " ".join(mention(u) for u in mentions)
    text = f"{prefix} {args.text}".strip() if prefix else args.text
    resp = api(client.chat_postMessage, channel=channel_id, text=text, thread_ts=args.thread)
    emit(
        {
            "ok": True,
            "sent_as": select_identity(args),
            "channel_id": channel_id,
            "recipients": [user_brief(u) for u in recipients],
            "mentioned": [user_brief(u) for u in mentions],
            "ts": resp["ts"],
            "text": text,
            "permalink": api(
                client.chat_getPermalink, channel=channel_id, message_ts=resp["ts"]
            ).get("permalink"),
        }
    )


def cmd_edit(args):
    client = get_client(args)
    channel = resolve_channel(client, args.channel)
    resp = api(client.chat_update, channel=channel["id"], ts=args.ts, text=args.text)
    emit(
        {
            "ok": True,
            "channel": channel_brief(channel),
            "ts": resp["ts"],
            "text": resp.get("text", args.text),
        }
    )


def cmd_delete(args):
    client = get_client(args)
    channel = resolve_channel(client, args.channel)
    api(client.chat_delete, channel=channel["id"], ts=args.ts)
    emit({"ok": True, "channel": channel_brief(channel), "ts": args.ts, "deleted": True})


def cmd_read(args):
    client = get_client(args)
    hz = Humanizer(client)
    channel = resolve_channel(client, args.channel)
    resp = api(client.conversations_history, channel=channel["id"], limit=args.limit)
    msgs = [
        {"ts": m.get("ts"), "user": m.get("user"), "text": hz.render(m.get("text")),
         "thread_ts": m.get("thread_ts"), "reply_count": m.get("reply_count")}
        for m in resp.get("messages", [])
    ]
    emit({"ok": True, "channel": channel_brief(channel), "count": len(msgs), "messages": msgs})


def cmd_thread(args):
    client = get_client(args)
    hz = Humanizer(client)
    channel = resolve_channel(client, args.channel)
    resp = api(client.conversations_replies, channel=channel["id"], ts=args.ts)
    msgs = [
        {"ts": m.get("ts"), "user": m.get("user"), "text": hz.render(m.get("text"))}
        for m in resp.get("messages", [])
    ]
    emit({"ok": True, "channel": channel_brief(channel), "count": len(msgs), "messages": msgs})


def cmd_search(args):
    client = get_client(args)
    hz = Humanizer(client)
    resp = api(client.search_messages, query=args.query, count=args.limit)
    matches = _search_matches(resp, hz)
    emit({"ok": True, "query": args.query, "count": len(matches), "matches": matches})


def _search_matches(resp, hz: Humanizer) -> list:
    return [
        {
            "ts": m.get("ts"),
            "from": m.get("username"),
            "from_id": m.get("user"),
            "channel": (m.get("channel") or {}).get("name"),
            "channel_id": (m.get("channel") or {}).get("id"),
            "text": hz.render(m.get("text")),
            "permalink": m.get("permalink"),
        }
        for m in (resp.get("messages") or {}).get("matches", [])
    ]


def add_thread_context(client, hz: Humanizer, match: dict, n: int) -> None:
    """Attach up to n messages that preceded this match in its thread."""
    channel_id, thread_ts = parse_thread(match.get("permalink"))
    channel_id = match.get("channel_id") or channel_id
    if not (channel_id and thread_ts) or thread_ts == match.get("ts"):
        return  # not in a thread, or the match IS the thread root
    resp, _ = api_safe(client.conversations_replies, channel=channel_id, ts=thread_ts, limit=200)
    if not resp:
        return
    before = [m for m in resp.get("messages", []) if (m.get("ts") or "") < match["ts"]]
    match["thread_context"] = [
        {"ts": m.get("ts"), "from_id": m.get("user"), "text": hz.render(m.get("text"))}
        for m in before[-n:]
    ]


def cmd_activity(args):
    # search.messages requires a user token — always run as the user.
    client = get_client(args)
    hz = Humanizer(client)
    me = api(client.auth_test)
    handle = me.get("user")
    after = (date.today() - timedelta(days=args.days)).isoformat()

    feeds = {
        "mentions": f"@{handle} after:{after}",   # messages that @-mention me
        "dms": f"to:@{handle} after:{after}",      # DMs sent to me
    }
    if not args.dms:
        feeds.pop("dms")

    # Per-channel last_read, fetched once and cached. A message is "unread" if its
    # ts is newer than last_read. Reading here never marks anything as read.
    last_read_cache: dict = {}

    def is_unread(match):
        cid = match.get("channel_id")
        if not cid:
            return None
        if cid not in last_read_cache:
            resp, _ = api_safe(client.conversations_info, channel=cid)
            last_read_cache[cid] = resp["channel"].get("last_read") if resp else None
        lr = last_read_cache[cid]
        return None if lr is None else (match["ts"] or "") > lr

    result = {"ok": True, "as": handle, "since": after, "feeds": {}}
    for name, query in feeds.items():
        resp, err = api_safe(
            client.search_messages,
            query=query,
            count=args.limit,
            sort="timestamp",
            sort_dir="desc",
        )
        if err == "missing_scope":
            fail(
                "activity needs the `search:read` User Token Scope. Add it to your "
                "Slack App's User Token Scopes and reinstall.",
                slack_error=err,
            )
        if err:
            fail(f"Slack API error: {err}", slack_error=err)
        matches = _search_matches(resp, hz)
        for mt in matches:
            mt["unread"] = is_unread(mt)
        if args.unread_only:
            matches = [m for m in matches if m.get("unread")]
        if args.context:
            for mt in matches:
                add_thread_context(client, hz, mt, args.context)
        result["feeds"][name] = {"query": query, "matches": matches}
    emit(result)


def cmd_react(args):
    client = get_client(args)
    channel = resolve_channel(client, args.channel)
    api(client.reactions_add, channel=channel["id"], timestamp=args.ts, name=args.emoji.strip(":"))
    emit({"ok": True, "channel": channel_brief(channel), "ts": args.ts, "emoji": args.emoji})


# --------------------------------------------------------------------------- #
# argparse
# --------------------------------------------------------------------------- #
def add_identity(sp):
    sp.add_argument(
        "--as", dest="as_identity", choices=["user", "bot"], default="user",
        help="Identity to act as: user (xoxp, default) or bot (xoxb)",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="slack", description="Operate Slack as yourself or as a bot.")
    p.add_argument("--token", help="raw token override (ignores --as)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="Validate and save token(s)")
    s.add_argument("--token", help="xoxp- user token")
    s.add_argument("--bot-token", dest="bot_token", help="xoxb- bot token")
    s.set_defaults(func=cmd_setup)

    s = sub.add_parser("whoami", help="Show the authenticated identity")
    add_identity(s)
    s.set_defaults(func=cmd_whoami)

    s = sub.add_parser("channels", help="List or find channels")
    s.add_argument("--name", help="Find one channel by name")
    s.add_argument("--types", help="Comma list: public_channel,private_channel,mpim,im")
    s.set_defaults(func=cmd_channels)

    s = sub.add_parser("users", help="List or find users")
    s.add_argument("--name", help="Find by display/real name or handle")
    s.add_argument("--email", help="Find by email (exact)")
    s.set_defaults(func=cmd_users)

    s = sub.add_parser("people", help="Manage the local alias table (name -> user ID)")
    s.add_argument("--add", action="append", metavar="NAME=USERID",
                   help="Add/update an alias (repeatable)")
    s.add_argument("--remove", action="append", metavar="NAME",
                   help="Remove an alias (repeatable)")
    s.set_defaults(func=cmd_people)

    s = sub.add_parser("post", help="Post a message, optionally @mentioning people")
    s.add_argument("--channel", required=True, help="#name or channel ID")
    s.add_argument("--text", required=True, help="Message body")
    s.add_argument("--mention", action="append", help="Name/email/ID to @mention (repeatable)")
    s.add_argument("--thread", help="thread_ts to reply into a thread")
    add_identity(s)
    s.set_defaults(func=cmd_post)

    s = sub.add_parser("dm", help="Send a direct message (1:1 or group)")
    s.add_argument("--to", action="append", required=True,
                   help="Recipient name/email/ID (repeat for a group DM)")
    s.add_argument("--text", required=True, help="Message body")
    s.add_argument("--mention", action="append", help="Name/email/ID to @mention (repeatable)")
    s.add_argument("--thread", help="thread_ts to reply into a thread")
    add_identity(s)
    s.set_defaults(func=cmd_dm)

    s = sub.add_parser("edit", help="Edit one of your own messages")
    s.add_argument("--channel", required=True, help="#name or channel ID")
    s.add_argument("--ts", required=True, help="ts of the message to edit")
    s.add_argument("--text", required=True, help="New message body")
    add_identity(s)
    s.set_defaults(func=cmd_edit)

    s = sub.add_parser("delete", help="Delete one of your own messages (irreversible)")
    s.add_argument("--channel", required=True, help="#name or channel ID")
    s.add_argument("--ts", required=True, help="ts of the message to delete")
    add_identity(s)
    s.set_defaults(func=cmd_delete)

    s = sub.add_parser("read", help="Read recent channel history")
    s.add_argument("--channel", required=True)
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_read)

    s = sub.add_parser("thread", help="Read a thread's replies")
    s.add_argument("--channel", required=True)
    s.add_argument("--ts", required=True, help="thread parent ts")
    s.set_defaults(func=cmd_thread)

    s = sub.add_parser("search", help="Search messages")
    s.add_argument("--query", required=True)
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("activity", help="Recent messages mentioning you (and optionally DMs to you)")
    s.add_argument("--days", type=int, default=7, help="Look back this many days (default 7)")
    s.add_argument("--limit", type=int, default=30, help="Max matches per feed")
    s.add_argument("--dms", action="store_true", help="Also include DMs sent to you")
    s.add_argument("--context", type=int, default=0, metavar="N",
                   help="For mentions inside a thread, include the N messages that "
                        "preceded yours (default 0 = off)")
    s.add_argument("--unread-only", dest="unread_only", action="store_true",
                   help="Keep only messages newer than the channel's last_read")
    s.set_defaults(func=cmd_activity)

    s = sub.add_parser("react", help="Add an emoji reaction")
    s.add_argument("--channel", required=True)
    s.add_argument("--ts", required=True)
    s.add_argument("--emoji", required=True, help="e.g. thumbsup or :tada:")
    add_identity(s)
    s.set_defaults(func=cmd_react)

    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
