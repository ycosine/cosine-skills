#!/usr/bin/env python3
"""Cloudflare DNS CLI — manage DNS records via the Cloudflare v4 API.

Prints one JSON object per invocation: {"ok": true, ...} on success,
{"ok": false, "error": "..."} on failure (non-zero exit code).

Credentials are read from (first match wins per key):
  1. Environment: CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID
  2. $CLOUDFLARE_ENV_FILE (a .env path)
  3. <skill-dir>/.env
  4. ~/.config/cloudflare-skill/.env
Accepted .env key spellings: CLOUDFLARE_API_TOKEN | CF_API_TOKEN | api_token,
CLOUDFLARE_ACCOUNT_ID | CF_ACCOUNT_ID | accountId | account_id.
Only the API token is required; account_id just narrows zone listing.

Stdlib only — no third-party dependencies.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.cloudflare.com/client/v4"
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOKEN_KEYS = ("CLOUDFLARE_API_TOKEN", "CF_API_TOKEN", "API_TOKEN", "api_token")
ACCOUNT_KEYS = ("CLOUDFLARE_ACCOUNT_ID", "CF_ACCOUNT_ID", "ACCOUNT_ID",
                "accountId", "account_id")


def die(msg, **extra):
    print(json.dumps({"ok": False, "error": msg, **extra}, ensure_ascii=False))
    sys.exit(1)


def parse_env_file(path):
    creds = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip().removeprefix("export ").strip()
                val = val.strip().strip("'\"")
                if val:
                    creds[key] = val
    except OSError:
        pass
    return creds


def load_credentials():
    candidates = [os.environ]
    for path in (os.environ.get("CLOUDFLARE_ENV_FILE"),
                 os.path.join(SKILL_DIR, ".env"),
                 os.path.expanduser("~/.config/cloudflare-skill/.env")):
        if path and os.path.isfile(path):
            candidates.append(parse_env_file(path))

    def pick(keys):
        for source in candidates:
            for k in keys:
                if source.get(k):
                    return source[k]
        return None

    token = pick(TOKEN_KEYS)
    if not token:
        die("No Cloudflare API token found. Put CLOUDFLARE_API_TOKEN (and "
            "optionally CLOUDFLARE_ACCOUNT_ID) in <skill-dir>/.env, "
            "~/.config/cloudflare-skill/.env, or the environment.")
    return token, pick(ACCOUNT_KEYS)


class ApiError(Exception):
    pass


def api(token, method, path, params=None, body=None, raw=False, soft=False):
    def fail(msg):
        if soft:
            raise ApiError(msg)
        die(msg)

    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode()
    except urllib.error.HTTPError as e:
        data = e.read().decode()
        try:
            errors = json.loads(data).get("errors", [])
            msg = "; ".join(f"[{x.get('code')}] {x.get('message')}"
                            for x in errors) or f"HTTP {e.code}"
        except (ValueError, AttributeError):
            msg = f"HTTP {e.code}: {data[:300]}"
        fail(msg)
    except urllib.error.URLError as e:
        fail(f"Network error: {e.reason}")
    if raw:
        return data
    payload = json.loads(data)
    if not payload.get("success"):
        fail("; ".join(x.get("message", "") for x in payload.get("errors", []))
             or "Unknown API error")
    return payload


def paginate(token, path, params=None):
    params = dict(params or {})
    params.setdefault("per_page", 100)
    page, items = 1, []
    while True:
        params["page"] = page
        payload = api(token, "GET", path, params)
        items.extend(payload["result"])
        info = payload.get("result_info") or {}
        if page >= info.get("total_pages", 1):
            return items
        page += 1


def resolve_zone(token, account_id, zone):
    """Accept a zone ID (32-hex) or a zone name; return (zone_id, zone_name)."""
    if re.fullmatch(r"[0-9a-f]{32}", zone):
        z = api(token, "GET", f"/zones/{zone}")["result"]
        return z["id"], z["name"]
    params = {"name": zone.lower().rstrip(".")}
    if account_id:
        params["account.id"] = account_id
    matches = api(token, "GET", "/zones", params)["result"]
    if not matches:
        die(f"Zone not found: {zone!r}. Run `zones` to list available zones.")
    return matches[0]["id"], matches[0]["name"]


def fqdn(name, zone_name):
    """'@' -> apex; 'www' -> 'www.<zone>'; already-qualified names pass through."""
    name = name.rstrip(".")
    if name in ("@", "", zone_name):
        return zone_name
    if name.endswith("." + zone_name):
        return name
    return f"{name}.{zone_name}"


def slim(rec):
    keep = ("id", "type", "name", "content", "ttl", "proxied", "priority",
            "comment")
    return {k: rec[k] for k in keep if rec.get(k) is not None}


def record_body(args, zone_name):
    body = {"type": args.type.upper(), "name": fqdn(args.name, zone_name),
            "content": args.content, "ttl": args.ttl}
    if args.proxied is not None:
        body["proxied"] = args.proxied
    if args.priority is not None:
        body["priority"] = args.priority
    if args.comment is not None:
        body["comment"] = args.comment
    return body


def find_records(token, zone_id, rtype, name):
    return api(token, "GET", f"/zones/{zone_id}/dns_records",
               {"type": rtype.upper(), "name": name})["result"]


def out(**kw):
    print(json.dumps({"ok": True, **kw}, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(prog="cf-dns")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("verify", help="verify the API token")

    sp = sub.add_parser("zones", help="list zones")
    sp.add_argument("--name")

    def zone_arg(sp):
        sp.add_argument("--zone", required=True,
                        help="zone name (example.com) or 32-hex zone ID")

    sp = sub.add_parser("records", help="list DNS records in a zone")
    zone_arg(sp)
    sp.add_argument("--type")
    sp.add_argument("--name", help="filter by record name (relative or FQDN)")
    sp.add_argument("--content")

    def record_fields(sp, require_content):
        sp.add_argument("--type", required=True, help="A/AAAA/CNAME/TXT/MX/...")
        sp.add_argument("--name", required=True,
                        help="record name; '@' for apex, relative names OK")
        sp.add_argument("--content", required=require_content,
                        help="record value (IP, hostname, text, ...)")
        sp.add_argument("--ttl", type=int, default=1,
                        help="seconds; 1 = automatic (default)")
        prox = sp.add_mutually_exclusive_group()
        prox.add_argument("--proxied", dest="proxied", action="store_true",
                          default=None)
        prox.add_argument("--no-proxied", dest="proxied", action="store_false")
        sp.add_argument("--priority", type=int, help="for MX/SRV")
        sp.add_argument("--comment")

    sp = sub.add_parser("add", help="create a record")
    zone_arg(sp)
    record_fields(sp, require_content=True)

    sp = sub.add_parser("upsert",
                        help="update the record matching type+name, else create")
    zone_arg(sp)
    record_fields(sp, require_content=True)

    sp = sub.add_parser("update", help="update a record by --id")
    zone_arg(sp)
    sp.add_argument("--id", required=True)
    sp.add_argument("--type")
    sp.add_argument("--name")
    sp.add_argument("--content")
    sp.add_argument("--ttl", type=int)
    prox = sp.add_mutually_exclusive_group()
    prox.add_argument("--proxied", dest="proxied", action="store_true",
                      default=None)
    prox.add_argument("--no-proxied", dest="proxied", action="store_false")
    sp.add_argument("--priority", type=int)
    sp.add_argument("--comment")

    sp = sub.add_parser("delete", help="delete a record (irreversible)")
    zone_arg(sp)
    sp.add_argument("--id", help="record ID (preferred)")
    sp.add_argument("--type")
    sp.add_argument("--name")

    sp = sub.add_parser("export", help="export a zone as a BIND file")
    zone_arg(sp)

    args = p.parse_args()
    token, account_id = load_credentials()

    if args.cmd == "verify":
        # Account-owned tokens (cfat_...) verify at the account endpoint;
        # classic user tokens at /user/tokens/verify. Try both.
        paths = []
        if account_id:
            paths.append(("account", f"/accounts/{account_id}/tokens/verify"))
        paths.append(("user", "/user/tokens/verify"))
        errors = []
        for scope, path in paths:
            try:
                res = api(token, "GET", path, soft=True)["result"]
            except ApiError as e:
                errors.append(f"{scope}: {e}")
                continue
            out(status=res.get("status"), token_scope=scope,
                token_id=res.get("id"), account_id=account_id)
            return
        die("; ".join(errors))

    if args.cmd == "zones":
        params = {"account.id": account_id} if account_id else {}
        if args.name:
            params["name"] = args.name
        zones = paginate(token, "/zones", params)
        out(count=len(zones), zones=[
            {"id": z["id"], "name": z["name"], "status": z["status"]}
            for z in zones])
        return

    zone_id, zone_name = resolve_zone(token, account_id, args.zone)

    if args.cmd == "records":
        params = {}
        if args.type:
            params["type"] = args.type.upper()
        if args.name:
            params["name"] = fqdn(args.name, zone_name)
        if args.content:
            params["content"] = args.content
        recs = paginate(token, f"/zones/{zone_id}/dns_records", params)
        out(zone=zone_name, count=len(recs), records=[slim(r) for r in recs])

    elif args.cmd == "add":
        rec = api(token, "POST", f"/zones/{zone_id}/dns_records",
                  body=record_body(args, zone_name))["result"]
        out(zone=zone_name, action="created", record=slim(rec))

    elif args.cmd == "upsert":
        body = record_body(args, zone_name)
        existing = find_records(token, zone_id, body["type"], body["name"])
        if len(existing) > 1:
            die(f"{len(existing)} records match {body['type']} {body['name']} "
                "— upsert is ambiguous; use `update --id` instead.",
                records=[slim(r) for r in existing])
        if existing:
            rec = api(token, "PUT",
                      f"/zones/{zone_id}/dns_records/{existing[0]['id']}",
                      body=body)["result"]
            out(zone=zone_name, action="updated", record=slim(rec))
        else:
            rec = api(token, "POST", f"/zones/{zone_id}/dns_records",
                      body=body)["result"]
            out(zone=zone_name, action="created", record=slim(rec))

    elif args.cmd == "update":
        body = {}
        for field in ("type", "name", "content", "ttl", "proxied", "priority",
                      "comment"):
            val = getattr(args, field)
            if val is not None:
                body[field] = val
        if not body:
            die("Nothing to update — pass at least one field.")
        if "type" in body:
            body["type"] = body["type"].upper()
        if "name" in body:
            body["name"] = fqdn(body["name"], zone_name)
        rec = api(token, "PATCH", f"/zones/{zone_id}/dns_records/{args.id}",
                  body=body)["result"]
        out(zone=zone_name, action="updated", record=slim(rec))

    elif args.cmd == "delete":
        rec_id = args.id
        if not rec_id:
            if not (args.type and args.name):
                die("Pass --id, or both --type and --name.")
            matches = find_records(token, zone_id, args.type,
                                   fqdn(args.name, zone_name))
            if not matches:
                die("No matching record found.")
            if len(matches) > 1:
                die(f"{len(matches)} records match — delete by --id instead.",
                    records=[slim(r) for r in matches])
            rec_id = matches[0]["id"]
        api(token, "DELETE", f"/zones/{zone_id}/dns_records/{rec_id}")
        out(zone=zone_name, action="deleted", record_id=rec_id)

    elif args.cmd == "export":
        text = api(token, "GET", f"/zones/{zone_id}/dns_records/export",
                   raw=True)
        out(zone=zone_name, bind=text)


if __name__ == "__main__":
    main()
