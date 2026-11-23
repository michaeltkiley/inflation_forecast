#!/usr/bin/env bash
# Check out / publish the `data` branch (orphan; created on first use) holding the vintage archive and the nowcast run history.
# Usage (from the repository root):  nowcast/scripts/data_branch.sh start  [worktree dir (default vintage)] [remote (default origin)]
#                                    nowcast/scripts/data_branch.sh finish [worktree dir (default vintage)] [remote (default origin)]
# `start` makes the branch available as a worktree at DIR (NOWCAST_ARCHIVE points at it); `finish` commits whatever the run wrote there and pushes it.
set -euo pipefail
CMD="${1:?usage: data_branch.sh start|finish [dir] [remote]}"
DIR="${2:-vintage}"
REMOTE="${3:-origin}"
git config user.name  >/dev/null 2>&1 || git config user.name  'github-actions[bot]'
git config user.email >/dev/null 2>&1 || git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
case "$CMD" in
  start)
    if git fetch --depth=1 "$REMOTE" data; then
      git worktree add -B data "$DIR" FETCH_HEAD
    else
      echo "no data branch yet: starting the archive"
      git worktree add --orphan -b data "$DIR"
    fi
    ;;
  finish)
    cd "$DIR"
    git add -A
    git diff --cached --quiet || git commit -q -m "Nowcast archive $(date -u +%F)"
    if git rev-parse -q --verify HEAD >/dev/null; then
      for i in 1 2 3; do git push "$REMOTE" HEAD:data && break; git pull --rebase "$REMOTE" data; done
    else
      echo "nothing archived yet"
    fi
    ;;
  *) echo "unknown command: $CMD" >&2; exit 2 ;;
esac
