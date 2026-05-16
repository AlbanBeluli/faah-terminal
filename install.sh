#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/AlbanBeluli/faah-terminal.git"
RAW_INSTALL_URL="https://raw.githubusercontent.com/AlbanBeluli/faah-terminal/main/install.sh"
START_MARKER="# >>> faah-terminal >>>"
END_MARKER="# <<< faah-terminal <<<"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
success() { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || return 1
}

ensure_path_line() {
  local rc_file="$1"
  local path_line='export PATH="$HOME/.local/bin:$PATH"'
  touch "$rc_file"
  if ! grep -Fq 'export PATH="$HOME/.local/bin:$PATH"' "$rc_file" && \
     ! grep -Fq "export PATH=\"\$HOME/.local/bin:\$PATH\"" "$rc_file" && \
     ! grep -Fq 'export PATH=$HOME/.local/bin:$PATH' "$rc_file"; then
    {
      printf '\n# Added by faah-terminal installer\n'
      printf '%s\n' "$path_line"
    } >> "$rc_file"
  fi
}

install_shell_hook() {
  local shell_name="$1"
  local rc_file="$2"
  local hook_cmd="$3"
  local temp_file

  mkdir -p "$(dirname "$rc_file")"
  touch "$rc_file"
  ensure_path_line "$rc_file"

  temp_file="$(mktemp)"
  awk \
    -v start="$START_MARKER" \
    -v end="$END_MARKER" \
    'BEGIN { skip=0 } $0 == start { skip=1; next } $0 == end { skip=0; next } skip == 0 { print }' \
    "$rc_file" > "$temp_file"

  {
    cat "$temp_file"
    printf '\n%s\n' "$START_MARKER"
    printf '# Terminal error drama alarm: play Faah when interactive commands fail.\n'
    printf 'if command -v faah >/dev/null 2>&1; then\n'
    printf '  %s\n' "$hook_cmd"
    printf 'fi\n'
    printf '%s\n' "$END_MARKER"
  } > "$rc_file"
  rm -f "$temp_file"
  success "Installed ${shell_name} hook in ${rc_file}"
}

pipx_install() {
  local pipx_cmd=("$@")
  if "${pipx_cmd[@]}" install --force "git+${REPO_URL}"; then
    return 0
  fi

  warn "pipx install hit an existing/broken venv; reinstalling cleanly"
  "${pipx_cmd[@]}" uninstall faah-terminal >/dev/null 2>&1 || true
  "${pipx_cmd[@]}" install "git+${REPO_URL}"
}

install_python_package() {
  if need_cmd pipx; then
    info "Installing faah-terminal with pipx"
    pipx_install pipx
    return
  fi

  if python3 -m pipx --version >/dev/null 2>&1; then
    info "Installing faah-terminal with python3 -m pipx"
    pipx_install python3 -m pipx
    return
  fi

  if need_cmd brew; then
    info "pipx not found; installing pipx with Homebrew"
    brew install pipx
    pipx ensurepath || true
    pipx install --force "git+${REPO_URL}"
    return
  fi

  info "pipx not found; falling back to python3 -m pip --user"
  python3 -m pip install --user --upgrade "git+${REPO_URL}"
}

main() {
  if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    cat <<EOF
Faah Terminal installer

Usage:
  curl -fsSL ${RAW_INSTALL_URL} | bash

Environment:
  FAAH_NO_HOOK=1       install CLI only, do not edit shell rc file
  FAAH_SHELL=zsh       force shell: zsh, bash, or fish
EOF
    exit 0
  fi

  need_cmd python3 || fail "python3 is required"
  need_cmd git || fail "git is required"

  info "Installing Faah Terminal"
  install_python_package

  local faah_bin=""
  if need_cmd faah; then
    faah_bin="$(command -v faah)"
  elif [ -x "$HOME/.local/bin/faah" ]; then
    faah_bin="$HOME/.local/bin/faah"
  else
    fail "faah installed, but the executable was not found. Add ~/.local/bin to PATH and retry."
  fi
  success "faah installed at ${faah_bin}"

  if [ "${FAAH_NO_HOOK:-0}" = "1" ]; then
    warn "Skipping shell hook because FAAH_NO_HOOK=1"
  else
    local detected_shell shell_base
    detected_shell="${FAAH_SHELL:-${SHELL:-}}"
    shell_base="$(basename "$detected_shell")"
    case "$shell_base" in
      zsh)
        install_shell_hook "zsh" "$HOME/.zshrc" 'eval "$(faah init zsh)"'
        ;;
      bash)
        install_shell_hook "bash" "$HOME/.bashrc" 'eval "$(faah init bash)"'
        ;;
      fish)
        install_shell_hook "fish" "$HOME/.config/fish/config.fish" 'faah init fish | source'
        ;;
      *)
        warn "Unknown shell '${shell_base}'. CLI installed; add a hook manually with: faah init zsh"
        ;;
    esac
  fi

  info "Testing sound"
  "$faah_bin" test || warn "Test alert failed, but installation completed"

  cat <<'EOF'

Faah Terminal is ready.

Open a new terminal, or reload your shell:
  exec $SHELL

Try it:
  false
  faah run -- python3 -c 'raise SystemExit(1)'

Config:
  faah config show
  faah config set cooldown_seconds 5
  faah snooze 30
EOF
}

main "$@"
