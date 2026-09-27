#!/usr/bin/env python3
"""Cloudflare R2 CLI — buckets via the Cloudflare v4 API, objects via R2's
S3-compatible API (SigV4 implemented here).

Prints one JSON object per invocation: {"ok": true, ...} on success,
{"ok": false, "error": "..."} on failure (non-zero exit code).

Credentials (first match wins per key):
  1. Environment
  2. $CLOUDFLARE_R2_ENV_FILE (a .env path)
  3. <skill-dir>/.env
  4. ~/.config/cloudflare-r2-skill/.env
Keys:
  CLOUDFLARE_ACCOUNT_ID    required (R2 endpoint is per account)
  CLOUDFLARE_R2_API_TOKEN  an API token with R2 read/write. Enough on its own:
                           bucket management uses it directly, and the S3 key
                           pair is derived from it (Access Key ID = token id,
                           Secret = SHA-256 of the token value).
  R2_ACCESS_KEY_ID /       optional explicit S3 key pair (e.g. from the R2
  R2_SECRET_ACCESS_KEY     dashboard's "Manage API tokens"); used for object
                           commands instead of the derived pair.

Proxies: urllib honors HTTPS_PROXY / https_proxy (HTTP proxies only).

Stdlib only — no third-party dependencies.
"""

import argparse
import datetime
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

API = "https://api.cloudflare.com/client/v4"
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGION = "auto"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
MULTIPART_THRESHOLD = 100 * 1024 * 1024
PART_SIZE = 64 * 1024 * 1024
PART_ATTEMPTS = 4
S3NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"

ACCOUNT_KEYS = ("CLOUDFLARE_ACCOUNT_ID", "CF_ACCOUNT_ID", "ACCOUNT_ID", "account_id")
TOKEN_KEYS = ("CLOUDFLARE_R2_API_TOKEN", "CF_R2_API_TOKEN", "R2_API_TOKEN")
AKID_KEYS = ("R2_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID")
SECRET_KEYS = ("R2_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY")


class Fail(Exception):
    pass


def die(msg, **extra):
    print(json.dumps({"ok": False, "error": msg, **extra}, ensure_ascii=False))
    sys.exit(1)


def out(**kw):
    print(json.dumps({"ok": True, **kw}, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- credentials

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


class Creds:
    def __init__(self):
        sources = [os.environ]
        for path in (os.environ.get("CLOUDFLARE_R2_ENV_FILE"),
                     os.path.join(SKILL_DIR, ".env"),
                     os.path.expanduser("~/.config/cloudflare-r2-skill/.env")):
            if path and os.path.isfile(path):
                sources.append(parse_env_file(path))

        def pick(keys):
            for src in sources:
                for k in keys:
                    if src.get(k):
                        return src[k]
            return None

        self.account = pick(ACCOUNT_KEYS)
        self.token = pick(TOKEN_KEYS)
        self._akid = pick(AKID_KEYS)
        self._secret = pick(SECRET_KEYS)
        if not self.account:
            die("CLOUDFLARE_ACCOUNT_ID missing (see .env.example)")

    def need_token(self):
        if not self.token:
            die("CLOUDFLARE_R2_API_TOKEN missing: bucket management needs an "
                "API token with R2 read/write (see .env.example)")
        return self.token

    def s3_keys(self):
        """Explicit key pair if given, else derived from the API token."""
        if self._akid and self._secret:
            return self._akid, self._secret
        token = self.need_token()
        verify = cf_api(token, "GET", f"/accounts/{self.account}/tokens/verify", soft=True)
        if verify is None:  # user-owned token rather than account-owned
            verify = cf_api(token, "GET", "/user/tokens/verify")
        return verify["result"]["id"], hashlib.sha256(token.encode()).hexdigest()

    @property
    def endpoint_host(self):
        return f"{self.account}.r2.cloudflarestorage.com"


# ---------------------------------------------------------------- v4 REST API

def cf_api(token, method, path, body=None, soft=False):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            errs = json.loads(e.read().decode()).get("errors", [])
            msg = "; ".join(f"[{x.get('code')}] {x.get('message')}" for x in errs) or f"HTTP {e.code}"
        except ValueError:
            msg = f"HTTP {e.code}"
        if soft:
            return None
        die(msg)
    except urllib.error.URLError as e:
        if soft:
            return None
        die(f"Network error: {e.reason}")
    if not payload.get("success"):
        if soft:
            return None
        die("; ".join(x.get("message", "") for x in payload.get("errors", [])) or "API error")
    return payload


# ---------------------------------------------------------------- SigV4 (S3)

def _hmac(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def uri_encode(s, keep_slash):
    return urllib.parse.quote(s, safe="/~" if keep_slash else "~")


def canonical_query(params):
    return "&".join(f"{uri_encode(k, False)}={uri_encode(str(v), False)}"
                    for k, v in sorted(params.items()))


def sign(method, host, path, params, headers, payload_hash, akid, secret, now,
         region=REGION, service="s3"):
    """Returns headers (incl. Authorization) for a SigV4-signed request.
    `path` is the raw path; it is URI-encoded here (S3: single encoding,
    slashes kept). `headers` are extra headers to sign."""
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    hdrs = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    hdrs.update({k.lower(): str(v).strip() for k, v in headers.items()})
    signed = ";".join(sorted(hdrs))
    canonical = "\n".join([
        method,
        uri_encode(path, True),
        canonical_query(params),
        "".join(f"{k}:{hdrs[k]}\n" for k in sorted(hdrs)),
        signed,
        payload_hash,
    ])
    scope = f"{datestamp}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    k = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret).encode(), datestamp), region), service),
              "aws4_request")
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    hdrs["authorization"] = (f"AWS4-HMAC-SHA256 Credential={akid}/{scope}, "
                             f"SignedHeaders={signed}, Signature={sig}")
    return hdrs


def presign_url(host, path, akid, secret, expires, now):
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    scope = f"{datestamp}/{REGION}/s3/aws4_request"
    params = {"X-Amz-Algorithm": "AWS4-HMAC-SHA256",
              "X-Amz-Credential": f"{akid}/{scope}",
              "X-Amz-Date": amz_date, "X-Amz-Expires": str(expires),
              "X-Amz-SignedHeaders": "host"}
    canonical = "\n".join(["GET", uri_encode(path, True), canonical_query(params),
                           f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"])
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    k = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret).encode(), datestamp), REGION), "s3"),
              "aws4_request")
    params["X-Amz-Signature"] = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    return f"https://{host}{uri_encode(path, True)}?{canonical_query(params)}"


