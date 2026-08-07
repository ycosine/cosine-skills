---
name: wt
description: Manage git worktrees with the wt CLI — create a workspace for a task (wt new), list workspaces (wt list --json), archive/restore/remove them, and run the repo's dev command (wt run). Use when the user asks to create a worktree/workspace, work on branches in parallel, clean up or archive worktrees, or jump between workspaces.
---

# wt — git worktree manager

`wt` manages worktrees under a central root (default `~/worktrees/<repo>/<name>`), with per-repo hooks configured in `~/.config/wt/repos/<repo>.toml`.

## Commands

| Command | Effect |
|---|---|
| `wt new [name] [--base <ref>] [--branch <name>] [--no-setup]` | Create a worktree. Without a name, picks an unused city name. Branch defaults to `wt/<name>`. Runs the repo's `post_create` hook unless `--no-setup`. Prints the new path on stdout. |
| `wt list --json [--all] [--archived] [--deep]` | Machine-readable listing: `repo, name, branch, path, dirty, main, archived`. `--all` covers every repo under the worktrees root; add `--deep` to reverse-discover through git's worktree registry, including worktrees created elsewhere by hand or other tools (slower — spawns git per repo). |
| `wt archive <name> [--force]` | Remove the worktree directory, keep the branch (recorded in state). Refuses if dirty unless `--force`. Runs `pre_archive` hook. |
| `wt restore <name>` | Recreate an archived worktree from its kept branch; runs `post_create`. |
| `wt rm <name> [--force]` | Remove worktree AND delete its branch. Refuses dirty / unmerged without `--force`. Also cleans up archived entries. |
| `wt run [name] [-- extra args]` | Run the repo's configured `run` hook inside the named worktree (or the one containing cwd). |
| `wt config --repo [--path]` | Create/edit the current repo's config (hooks, base_branch). `--path` prints the file path instead of opening $EDITOR. |

## Agent guidance

- **Always use `--json` for reading state** — never parse the human table.
- **Do not use `wt jump`** — it is interactive (fzf) and only changes directory via the user's shell wrapper. To work inside a worktree, get its `path` from `wt list --json` and `cd` in Bash.
- `wt new` prints the created path as the last line of stdout — capture it to continue working there.
- Destructive flags: `--force` on `archive`/`rm` discards uncommitted changes. Confirm with the user before using it on a dirty worktree you did not create.
- To configure hooks non-interactively, edit the file at `wt config --repo --path` directly. Hook env vars: `$WT_NAME`, `$WT_BRANCH`, `$WT_WORKTREE_PATH`, `$WT_MAIN_REPO`.
