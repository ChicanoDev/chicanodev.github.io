#!/usr/bin/env bash
# Merge and release scheduled blog PRs whose posts are due.
# Called by .github/workflows/blog-ship.yml (started hourly by n8n). The rules
# live in scripts/blog-schedule.mjs (unit-tested); this file is only the glue to
# GitHub. Exit 1 means "something needs a human" and the summary says what.
#
# Needs: GH_TOKEN (contents, pull-requests and actions: write), a full-history
# checkout of main with push credentials, Node.
set -euo pipefail

LABEL=${BLOG_LABEL:-blog:scheduled}
AUTHOR=${BLOG_AUTHOR:-dgvigil}
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SUMMARY=${GITHUB_STEP_SUMMARY:-/dev/stdout}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

say() { printf '%s\n' "$*" >> "$SUMMARY"; }
needs_human=0
merged=()

say "## Scheduled blog PRs ($NOW)"

# The PR list is read on fd 3 so nothing inside the loop (gh, git) can consume it.
while IFS=$'\t' read -r -u 3 number sha author cross title; do
  [ -n "$number" ] || continue
  pr="#$number $title"
  if [ "$cross" = true ] || [ "$author" != "$AUTHOR" ]; then
    say "- $pr: skipped, only same-repo PRs by $AUTHOR are merged automatically"; continue
  fi

  # Every check on the head commit must have finished green (none pending).
  # shellcheck disable=SC2016 # $c is a jq variable, not a shell one
  if ! gh pr view "$number" --json statusCheckRollup --jq '
      [.statusCheckRollup[] | (.conclusion // .state // "")] as $c
      | ($c | length) > 0 and all($c[]; . == "SUCCESS" or . == "SKIPPED" or . == "NEUTRAL")' | grep -qx true; then
    say "- $pr: waiting, checks are not all green yet"; continue
  fi

  gh pr view "$number" --json files --jq '.files[].path' > "$work/files"
  classes=$(node scripts/blog-schedule.mjs classify < "$work/files")
  if [ "$(jq '.disallowed | length' <<<"$classes")" -gt 0 ]; then
    say "- $pr: **not a content-only PR** ($(jq -r '.disallowed | join(", ")' <<<"$classes")). Remove the label or split the PR."
    needs_human=1; continue
  fi

  git fetch --quiet origin "refs/pull/$number/head"
  if [ "$(git rev-parse FETCH_HEAD)" != "$sha" ]; then
    say "- $pr: head moved while checking, next run will retry"; continue
  fi
  files=()
  while read -r post; do
    out="$work/$number-$(basename "$post")"
    git show "$sha:$post" > "$out"
    files+=("$out")
  done < <(jq -r '.posts[]' <<<"$classes")

  if ! verdict=$(node scripts/blog-schedule.mjs check --now "$NOW" "${files[@]}" 2>&1); then
    say "- $pr: **invalid post**: $verdict"; needs_human=1; continue
  fi
  due_at=$(jq -r .dueAt <<<"$verdict")
  if [ "$(jq -r .due <<<"$verdict")" != true ]; then
    say "- $pr: scheduled for $due_at"; continue
  fi

  # --match-head-commit: refuse if anything was pushed after the checks we read.
  if gh pr merge "$number" --squash --match-head-commit "$sha" --subject "$title (#$number)"; then
    say "- $pr: **merged** (due $due_at)"
    merged+=("$number")
  else
    say "- $pr: **merge failed**, see the log"; needs_human=1
  fi
done 3< <(gh pr list --label "$LABEL" --state open --limit 50 \
  --json number,headRefOid,author,isCrossRepository,title \
  --jq '.[] | [.number, .headRefOid, .author.login, .isCrossRepository, .title] | @tsv')

if [ "${#merged[@]}" -eq 0 ]; then
  # Nothing new merged: still make sure already-released posts that became due
  # go live now, instead of waiting for GitHub's unreliable hourly cron.
  gh workflow run publish.yml --ref main
  say "No PR merged; started *Publish scheduled posts*."
  exit "$needs_human"
fi

git fetch --quiet --tags origin main
# Pushes made with GITHUB_TOKEN start no workflows, so staging is started by hand.
gh workflow run staging.yml --ref main

last=$(git tag --list 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -1)
verdict=$(git diff --name-only "$last" origin/main | node scripts/blog-schedule.mjs releasable)
if [ "$(jq -r .ok <<<"$verdict")" != true ]; then
  say "### Not released automatically"
  say "main has changes since $last that are not blog content, so a human must release:"
  mapfile -t blocking < <(jq -r '.blocking[]' <<<"$verdict")
  say '```'
  printf '%s\n' "${blocking[@]}" >> "$SUMMARY"
  git log --oneline "$last..origin/main" -- "${blocking[@]}" >> "$SUMMARY"
  say '```'
  say "Check staging, then run \`scripts/release.sh\`. The merged posts stay hidden in production until then."
  exit 1
fi

tag=$(git tag --list | node scripts/blog-schedule.mjs next-tag)
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git tag -a "$tag" -m "$tag: scheduled post(s) #${merged[*]}" origin/main
git push origin "refs/tags/$tag"
gh workflow run release.yml --ref main -f tag="$tag"
say "### Released $tag"
say "Tagged origin/main and started the Release workflow (PRs #${merged[*]})."
exit "$needs_human"
