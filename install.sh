#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
DESKTOP_DIR="${HOME}/.local/share/applications"
DESKTOP_FILE="${DESKTOP_DIR}/cockpit.desktop"
LOCAL_BIN_DIR="${HOME}/.local/bin"
CLI_SYMLINK="${LOCAL_BIN_DIR}/cockpit"
ICON_PATH="${PROJECT_ROOT}/cockpit.svg"

echo "================================================================"
echo " Cockpit — Ubuntu 8GB System Assistant & Dev Control Center"
echo "================================================================"

# Clean up any legacy Octane artifacts
rm -rf "${DESKTOP_DIR}/octane.desktop" \
       "${DESKTOP_DIR}/ubuntu-dev-center.desktop" \
       "${LOCAL_BIN_DIR}/octane" \
       "${HOME}/.config/octane-app-profile" \
       "${PROJECT_ROOT}/octane.svg" \
       "${PROJECT_ROOT}/octane.desktop" \
       "${PROJECT_ROOT}/scripts/octane.desktop" \
       "${PROJECT_ROOT}/scripts/ubuntu-dev-center.desktop" \
       "${FRONTEND_DIR}/public/octane.svg" 2>/dev/null || true

# 1. Setup Python Virtual Environment & Backend Dependencies
echo "[1/4] Setting up Python virtual environment in backend/.venv..."
python3 -m venv "${BACKEND_DIR}/.venv"
"${BACKEND_DIR}/.venv/bin/pip" install --upgrade pip -q
"${BACKEND_DIR}/.venv/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" -q
echo "      Backend dependencies installed."

# 2. Build Vue 3 + Vite + Tailwind Frontend
echo "[2/4] Installing frontend dependencies and compiling static bundle..."
cd "${FRONTEND_DIR}"
if [[ ! -d "node_modules" ]]; then
  npm install --no-fund --no-audit --cache /tmp/cockpit-npm-cache
fi
npm run build
echo "      Frontend compiled into frontend/dist."

# 3. Install CLI symlink (~/.local/bin/cockpit)
echo "[3/4] Installing CLI command symlink to ${CLI_SYMLINK}..."
chmod +x "${PROJECT_ROOT}/launch.sh"
chmod +x "${PROJECT_ROOT}/scripts/launch.sh" 2>/dev/null || true
mkdir -p "${LOCAL_BIN_DIR}"
ln -sf "${PROJECT_ROOT}/launch.sh" "${CLI_SYMLINK}"

# 4. Install Ubuntu .desktop Application Shortcut
echo "[4/4] Installing Ubuntu desktop entry to ${DESKTOP_FILE}..."
mkdir -p "${DESKTOP_DIR}"

cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Cockpit
GenericName=Ubuntu System Assistant & RAM Guard
Comment=Ultra-lightweight Ubuntu 8GB System Assistant, RAM Rescue & Developer Control Center
Exec=${PROJECT_ROOT}/launch.sh
Icon=${ICON_PATH}
Terminal=false
Categories=System;Utility;Development;Monitor;
Keywords=cockpit;system;monitor;ram;swap;ports;packages;cleaner;systemd;ubuntu;
StartupWMClass=Cockpit
StartupNotify=true
EOF

# Keep a copy inside project root and scripts/cockpit.desktop
cp "${DESKTOP_FILE}" "${PROJECT_ROOT}/cockpit.desktop"
cp "${DESKTOP_FILE}" "${PROJECT_ROOT}/scripts/cockpit.desktop"
chmod +x "${DESKTOP_FILE}" "${PROJECT_ROOT}/cockpit.desktop"

# Refresh GNOME / freedesktop application database
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${DESKTOP_DIR}" >/dev/null 2>&1 || true
fi

if command -v xdg-desktop-menu >/dev/null 2>&1; then
  xdg-desktop-menu forceupdate >/dev/null 2>&1 || true
fi

echo "================================================================"
echo " Installation complete!"
echo " - CLI Command:      ${CLI_SYMLINK} (run 'cockpit' from terminal)"
echo " - Desktop shortcut: ${DESKTOP_FILE}"
echo " - Custom Icon:      ${ICON_PATH}"
echo "================================================================"

if [[ "${1:-}" != "--no-launch" ]]; then
  "${PROJECT_ROOT}/launch.sh"
fi
