#!/usr/bin/env bash

# git-setup.sh – initialise remote and push the cleaned DIAD repo
# Usage: ./git-setup.sh [--dry-run]
#   --dry-run   Show the commands without executing them.

set -euo pipefail

REPO_URL="https://github.com/dataforentrepreneurs/DIAD_Scaffold.git"
BRANCH="main"

log() {
  echo "[git-setup] $*"
}

DRY_RUN=false
if [[ "${1-}" == "--dry-run" ]]; then
  DRY_RUN=true
  log "Running in dry‑run mode"
fi

# Ensure we are inside the repository root
if [ ! -d ".git" ]; then
  log "Error: .git directory not found – make sure you are in the repo root."
  exit 1
fi

# Add remote if not present
if git remote get-url origin >/dev/null 2>&1; then
  CURRENT_URL=$(git remote get-url origin)
  if [ "$CURRENT_URL" != "$REPO_URL" ]; then
    log "Updating remote 'origin' URL from $CURRENT_URL to $REPO_URL"
    if ! $DRY_RUN; then
      git remote set-url origin "$REPO_URL"
    fi
  else
    log "Remote 'origin' already points to the correct URL."
  fi
else
  log "Adding remote 'origin' -> $REPO_URL"
  if ! $DRY_RUN; then
    git remote add origin "$REPO_URL"
  fi
fi

# Ensure the branch name is "main"
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
  log "Renaming current branch $CURRENT_BRANCH to $BRANCH"
  if ! $DRY_RUN; then
    git branch -M "$BRANCH"
  fi
else
  log "Current branch is already $BRANCH"
fi

# Push to GitHub (force‑push if needed for a clean history)
log "Pushing $BRANCH to remote..."
if $DRY_RUN; then
  echo "git push -u origin $BRANCH"
else
  git push -u origin "$BRANCH"
fi

log "Finished. Your repository is now up‑to‑date at $REPO_URL"
