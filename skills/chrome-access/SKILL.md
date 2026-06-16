---
name: chrome-access
description: >-
  Drive a local Chrome over the Chrome DevTools Protocol (CDP) so the agent can
  read and interact with real browser content — read DOM, run JS, snapshot the
  accessibility tree, click/fill/navigate, and screenshot.

  Use this skill when the user asks to "open Chrome", "read a page", "control my
  browser", "use CDP", "connect to Chrome", "drive Chrome", "screenshot a site",
  or otherwise wants the agent to see/act on live browser content on any
  arbitrary website (not just a specific repo's local build).

  For verifying THIS repo's dashboard UI specifically, prefer the repo's own
  `agent-browser` skill (Playwright auth state, concierge build) instead.
source: personal
risk: safe
domain: automation
category: browser
version: 1.0.0
---

# chrome-access — drive Chrome over CDP

Launch (or attach to) a Chrome instance with remote debugging enabled, then use
the `agent-browser` CLI as the CDP client to read and act on page content.

## Mental model

Three layers — the agent never speaks raw CDP, `agent-browser` does:

```
Claude  ──shell──▶  agent-browser  ──CDP (ws://localhost:9222)──▶  Chrome
                    (CDP client)                                   (server: --remote-debugging-port)
```

- **Chrome** is the CDP *server* — `--remote-debugging-port=9222` exposes an
  HTTP/WebSocket endpoint at `http://localhost:9222`. This endpoint IS the thing
  people loosely call a "CDP proxy"; there is no separate proxy to install.
- **agent-browser** is the CDP *client*: it holds the WebSocket open across
  commands, translates `open`/`get text`/`click`/`eval` into CDP frames, manages
  element refs (`@e1`, `@e2`), and returns content/screenshots back to the shell.

## Prerequisites (usually already present)

- Chrome Canary installed (macOS: `/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary`).
  **Use Canary, not the daily Google Chrome.** Canary is a distinct app bundle
  (`com.google.Chrome.canary`), so the agent instance never steals "open link"
  events from your real Chrome. A separate `--user-data-dir` alone does NOT
  prevent that — macOS routes URL opens by bundle id, so a same-bundle agent
  instance hijacks every link open. Plain Google Chrome
  (`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`) works as a
  fallback only if Canary isn't installed.
- `agent-browser` CLI on PATH (macOS pnpm install: `~/Library/pnpm/agent-browser`).
  Verify: `agent-browser --version`. It has native CDP support (`connect`,
  `get cdp-url`). **Nothing else needs installing.**

## The Chrome 136+ gotcha (read this first)

Since Chrome 136, Chrome **refuses to open a remote-debugging port when launched
against the default user-data-dir** (security mitigation). Consequences:

- You cannot "just add a debug port" to the user's already-running normal Chrome.
- You MUST pass a separate `--user-data-dir`.
- Passing `--remote-debugging-port` to a second `open` while Chrome is already
  running does nothing — Chrome just focuses the existing instance.

So choose a launch mode deliberately.

## Launch modes

### Mode A — dedicated debug Chrome (clean, default, zero risk)

Fresh isolated profile. Does NOT touch the user's running Chrome; the two coexist.
Trade-off: the profile is empty — no existing logins. Log in once inside it if a
site needs auth (state persists in the data dir until you delete it).

**Preferred: headless detached daemon.** This is the robust default for agent
use — no window to accidentally close, and it survives independent of the agent's
turn/background-task lifecycle (so no spurious "background command failed"
notifications). Drive it purely over CDP; the user can't see/click it.

```bash
pkill -f "user-data-dir=/tmp/chrome-cdp" 2>/dev/null; sleep 1   # clear stragglers
nohup "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary" \
  --headless=new \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-cdp \
  --no-first-run \
  --no-default-browser-check \
  about:blank >/tmp/chrome-cdp.log 2>&1 &
disown
```

**Headed variant (when the user needs to see/log in manually):** drop
`--headless=new`. A real window appears. WARNING: if launched as a tracked
background task, closing that window quits Chrome (exit 144) and fires a `failed`
notification — that's a normal window-close, not a crash; just relaunch. Still
prefer `nohup … & disown` over a tracked background task to avoid the churn.

### Mode B — debug Chrome with the user's existing logins

Copy the real profile to a separate dir, then launch that with the debug port so
cookies/logins come along. Trade-off: the user must **fully quit their running
Chrome first** (disrupts their open tabs), and copying the profile may be large.
Only do this when the user explicitly needs their real sessions and accepts the
quit. (macOS profile root: `~/Library/Application Support/Google/Chrome`.)

### Mode C — repo's agent-browser skill (not this skill)

For verifying this repo's dashboard/agents-card UI, the repo's `agent-browser`
skill uses Playwright-captured auth state + concierge build — no personal Chrome,
no fresh login. Prefer it for repo-local UI checks.

**When unsure which mode, ask the user** — the choice (quit their Chrome vs. spin
up a separate one) is theirs to make. Default to Mode A.

## Bring it up

```bash
# 1. Launch (Mode A) in the background — see command above.

# 2. Poll until the CDP endpoint answers (Chrome takes ~1-3s)
for i in 1 2 3 4 5; do
  curl -s http://localhost:9222/json/version && break
  sleep 1
done
# A JSON blob with "webSocketDebuggerUrl" means it's up.

# 3. Attach the client
agent-browser connect 9222

# 4. Prove you can read content
agent-browser open https://example.com
agent-browser wait 'h1'
agent-browser get text 'h1'      # → "Example Domain"
agent-browser get url
```

The agent-browser daemon persists between commands — `connect` once, then every
later command reuses the live session.

## Core command loop

```bash
agent-browser open <url>             # navigate (https:// auto-prepended)
agent-browser wait <sel|ms>          # wait for element or time
agent-browser snapshot -i            # accessibility tree → @e1, @e2 refs
agent-browser get text <sel>         # read text
agent-browser get html <sel>         # read markup
agent-browser get url                # current URL
agent-browser click @e5              # click a ref (or a CSS/text selector)
agent-browser fill <sel> "text"      # clear + type
agent-browser press Enter            # key press
agent-browser screenshot /tmp/x.png  # viewport shot (Read it to view inline)
agent-browser screenshot --fullpage /tmp/full.png
agent-browser eval '<js>'            # run JS in page context
```

**Refs go stale** after any navigation, submit, modal open/close, or re-render.
Re-`snapshot -i` immediately before the next ref-based action.

**`eval` must wrap in an IIFE** — a bare `return` throws `Illegal return statement`:

```bash
# RIGHT
agent-browser eval '(() => { const el = document.querySelector(".x"); return el ? getComputedStyle(el).zIndex : null; })()'
```

## Lifecycle

- **Restart the debug Chrome** after it's been closed: re-run the same launch
  command. Port is fixed at 9222; profile persists in `/tmp/chrome-cdp`.
- **Reset login state**: delete the `--user-data-dir` (e.g. `rm -rf /tmp/chrome-cdp`).
- **Release the client**: `agent-browser close` (default session) or
  `agent-browser close --all` (every session). `agent-browser session list`
  shows what's open. Leaving Chrome up between tasks is fine and faster.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `curl http://localhost:9222/json/version` empty / refused | Chrome didn't open the port. Almost always the Chrome 136+ default-profile block — confirm you passed a non-default `--user-data-dir`. |
| Port opens but profile has no logins | Expected in Mode A. Log in inside the debug Chrome, or switch to Mode B. |
| Adding the flag to running Chrome does nothing | A second launch just focuses the existing instance. Quit Chrome fully (Mode B) or use a separate data-dir + port (Mode A). |
| `SyntaxError: Illegal return statement` in `eval` | Wrap in an IIFE: `(() => { ... })()`. |
| Click doesn't navigate; refs wrong | Refs went stale — re-`snapshot -i` and use fresh `@eN`. |
| `net::ERR_CERT_AUTHORITY_INVALID` on local HTTPS | agent-browser ignores cert errors by default; confirm the server is up with `curl -kI <url>`. |
| Need the raw CDP WebSocket URL | `agent-browser get cdp-url`, or `curl -s http://localhost:9222/json/version`. |

## Notes

- The repo-local `agent-browser` skill (`skills/agent-browser`) covers the
  Playwright-auth/concierge path for this codebase's apps; this global skill is
  the general-purpose "drive any Chrome on any site over CDP" version.
- agent-browser ships its own docs: `agent-browser skills get core --full`.
