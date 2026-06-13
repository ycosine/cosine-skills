#!/usr/bin/env bash
# Install personal skills from this repo into ~/.claude/skills via symlink,
# and set up each skill's Python venv.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$REPO/skills"
SKILLS_DST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

mkdir -p "$SKILLS_DST"

for dir in "$SKILLS_SRC"/*/; do
  name="$(basename "$dir")"
  link="$SKILLS_DST/$name"

  # symlink so edits in the repo take effect immediately
  if [ -L "$link" ] || [ ! -e "$link" ]; then
    ln -sfn "$dir" "$link"
    echo "linked  $name -> $link"
  else
    echo "skip    $name (a non-symlink already exists at $link)"
    continue
  fi

  # per-skill venv if it declares requirements
  if [ -f "$dir/requirements.txt" ]; then
    if [ ! -d "$dir/.venv" ]; then
      python3 -m venv "$dir/.venv"
    fi
    "$dir/.venv/bin/pip" install -q --upgrade pip
    "$dir/.venv/bin/pip" install -q -r "$dir/requirements.txt"
    echo "deps    $name (venv ready)"
  fi

  # make wrapper scripts executable
  find "$dir/scripts" -maxdepth 1 -type f ! -name '*.py' -exec chmod +x {} \; 2>/dev/null || true
done

echo "done."
