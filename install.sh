#!/usr/bin/env bash
set -euo pipefail

REPO="pareekshithbompally/pai-cli"
PACKAGE_NAME="pai-cli"
MIN_PYTHON="3.10"
INSTALL_SPEC="${PAI_INSTALL_SPEC:-git+https://github.com/${REPO}.git}"
GOOGLE_DEPS=("google-cloud-bigquery" "db-dtypes")
BIN_DIR="${PIPX_BIN_DIR:-$HOME/.local/bin}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

info()  { printf "${GREEN}▸${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}▸${NC} %s\n" "$*"; }
error() { printf "${RED}✗${NC} %s\n" "$*" >&2; exit 1; }

OS="$(uname -s)"
case "$OS" in
    Darwin) PLATFORM="macOS" ;;
    Linux) PLATFORM="Linux" ;;
    *) error "Unsupported platform: $OS" ;;
esac

find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            local ver
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || continue
            local major minor req_major req_minor
            major=${ver%%.*}
            minor=${ver#*.}
            req_major=${MIN_PYTHON%%.*}
            req_minor=${MIN_PYTHON#*.}
            if [ "$major" -gt "$req_major" ] || { [ "$major" -eq "$req_major" ] && [ "$minor" -ge "$req_minor" ]; }; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON=$(find_python) || error "Python >=${MIN_PYTHON} is required. Install from https://python.org"
info "Found Python: $($PYTHON --version 2>&1)"

if ! command -v pipx >/dev/null 2>&1; then
    printf "\n${RED}${BOLD}pipx is required but not installed.${NC}\n\n"
    if [ "$PLATFORM" = "macOS" ]; then
        info "Install with Homebrew:"
        printf "    ${BOLD}brew install pipx${NC}\n"
    else
        info "Install with your package manager:"
        printf "    ${BOLD}sudo apt install pipx${NC}        # Debian / Ubuntu\n"
        printf "    ${BOLD}sudo dnf install pipx${NC}        # Fedora\n"
        printf "    ${BOLD}sudo pacman -S python-pipx${NC}   # Arch\n"
    fi
    printf "\n"
    info "Or install from source: https://pipx.pypa.io/stable/installation/"
    printf "\n"
    info "Then re-run this script."
    exit 1
fi

info "Found pipx: $(pipx --version 2>&1)"

info "Installing pai-cli with pipx..."
if ! pipx install --force --python "$PYTHON" "$INSTALL_SPEC" >/dev/null 2>&1; then
    error "Installation failed. Run manually to see details: pipx install --force --python \"$PYTHON\" \"$INSTALL_SPEC\""
fi

info "Injecting Google billing dependencies..."
if ! pipx inject --force "$PACKAGE_NAME" "${GOOGLE_DEPS[@]}" >/dev/null 2>&1; then
    error "Base install succeeded, but Google billing dependencies failed. Run manually: pipx inject \"$PACKAGE_NAME\" ${GOOGLE_DEPS[*]}"
fi

printf "\n${GREEN}${BOLD}pai-cli installed successfully.${NC}\n"
if [ -x "$BIN_DIR/pai" ]; then
    info "Run 'pai --help' to get started."
else
    warn "pai was installed but is not on your PATH yet."
    warn "Run 'pipx ensurepath' and restart your shell."
fi
