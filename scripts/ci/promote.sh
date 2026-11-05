#!/usr/bin/env bash
# Commit a new desired state for one environment straight to main.
#
#   promote.sh <env> <kind> <digest> <ref> <commit> <build_now> <published_json> [--rollback]
#
# Safe under races. Every attempt starts from the CURRENT origin/main, asks
# scripts/deploy-state.mjs whether this change should still win (a newer release
# or a different deployed source means it should not), and pushes. If someone
# else pushed first, the push is rejected and we start over with fresh state.
# Git's refusal to accept a non-fast-forward push is the lock; no other lock exists.
set -euo pipefail

env_name=$1 kind=$2 digest=$3 ref=$4 commit=$5 build_now=$6 published=$7
shift 7

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'

for attempt in 1 2 3 4 5; do
  git fetch --quiet origin main
  git checkout --quiet --detach origin/main

  out=$(node scripts/deploy-state.mjs promote \
    --env "$env_name" --kind "$kind" --digest "$digest" --ref "$ref" \
    --commit "$commit" --build-now "$build_now" --published "$published" "$@")
  echo "$out"

  if grep -q '^promote=false' <<<"$out"; then
    reason=$(sed -n 's/^reason=//p' <<<"$out")
    echo "::notice::Not promoting ($env_name/$kind): $reason"
    echo "Skipped $env_name/$kind: $reason" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
    exit 0
  fi

  git add "deploy/k8s/overlays/$env_name"
  git commit --quiet -m "chore(deploy): $env_name -> $ref [$kind] ${digest:0:19}"

  if git push --quiet origin HEAD:main; then
    echo "Promoted $env_name/$kind: $ref ($digest)" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
    exit 0
  fi
  echo "::warning::push raced with another commit (attempt $attempt); retrying from fresh main"
  sleep $((attempt * 3))
done

echo "::error::could not push after 5 attempts. If main is protected, the Actions bot needs a ruleset bypass (see docs/k8s-migration/runbook.md)."
exit 1
