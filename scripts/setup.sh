#!/usr/bin/env bash
# Sets up framewise from a clone of the repo, ready for `framewise review`:
#
#   1. checks the prerequisites: uv, Node.js (warning if it is not the
#      version in frontend/.nvmrc) and, on macOS, Homebrew;
#   2. installs the system packages, with Homebrew on macOS and apt on
#      Debian and Ubuntu (through sudo unless run as root, showing the
#      command first);
#   3. builds the Review UI;
#   4. installs the backend, on Linux with the portable Providers and their
#      models. On macOS it keeps the portable Providers if you installed them.
#
# Supported: macOS, Debian and Ubuntu. On other Linux distros it stops and
# lists the packages to install yourself.
#
# Re-running is safe. Run it again after pulling to update framewise.
#
# Usage: scripts/setup.sh [--help]

set -euo pipefail

print_help() {
  awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"
}

fail() {
  echo "setup: $*" >&2
  exit 1
}

case "${1:-}" in
  "") ;;
  -h | --help)
    print_help
    exit 0
    ;;
  *) fail "unknown argument '$1'. See scripts/setup.sh --help." ;;
esac

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
platform="$(uname -s)"

check_prerequisites() {
  if ! command -v uv > /dev/null; then
    fail "uv is not installed. Install it from https://docs.astral.sh/uv/getting-started/installation/ and run this script again."
  fi

  local wanted actual
  wanted="$(tr -d '[:space:]v' < "$repo_root/frontend/.nvmrc")"
  if ! command -v node > /dev/null; then
    fail "Node.js is not installed. The frontend expects Node $wanted, as recorded in frontend/.nvmrc (nvm use reads it)."
  fi
  actual="$(node --version)"
  actual="${actual#v}"
  if [[ "$actual" != "$wanted" && "$actual" != "$wanted".* ]]; then
    echo "setup: warning: the frontend expects Node $wanted, as recorded in frontend/.nvmrc, but found Node $actual. Run 'nvm use' in frontend/ to switch if the build fails." >&2
  fi

  if [[ "$platform" == Darwin ]] && ! command -v brew > /dev/null; then
    fail "Homebrew is not installed. Install it from https://brew.sh and run this script again."
  fi
}

install_macos_packages() {
  local packages=(
    exiftool # ExifTool, which framewise needs for Rating write-back.
  )
  echo "+ brew install ${packages[*]}"
  brew install "${packages[@]}"
}

run_as_root() {
  if [[ "$EUID" -eq 0 ]]; then
    echo "+ $*"
    "$@"
  else
    echo "+ sudo $*"
    sudo "$@"
  fi
}

install_debian_packages() {
  local packages=(
    libgl1                 # OpenGL, which MediaPipe's portable Providers load.
    libegl1                # EGL, which MediaPipe's portable Providers load.
    libgles2               # OpenGL ES, which MediaPipe's portable Providers load.
    libimage-exiftool-perl # ExifTool, which framewise needs for Rating write-back.
    zenity                 # Optional: the dialog for choosing the Session folder.
  )
  run_as_root apt-get update
  run_as_root apt-get install -y "${packages[@]}"
}

stop_on_unsupported_linux() {
  fail "this Linux distro is not supported. Install the equivalents of these packages, then run this script again:
  - the OpenGL, EGL and OpenGL ES libraries, which MediaPipe's portable Providers load
  - ExifTool, which framewise needs for Rating write-back
  - zenity (optional), for choosing the Session folder in a dialog"
}

install_system_packages() {
  case "$platform" in
    Darwin) install_macos_packages ;;
    Linux)
      if command -v apt-get > /dev/null; then
        install_debian_packages
      else
        stop_on_unsupported_linux
      fi
      ;;
    MINGW* | MSYS* | CYGWIN*) fail "on Windows, run scripts/setup.ps1 in PowerShell instead." ;;
    *) fail "$platform is not supported. framewise runs on macOS, Linux and Windows." ;;
  esac
}

build_review_ui() {
  cd "$repo_root/frontend"
  npm ci
  npx ng build
}

# uv sync removes packages it is not asked for, so on macOS a re-run asks
# for the portable extra again if mediapipe shows it was installed.
has_portable_extra() {
  uv pip show --python .venv mediapipe > /dev/null 2>&1
}

install_backend() {
  cd "$repo_root/backend"
  if [[ "$platform" == Linux ]]; then
    uv sync --locked --extra portable
    uv run framewise models download
  elif has_portable_extra; then
    uv sync --locked --extra portable
  else
    uv sync --locked
  fi
}

check_prerequisites
install_system_packages
build_review_ui
install_backend

echo "framewise is set up. Review a Session with: cd backend && uv run framewise review"
