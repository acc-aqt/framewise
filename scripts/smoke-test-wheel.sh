#!/usr/bin/env bash
# Checks that a built framewise wheel works on its own, as a photographer
# installs it: runs `uvx --python 3.13 --from <wheel> framewise review` on a one-Frame
# Session and checks over HTTP that the Review UI and the Session load and
# that the Frame gets analyzed.
#
# Needs uv, curl and ExifTool, and nothing from the checkout but a test photo.
# On Linux it installs the wheel with the portable extra, which framewise
# needs there.
#
# Usage: scripts/smoke-test-wheel.sh <wheel> [--help]

set -euo pipefail

print_help() {
  awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"
}

fail() {
  echo "smoke-test: $*" >&2
  exit 1
}

case "${1:-}" in
  "") fail "give the wheel to test. See scripts/smoke-test-wheel.sh --help." ;;
  -h | --help)
    print_help
    exit 0
    ;;
esac

wheel="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
[[ -f "$wheel" ]] || fail "no wheel at $1."
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
port=8765
url="http://127.0.0.1:$port"

for command in uv curl exiftool; do
  command -v "$command" > /dev/null || fail "$command is not installed."
done

if [[ "$(uname -s)" == Linux ]]; then
  package="framewise[portable] @ file://$wheel"
else
  package="$wheel"
fi

fetch() {
  curl --silent --fail "$url$1" || true
}

scratch="$(mktemp -d)"
server_pid=""
cleanup() {
  [[ -n "$server_pid" ]] && kill "$server_pid" 2> /dev/null
  rm -rf "$scratch"
}
trap cleanup EXIT

mkdir "$scratch/session"
cp "$repo_root/backend/tests/fixtures/faces/eyes-open.jpg" "$scratch/session/DSCF0001.JPG"
export FRAMEWISE_DATA_DIR="$scratch/data"

echo "+ uvx --python 3.13 --from '$package' framewise review <session> --port $port"
uvx --python 3.13 --from "$package" framewise review "$scratch/session" --port "$port" > "$scratch/log" 2>&1 &
server_pid=$!

# The first run installs framewise and its dependencies before it serves.
for _ in $(seq 600); do
  curl --silent --fail "$url/api/session" > "$scratch/session.json" && break
  if ! kill -0 "$server_pid" 2> /dev/null; then
    cat "$scratch/log" >&2
    fail "framewise exited before serving the Review UI."
  fi
  sleep 1
done
[[ -s "$scratch/session.json" ]] || {
  cat "$scratch/log" >&2
  fail "framewise did not serve the Review UI within 10 minutes."
}

[[ "$(cat "$scratch/session.json")" == *'"total_frames":1'* ]] ||
  fail "the Session does not have the one Frame: $(cat "$scratch/session.json")"
[[ "$(fetch /)" == *"<app-root"* ]] || fail "$url/ does not serve the Review UI."
[[ "$(fetch /api/about)" == *'"changelog":[{'* ]] ||
  fail "the Review UI shows no Changelog under What's new."

# The first analysis downloads the portable Providers' models.
for _ in $(seq 600); do
  [[ "$(fetch /api/progress)" == *'"frames_left":0'* ]] && break
  sleep 1
done
[[ "$(fetch /api/progress)" == *'"frames_left":0'* ]] || {
  cat "$scratch/log" >&2
  fail "framewise did not analyze the Frame within 10 minutes."
}
cat "$scratch/log"

echo "smoke-test: the wheel serves the Review UI with the Session and the Changelog, and analyzes the Frame."
