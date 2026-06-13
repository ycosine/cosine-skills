#!/usr/bin/env bash
# Install personal skills from this repo into ~/.claude/skills via symlink,
# set up each skill's Python venv, and scaffold the Slack config in ~/.config.
#
# Safe to re-run: symlinks are refreshed, venvs reused, and existing config
# files are never overwritten.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$REPO/skills"
SKILLS_DST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
SLACK_CFG_DIR="${SLACK_SKILL_DIR:-$HOME/.config/slack-skill}"

# --- preflight ------------------------------------------------------------- #
if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 not found — install Python 3 first." >&2
  exit 1
fi

mkdir -p "$SKILLS_DST"

# --- link skills + build venvs --------------------------------------------- #
for dir in "$SKILLS_SRC"/*/; do
  name="$(basename "$dir")"
  link="$SKILLS_DST/$name"

  if [ -L "$link" ] || [ ! -e "$link" ]; then
    ln -sfn "$dir" "$link"
    echo "linked  $name -> $link"
  else
    echo "skip    $name (a non-symlink already exists at $link)"
    continue
  fi

  if [ -f "$dir/requirements.txt" ]; then
    if [ ! -d "$dir/.venv" ]; then
      python3 -m venv "$dir/.venv"
    fi
    "$dir/.venv/bin/pip" install -q --upgrade pip
    "$dir/.venv/bin/pip" install -q -r "$dir/requirements.txt"
    echo "deps    $name (venv ready)"
  fi

  # make wrapper/CLI scripts executable
  find "$dir/scripts" -maxdepth 1 -type f -exec chmod +x {} \; 2>/dev/null || true
done

# --- scaffold Slack config (never overwrite) ------------------------------- #
mkdir -p "$SLACK_CFG_DIR"

scaffold() {  # <example-file> <dest-file>
  local src="$1" dst="$2"
  if [ -f "$dst" ]; then
    echo "config  $(basename "$dst") already exists — left untouched"
  elif [ -f "$src" ]; then
    cp "$src" "$dst"
    chmod 600 "$dst"
    echo "config  created $dst (from template)"
  fi
}

scaffold "$SKILLS_SRC/slack/config.example.json" "$SLACK_CFG_DIR/config.json"
scaffold "$SKILLS_SRC/slack/people.example.json" "$SLACK_CFG_DIR/people.json"

# --- next steps ------------------------------------------------------------ #
echo
echo "done. Next:"
if grep -q '"user_token": ""' "$SLACK_CFG_DIR/config.json" 2>/dev/null; then
  echo "  1. Add your Slack tokens:"
  echo "       \$EDITOR $SLACK_CFG_DIR/config.json"
  echo "     (or: $SKILLS_DST/slack/scripts/slack setup --token xoxp-... [--bot-token xoxb-...])"
  echo "  2. Verify:  $SKILLS_DST/slack/scripts/slack whoami"
else
  echo "  Slack token already configured. Verify with:"
  echo "     $SKILLS_DST/slack/scripts/slack whoami"
fi
