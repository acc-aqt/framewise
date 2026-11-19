#!/usr/bin/env bash
# Cuts a Release of framewise (ADR-0007):
#
#   1. checks the version is X.Y.Z and newer than the last Release, that
#      CHANGELOG.md has entries under "## Unreleased", and that you are on a
#      clean main that is up to date with origin;
#   2. sets the version in backend/pyproject.toml and backend/uv.lock, unless
#      it is already X.Y.Z;
#   3. turns "## Unreleased" into "## X.Y.Z — <today>" under a fresh, empty
#      "## Unreleased", and checks the Changelog is still in the shape the
#      Review UI shows;
#   4. commits "Release vX.Y.Z" and tags it vX.Y.Z, with the release notes
#      as the tag's message;
#   5. shows the commit and the release notes, and only after you confirm
#      pushes main and the tag and creates the GitHub Release with gh.
#
# --dry-run shows the Changelog change and the release notes and changes
# nothing. It only warns when you are not on a clean, up-to-date main.
#
# Usage: scripts/release.sh X.Y.Z [--dry-run] | --help

set -euo pipefail

print_help() {
  awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"
}

fail() {
  echo "release: $*" >&2
  exit 1
}

warn() {
  echo "release: warning: $*" >&2
}

version=""
dry_run=false
for argument in "$@"; do
  case "$argument" in
    -h | --help)
      print_help
      exit 0
      ;;
    --dry-run) dry_run=true ;;
    -*) fail "unknown option '$argument'. See scripts/release.sh --help." ;;
    *)
      [[ -z "$version" ]] || fail "give one version. See scripts/release.sh --help."
      version="$argument"
      ;;
  esac
done
[[ -n "$version" ]] || fail "give the version to release, such as 0.2.0. See scripts/release.sh --help."
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "'$version' is not a version like 0.2.0."

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
changelog="$repo_root/CHANGELOG.md"
pyproject="$repo_root/backend/pyproject.toml"
tag="v$version"
today="$(date +%Y-%m-%d)"
heading="## $version — $today"

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

# Whether version $1 is newer than version $2.
is_newer() {
  [[ "$1" != "$2" && "$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n | tail -n 1)" == "$1" ]]
}

check_git_state() {
  local problems=()
  [[ "$(git -C "$repo_root" branch --show-current)" == main ]] || problems+=("you are not on main")
  [[ -z "$(git -C "$repo_root" status --porcelain)" ]] || problems+=("the working tree has uncommitted changes")
  git -C "$repo_root" fetch --quiet origin main
  [[ "$(git -C "$repo_root" rev-parse HEAD)" == "$(git -C "$repo_root" rev-parse origin/main)" ]] ||
    problems+=("main is not the same as origin/main")
  for problem in ${problems[@]+"${problems[@]}"}; do
    if $dry_run; then
      warn "$problem; a real run would stop here."
    else
      fail "$problem."
    fi
  done
}

check_version() {
  if git -C "$repo_root" rev-parse --quiet --verify "refs/tags/$tag" > /dev/null; then
    fail "$tag is already tagged."
  fi
  local last
  last="$(grep -m 1 -E '^## [0-9]+\.[0-9]+\.[0-9]+ ' "$changelog" | awk '{ print $2 }' || true)"
  if [[ -n "$last" ]] && ! is_newer "$version" "$last"; then
    fail "$version is not newer than the last Release, $last."
  fi
}

unreleased_entries() {
  awk '/^## Unreleased$/ { inside = 1; next } /^## / { inside = 0 } inside && /^- /' "$changelog"
}

# Writes the Changelog with Unreleased turned into the Release, to $1.
write_released_changelog() {
  awk -v heading="$heading" '
    !done && $0 == "## Unreleased" { print; print ""; print heading; done = 1; next }
    { print }
  ' "$changelog" > "$1"
}

# Prints the Release's section of the Changelog at $1, without its heading.
release_notes() {
  awk -v heading="$heading" '
    $0 == heading { inside = 1; next }
    inside && /^## / { exit }
    inside { lines[++count] = $0 }
    END {
      first = 1; while (first <= count && lines[first] == "") first++
      last = count; while (last >= first && lines[last] == "") last--
      for (i = first; i <= last; i++) print lines[i]
    }
  ' "$1"
}

set_version() {
  local current
  current="$(sed -n -E 's/^version = "(.*)"$/\1/p' "$pyproject" | head -n 1)"
  if [[ "$current" == "$version" ]]; then
    echo "release: backend/pyproject.toml already says $version."
    return
  fi
  is_newer "$version" "$current" || fail "$version is not newer than backend/pyproject.toml's $current."
  sed -i.bak -E "s/^version = \"$current\"$/version = \"$version\"/" "$pyproject"
  rm "$pyproject.bak"
  (cd "$repo_root/backend" && uv lock --quiet)
}

confirm() {
  local answer
  read -r -p "$1 [y/N] " answer
  [[ "$answer" == y || "$answer" == Y ]]
}

command -v git > /dev/null || fail "git is not installed."
$dry_run || command -v gh > /dev/null || fail "gh is not installed. Install it from https://cli.github.com."
$dry_run || command -v uv > /dev/null || fail "uv is not installed."

check_git_state
check_version
[[ -n "$(unreleased_entries)" ]] || fail "CHANGELOG.md has no entries under '## Unreleased', so there is nothing to release."

released="$scratch/CHANGELOG.md"
notes="$scratch/notes.md"
write_released_changelog "$released"
release_notes "$released" > "$notes"

if $dry_run; then
  echo "release: CHANGELOG.md would change like this:"
  diff -u "$changelog" "$released" || true
  echo
  echo "release: the GitHub Release $tag would say:"
  cat "$notes"
  exit 0
fi

set_version
cp "$released" "$changelog"
(cd "$repo_root/backend" && uv run --quiet pytest --quiet tests/test_about_api.py) ||
  fail "the Changelog or version check failed. Undo with: git -C '$repo_root' checkout -- CHANGELOG.md backend/pyproject.toml backend/uv.lock"

git -C "$repo_root" add CHANGELOG.md backend/pyproject.toml backend/uv.lock
git -C "$repo_root" commit --quiet -m "Release $tag"
git -C "$repo_root" tag --annotate --cleanup=verbatim --file "$notes" "$tag"

git -C "$repo_root" show --stat HEAD
echo
echo "release: the GitHub Release $tag will say:"
cat "$notes"
echo

publish="git push --atomic origin main $tag && gh release create $tag --title 'framewise $version' --notes-from-tag"
if ! confirm "Push main and $tag to origin and publish the GitHub Release?"; then
  echo "release: nothing was pushed. To publish later, run:"
  echo "  $publish"
  echo "or undo the Release with: git tag -d $tag && git reset --hard HEAD~1"
  exit 0
fi

git -C "$repo_root" push --atomic origin main "$tag"
gh release create "$tag" --title "framewise $version" --notes-from-tag
