#!/usr/bin/env bash
# install-claude-cli.sh — install a pinned Claude Code CLI into a
# project-local directory so GitLab can cache it between pipelines.
# Native-registration installs (`slopgate install claude`) shell out to
# `claude plugin ...`, so the CLI must be on PATH.
set -euo pipefail

version="${CLAUDE_CODE_VERSION:?CLAUDE_CODE_VERSION must be set}"
dest="${CI_PROJECT_DIR:?CI_PROJECT_DIR must be set}/.ci/claude"

if [ -x "$dest/claude" ] && [ "$("$dest/claude" --version | awk '{print $1}')" = "$version" ]; then
  echo "claude ${version}: cache hit"
  exit 0
fi

echo "claude ${version}: installing"
curl -fsSL https://claude.ai/install.sh | bash -s -- "$version"
mkdir -p "$dest"
cp "$(readlink -f "$HOME/.local/bin/claude")" "$dest/claude"
chmod +x "$dest/claude"
"$dest/claude" --version