class S3:
    def __init__(self, creds):
        self.host = creds.endpoint_host
        self.akid, self.secret = creds.s3_keys()

    def request(self, method, path, params=None, headers=None, body=b"",
                payload_hash=None, stream_to=None, timeout=300):
        params = params or {}
        if payload_hash is None:
            payload_hash = hashlib.sha256(body).hexdigest() if isinstance(body, bytes) else "UNSIGNED-PAYLOAD"
        now = datetime.datetime.now(datetime.timezone.utc)
        hdrs = sign(method, self.host, path, params, headers or {}, payload_hash,
                    self.akid, self.secret, now)
        url = f"https://{self.host}{uri_encode(path, True)}"
        if params:
            url += "?" + canonical_query(params)
        hdrs.pop("host")
        req = urllib.request.Request(url, method=method, headers=hdrs,
                                     data=body if method in ("PUT", "POST") else None)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            code = msg = ""
            try:
                root = ET.fromstring(text)
                code, msg = root.findtext("Code") or "", root.findtext("Message") or ""
            except ET.ParseError:
                msg = text[:200]
            raise Fail(f"HTTP {e.code} {code}: {msg}".strip())
        except urllib.error.URLError as e:
            raise Fail(f"Network error: {e.reason}")
        with resp:
            if stream_to is not None:
                n = 0
                while chunk := resp.read(1 << 20):
                    stream_to.write(chunk)
                    n += len(chunk)
                return resp.headers, n
            return resp.headers, resp.read()


def xml_find_all(data, tag):
    root = ET.fromstring(data)
    return root.findall(f".//{S3NS}{tag}") or root.findall(f".//{tag}")


def xml_text(el, tag):
    v = el.find(f"{S3NS}{tag}")
    if v is None:
        v = el.find(tag)
    return v.text if v is not None else None


# ---------------------------------------------------------------- object ops

def list_objects(s3, bucket, prefix, delimiter=None):
    objs, prefixes, token = [], [], None
    while True:
        params = {"list-type": "2", "max-keys": "1000"}
        if prefix:
            params["prefix"] = prefix
        if delimiter:
            params["delimiter"] = delimiter
        if token:
            params["continuation-token"] = token
        _, data = s3.request("GET", f"/{bucket}", params)
        for c in xml_find_all(data, "Contents"):
            objs.append({"key": xml_text(c, "Key"), "size": int(xml_text(c, "Size") or 0),
                         "last_modified": xml_text(c, "LastModified"),
                         "etag": (xml_text(c, "ETag") or "").strip('"')})
        for p in xml_find_all(data, "CommonPrefixes"):
            prefixes.append(xml_text(p, "Prefix"))
        root = ET.fromstring(data)
        truncated = (root.findtext(f"{S3NS}IsTruncated") or root.findtext("IsTruncated")) == "true"
        token = root.findtext(f"{S3NS}NextContinuationToken") or root.findtext("NextContinuationToken")
        if not truncated or not token:
            return objs, prefixes


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def with_retries(what, fn, attempts=PART_ATTEMPTS):
    """Retries network errors and 5xx (flaky cross-border links); a 4xx is
    the request's own fault and fails at once — except RequestTimeout."""
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Fail as e:
            client_error = str(e).startswith("HTTP 4") and "RequestTimeout" not in str(e)
            if i == attempts or client_error:
                raise Fail(f"{what}: {e}")
            time.sleep(min(2 ** i, 20))


