#!/usr/bin/env bash
# Remove the archived slopgate-windows-powershell worktree and tag its tip.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKTREE="../slopgate-windows-powershell"
BRANCH="windows-powershell-compat"
TAG="archive/windows-powershell-compat"

cd "$REPO_ROOT"

if git worktree list --porcelain | grep -q "slopgate-windows-powershell"; then
  tip="$(git -C "$WORKTREE" rev-parse HEAD 2>/dev/null || true)"
  if [[ -n "${tip}" ]] && ! git rev-parse "$TAG" >/dev/null 2>&1; then
    git tag -a "$TAG" "$tip" -m "Archive windows-powershell-compat worktree (superseded by slopgate)"
    echo "Tagged $TAG at $tip"
  fi
  git worktree remove "$WORKTREE" --force
  echo "Removed worktree $WORKTREE"
else
  echo "Worktree not registered; skipping remove"
fi

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  if git merge-base --is-ancestor "$BRANCH" master 2>/dev/null; then
    git branch -d "$BRANCH" && echo "Deleted merged branch $BRANCH"
  else
    echo "Branch $BRANCH not merged into master; kept (see tag $TAG)"
    echo "Delete manually with: git branch -D $BRANCH"
  fi
fi

# Repair stale gitdir pointer if a bare directory remains
if [[ -f "$REPO_ROOT/../slopgate-windows-powershell/.git" ]]; then
  echo "Note: $REPO_ROOT/../slopgate-windows-powershell still exists on disk."
  echo "Remove manually after confirming ARCHIVED.md if worktree remove did not delete it."
fi
