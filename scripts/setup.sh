#!/usr/bin/env bash
# Install the shared tools and skills on macOS, Linux, or WSL. No sudo.
set -euo pipefail

repo_dir="${TSTACK_DIR:-$HOME/src/tstack}"
repo_url="https://github.com/S0nrxse/tstack.git"
export PATH="$HOME/.local/bin:$PATH"

for dependency in git curl python3; do
  command -v "$dependency" >/dev/null || {
    printf 'Install %s first, then rerun this script.\n' "$dependency" >&2
    exit 1
  }
done
case "$(uname -s)" in
  Darwin|Linux) ;;
  *) printf 'Run this setup in macOS, Linux, or WSL.\n' >&2; exit 1 ;;
esac

if [ ! -e "$repo_dir" ]; then
  mkdir -p "$(dirname "$repo_dir")"
  git clone "$repo_url" "$repo_dir"
fi
git -C "$repo_dir" rev-parse --show-toplevel >/dev/null
case "$(git -C "$repo_dir" remote get-url origin)" in
  "$repo_url"|https://github.com/S0nrxse/tstack|git@github.com:S0nrxse/tstack.git) ;;
  *) printf 'Expected your S0nrxse/tstack fork at %s.\n' "$repo_dir" >&2; exit 1 ;;
esac

installer_dir="$(mktemp -d)"
trap 'rm -rf "$installer_dir"' EXIT
curl --fail --silent --show-error --location https://t3.codes/install.sh -o "$installer_dir/t3.sh"
if [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = x86_64 ]; then
  if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || true)" = 1 ]; then
    T3CODE_CHANNEL=nightly arch -arm64 /bin/sh "$installer_dir/t3.sh"
  else
    printf 'Intel Mac: install the Nightly desktop app from https://t3.codes/download (no standalone CLI archive).\n'
  fi
else
  T3CODE_CHANNEL=nightly sh "$installer_dir/t3.sh"
fi
curl --fail --silent --show-error --location https://claude.ai/install.sh -o "$installer_dir/claude.sh"
bash "$installer_dir/claude.sh"

python3 "$repo_dir/scripts/sync-skills.py" --pull --install-auto-sync

# Noninteractive SSH shells and desktop apps also need to discover these tools.
path_line='export PATH="$HOME/.local/bin:$PATH"'
for profile in "$HOME/.profile" "$HOME/.zshenv" "$HOME/.bashrc"; do
  if ! grep -Fqx "$path_line" "$profile" 2>/dev/null; then
    printf '\n# TStack tools\n%s\n' "$path_line" >> "$profile"
  fi
done

if command -v t3 >/dev/null; then t3 --version; fi
claude --version
printf '\nSetup complete. Skills sync hourly from your fork.\n'
printf 'Edit skills in %s/skills, then commit and push to share changes.\n' "$repo_dir"
printf 'Run claude auth login on this machine if it is not signed in.\n'
printf 'Restart T3 Code when ready, then refresh Settings > Providers.\n'
printf 'For desktop T3 Code, install the Nightly app from https://t3.codes/download.\n'