def put_object(s3, bucket, key, path, content_type, meta):
    size = os.path.getsize(path)
    headers = {"content-type": content_type}
    headers.update({f"x-amz-meta-{k}": v for k, v in meta.items()})
    if size <= MULTIPART_THRESHOLD:
        with open(path, "rb") as f:
            body = f.read()
        h, _ = with_retries("put", lambda: s3.request(
            "PUT", f"/{bucket}/{key}", headers=headers, body=body))
        return {"etag": (h.get("ETag") or "").strip('"'), "parts": 1}

    _, data = s3.request("POST", f"/{bucket}/{key}", {"uploads": ""}, headers=headers)
    upload_id = xml_text(ET.fromstring(data), "UploadId")
    if not upload_id:
        raise Fail("multipart: no UploadId in response")
    parts = []
    try:
        with open(path, "rb") as f:
            n = 0
            while chunk := f.read(PART_SIZE):
                n += 1
                h, _ = with_retries(f"part {n}", lambda c=chunk, n=n: s3.request(
                    "PUT", f"/{bucket}/{key}", {"partNumber": str(n), "uploadId": upload_id},
                    body=c))
                parts.append((n, h.get("ETag")))
        complete = "<CompleteMultipartUpload>" + "".join(
            f"<Part><PartNumber>{n}</PartNumber><ETag>{e}</ETag></Part>" for n, e in parts
        ) + "</CompleteMultipartUpload>"
        _, data = with_retries("complete", lambda: s3.request(
            "POST", f"/{bucket}/{key}", {"uploadId": upload_id}, body=complete.encode()))
    except Fail:
        try:
            s3.request("DELETE", f"/{bucket}/{key}", {"uploadId": upload_id})
        except Fail:
            pass
        raise
    etag = ET.fromstring(data).findtext(f"{S3NS}ETag") or ""
    return {"etag": etag.strip('"'), "parts": len(parts)}


# ---------------------------------------------------------------- selftest

