#!/usr/bin/env bash
# Cut a production release: tag the current tip of origin/main and push the tag.
# The tag push starts .github/workflows/release.yml, which tests, builds the
# image from exactly that commit and commits the new digest for Argo CD.
#
#   scripts/release.sh v1.2.0
#
# Safe by construction: it refuses anything but a vX.Y.Z tag on origin/main whose
# staging build succeeded, and asks before pushing.
set -euo pipefail

tag=${1:?usage: scripts/release.sh vX.Y.Z}
[[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "'$tag' is not vX.Y.Z" >&2; exit 1; }

git fetch --quiet origin main --tags
if git rev-parse --verify --quiet "refs/tags/$tag" >/dev/null; then
  echo "tag $tag already exists" >&2; exit 1
fi

# Release what staging has been running, not whatever main moved to a minute ago:
# bot digest commits also land on main, so "tip of main" can be one commit ahead
# of the last application commit. Use the commit staging actually built.
staging_commit=$(jq -r '.commit' <(git show origin/main:deploy/k8s/overlays/staging/release.json))
[ -n "$staging_commit" ] || { echo "staging has not deployed anything yet" >&2; exit 1; }

conclusion=$(gh run list --workflow staging.yml --branch main --commit "$staging_commit" --limit 1 --json conclusion --jq '.[0].conclusion // "none"')
[ "$conclusion" = "success" ] || { echo "staging build for ${staging_commit:0:7} is '$conclusion', not success" >&2; exit 1; }

echo "About to release $tag at ${staging_commit:0:7}:"
git log -1 --format='  %h %s (%an, %ar)' "$staging_commit"
echo "Changes since the last release:"
last=$(git tag --list 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -1)
git log --oneline "${last:+$last..}$staging_commit" -- . ':!deploy/k8s/overlays' | sed 's/^/  /'
echo
echo "Have you checked staging.chicanodev.com (and /version.json shows ${staging_commit:0:7})?"
read -r -p "Tag and push $tag? [y/N] " answer
[ "$answer" = "y" ] || { echo "aborted"; exit 1; }

git tag -a "$tag" -m "$tag" "$staging_commit"
git push origin "refs/tags/$tag"
echo "Pushed $tag. Watch: gh run watch \$(gh run list --workflow release.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