def selftest():
    """AWS's documented SigV4 example (S3 docs, 'Example: GET Object')."""
    now = datetime.datetime(2013, 5, 24, 0, 0, 0, tzinfo=datetime.timezone.utc)
    hdrs = sign("GET", "examplebucket.s3.amazonaws.com", "/test.txt", {},
                {"Range": "bytes=0-9"}, EMPTY_SHA256,
                "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", now,
                region="us-east-1")
    want = "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    got = hdrs["authorization"].rsplit("Signature=", 1)[1]
    return got == want, got, want


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(prog="cf-r2")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest", help="check the SigV4 signer against AWS's documented example")
    sub.add_parser("verify", help="check credentials (token + S3 keys)")
    sub.add_parser("buckets", help="list buckets")
    sp = sub.add_parser("create-bucket", help="create a bucket")
    sp.add_argument("bucket")
    sp.add_argument("--location", help="location hint: apac, wnam, enam, weur, eeur, oc")
    sp = sub.add_parser("delete-bucket", help="delete an EMPTY bucket (irreversible)")
    sp.add_argument("bucket")
    for name, hlp in (("ls", "list objects"), ("du", "total size / count")):
        sp = sub.add_parser(name, help=hlp)
        sp.add_argument("bucket")
        sp.add_argument("--prefix", default="")
        if name == "ls":
            sp.add_argument("--delimiter", help="e.g. / to list one level")
    sp = sub.add_parser("put", help="upload a file (multipart above 100 MiB)")
    sp.add_argument("bucket")
    sp.add_argument("key")
    sp.add_argument("file")
    sp.add_argument("--content-type", default="application/octet-stream")
    sp.add_argument("--no-sha256", action="store_true",
                    help="skip storing x-amz-meta-sha256 (saves one read pass)")
    sp = sub.add_parser("get", help="download an object")
    sp.add_argument("bucket")
    sp.add_argument("key")
    sp.add_argument("--out", required=True)
    sp.add_argument("--verify", action="store_true", help="check against x-amz-meta-sha256")
    sp = sub.add_parser("head", help="object metadata")
    sp.add_argument("bucket")
    sp.add_argument("key")
    sp = sub.add_parser("rm", help="delete an object (irreversible)")
    sp.add_argument("bucket")
    sp.add_argument("key")
    sp = sub.add_parser("presign", help="time-limited GET URL")
    sp.add_argument("bucket")
    sp.add_argument("key")
    sp.add_argument("--expires", type=int, default=3600, help="seconds (max 604800)")
    a = p.parse_args()

    if a.cmd == "selftest":
        ok, got, want = selftest()
        if not ok:
            die("SigV4 signer mismatch", got=got, want=want)
        return out(signer="matches AWS documented example")

    creds = Creds()
    acct = creds.account
    try:
        if a.cmd == "verify":
            res = {"account_id": acct}
            if creds.token:
                v = cf_api(creds.token, "GET", f"/accounts/{acct}/tokens/verify", soft=True) \
                    or cf_api(creds.token, "GET", "/user/tokens/verify", soft=True)
                res["token_status"] = v["result"]["status"] if v else "invalid"
                b = cf_api(creds.token, "GET", f"/accounts/{acct}/r2/buckets", soft=True)
                res["token_can_list_buckets"] = b is not None
            s3 = S3(creds)
            s3.request("GET", "/")  # ListBuckets
            res["s3_keys"] = "ok"
            return out(**res)
        if a.cmd == "buckets":
            r = cf_api(creds.need_token(), "GET", f"/accounts/{acct}/r2/buckets")
            return out(buckets=[{"name": b["name"], "created": b.get("creation_date"),
                                 "location": b.get("location")}
                                for b in r["result"].get("buckets", [])])
        if a.cmd == "create-bucket":
            body = {"name": a.bucket}
            if a.location:
                body["locationHint"] = a.location
            r = cf_api(creds.need_token(), "POST", f"/accounts/{acct}/r2/buckets", body)
            return out(action="created", bucket=r["result"])
        if a.cmd == "delete-bucket":
            cf_api(creds.need_token(), "DELETE", f"/accounts/{acct}/r2/buckets/{a.bucket}")
            return out(action="deleted", bucket=a.bucket)

        s3 = S3(creds)
        if a.cmd in ("ls", "du"):
            objs, prefixes = list_objects(s3, a.bucket, a.prefix,
                                          getattr(a, "delimiter", None))
            if a.cmd == "du":
                return out(bucket=a.bucket, prefix=a.prefix, objects=len(objs),
                           bytes=sum(o["size"] for o in objs))
            return out(bucket=a.bucket, count=len(objs), objects=objs,
                       **({"prefixes": prefixes} if prefixes else {}))
        if a.cmd == "put":
            meta = {} if a.no_sha256 else {"sha256": file_sha256(a.file)}
            t0 = time.time()
            r = put_object(s3, a.bucket, a.key, a.file, a.content_type, meta)
            size = os.path.getsize(a.file)
            dt = time.time() - t0
            return out(action="uploaded", bucket=a.bucket, key=a.key, bytes=size,
                       seconds=round(dt, 1), mb_per_s=round(size / 1e6 / max(dt, 1e-6), 2),
                       **r, **meta)
        if a.cmd == "get":
            tmp = a.out + ".part"
            with open(tmp, "wb") as f:
                h, n = s3.request("GET", f"/{a.bucket}/{a.key}", stream_to=f, timeout=600)
            want = h.get("x-amz-meta-sha256")
            if a.verify:
                if not want:
                    raise Fail("object has no x-amz-meta-sha256 to verify against")
                got = file_sha256(tmp)
                if got != want:
                    os.remove(tmp)
                    raise Fail(f"sha256 mismatch: got {got}, object says {want}")
            os.replace(tmp, a.out)
            return out(action="downloaded", key=a.key, out=a.out, bytes=n,
                       verified=bool(a.verify))
        if a.cmd == "head":
            h, _ = s3.request("HEAD", f"/{a.bucket}/{a.key}")
            return out(key=a.key, bytes=int(h.get("Content-Length") or 0),
                       last_modified=h.get("Last-Modified"), etag=(h.get("ETag") or "").strip('"'),
                       content_type=h.get("Content-Type"),
                       meta={k[11:]: v for k, v in h.items() if k.lower().startswith("x-amz-meta-")})
        if a.cmd == "rm":
            s3.request("DELETE", f"/{a.bucket}/{a.key}")
            return out(action="deleted", bucket=a.bucket, key=a.key)
        if a.cmd == "presign":
            if not 1 <= a.expires <= 604800:
                raise Fail("--expires must be 1..604800 seconds")
            url = presign_url(s3.host, f"/{a.bucket}/{a.key}", s3.akid, s3.secret, a.expires,
                              datetime.datetime.now(datetime.timezone.utc))
            return out(url=url, expires_in=a.expires)
    except Fail as e:
        die(str(e))


if __name__ == "__main__":
    main()
