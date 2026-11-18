#!/usr/bin/env bash
set -euo pipefail

# Resolve real script location even when invoked via ~/.local/bin/cockpit symlink
SOURCE="${BASH_SOURCE[0]}"
while [ -h "${SOURCE}" ]; do
  DIR="$(cd -P "$(dirname "${SOURCE}")" && pwd)"
  SOURCE="$(readlink "${SOURCE}")"
  [[ ${SOURCE} != /* ]] && SOURCE="${DIR}/${SOURCE}"
done
PROJECT_ROOT="$(cd -P "$(dirname "${SOURCE}")" && pwd)"

BACKEND_DIR="${PROJECT_ROOT}/backend"
VENV_PYTHON="${BACKEND_DIR}/.venv/bin/python"
TRAY_SCRIPT="${PROJECT_ROOT}/scripts/tray_indicator.py"
HOST="127.0.0.1"
PORT="8765"
URL="http://${HOST}:${PORT}"
PID_FILE="/tmp/cockpit-dev-center.pid"
TRAY_PID_FILE="/tmp/cockpit-tray-indicator.pid"
LOG_FILE="/tmp/cockpit-dev-center.log"
TRAY_LOG_FILE="/tmp/cockpit-tray-indicator.log"
PROFILE_DIR="${HOME}/.config/cockpit-app-profile"

is_running() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 1 "${URL}/api/health" >/dev/null 2>&1
    return $?
  elif command -v ss >/dev/null 2>&1; then
    ss -tln | grep -q ":${PORT} "
    return $?
  fi
  return 1
}

is_tray_running() {
  if [[ -f "${TRAY_PID_FILE}" ]]; then
    local tpid
    tpid="$(cat "${TRAY_PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${tpid}" ]] && kill -0 "${tpid}" 2>/dev/null; then
      return 0
    fi
  fi
  pgrep -f "scripts/tray_indicator.py" >/dev/null 2>&1
  return $?
}

spawn_detached() {
  local logfile="$1"
  shift
  if command -v systemd-run >/dev/null 2>&1 && systemd-run --user --scope true >/dev/null 2>&1; then
    systemd-run --user --scope --quiet setsid "$@" </dev/null > "${logfile}" 2>&1 &
  else
    setsid "$@" </dev/null > "${logfile}" 2>&1 &
  fi
}

start_tray_indicator() {
  if is_tray_running; then
    return 0
  fi
  if [[ -f "${TRAY_SCRIPT}" ]] && [[ -x "/usr/bin/python3" ]]; then
    chmod +x "${TRAY_SCRIPT}" 2>/dev/null || true
    spawn_detached "${TRAY_LOG_FILE}" /usr/bin/python3 "${TRAY_SCRIPT}"
    disown 2>/dev/null || true
  fi
}

stop_all() {
  # 1. Stop FastAPI backend
  if [[ -f "${PID_FILE}" ]]; then
    kill "$(cat "${PID_FILE}")" 2>/dev/null || true
    rm -f "${PID_FILE}"
  fi
  pkill -f "uvicorn main:app.*--port ${PORT}" 2>/dev/null || true

  # 2. Stop Tray Indicator
  if [[ -f "${TRAY_PID_FILE}" ]]; then
    kill "$(cat "${TRAY_PID_FILE}")" 2>/dev/null || true
    rm -f "${TRAY_PID_FILE}"
  fi
  pkill -f "scripts/tray_indicator.py" 2>/dev/null || true

  # 3. Close isolated Cockpit app window if open
  pkill -f "user-data-dir=${PROFILE_DIR}" 2>/dev/null || true
}

if [[ "${1:-}" == "--stop" ]]; then
  stop_all
  echo "[Cockpit] Stopped backend server, tray indicator, and desktop window."
  exit 0
fi

if [[ "${1:-}" == "--restart" ]]; then
  if [[ -f "${PID_FILE}" ]]; then
    kill "$(cat "${PID_FILE}")" 2>/dev/null || true
    rm -f "${PID_FILE}"
  fi
  pkill -f "uvicorn main:app.*--port ${PORT}" 2>/dev/null || true
  if [[ -f "${TRAY_PID_FILE}" ]]; then
    kill "$(cat "${TRAY_PID_FILE}")" 2>/dev/null || true
    rm -f "${TRAY_PID_FILE}"
  fi
  pkill -f "scripts/tray_indicator.py" 2>/dev/null || true
  sleep 0.4
fi

if ! is_running; then
  if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "[Cockpit] Python virtual environment not found. Running install.sh first..."
    "${PROJECT_ROOT}/install.sh" --no-launch
  fi

  echo "[Cockpit] Starting ultra-lightweight FastAPI backend & Guard Engine on ${URL}..."
  cd "${BACKEND_DIR}"
  spawn_detached "${LOG_FILE}" "${VENV_PYTHON}" -m uvicorn main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers 1 \
    --no-access-log \
    --log-level warning
  sleep 0.2
  pgrep -n -f "uvicorn main:app.*--port ${PORT}" > "${PID_FILE}" 2>/dev/null || true
  disown 2>/dev/null || true

  # Wait up to 6 seconds for server socket readiness
  for _ in {1..30}; do
    if is_running; then
      break
    fi
    sleep 0.2
  done
fi

# Always ensure the Ubuntu Top Bar tray indicator is running in the background
start_tray_indicator

if [[ "${1:-}" == "--backend-only" ]] || [[ "${1:-}" == "--tray-only" ]]; then
  echo "[Cockpit] Backend and Ubuntu Top Bar tray indicator are active at ${URL}"
  exit 0
fi

# If --open-only or normal launch, check if window is already open and focus it if possible
if command -v wmctrl >/dev/null 2>&1; then
  if wmctrl -lx 2>/dev/null | grep -qi "cockpit"; then
    wmctrl -x -a "Cockpit" 2>/dev/null && exit 0
  fi
elif command -v xdotool >/dev/null 2>&1; then
  if xdotool search --class "Cockpit" windowactivate 2>/dev/null; then
    exit 0
  fi
fi

mkdir -p "${PROFILE_DIR}"

# Launch isolated Chrome/Chromium instance with explicit WM class so GNOME treats Cockpit as a standalone native app
for BROWSER_BIN in google-chrome google-chrome-stable chromium chromium-browser brave-browser microsoft-edge; do
  if command -v "${BROWSER_BIN}" >/dev/null 2>&1; then
    spawn_detached "/dev/null" "${BROWSER_BIN}" \
      --app="${URL}" \
      --class=Cockpit \
      --name=Cockpit \
      --user-data-dir="${PROFILE_DIR}" \
      --no-first-run \
      --no-default-browser-check \
      --disable-extensions \
      --window-size=1360,860
    disown 2>/dev/null || true
    exit 0
  fi
done

if command -v xdg-open >/dev/null 2>&1; then
  nohup xdg-open "${URL}" >/dev/null 2>&1 &
else
  echo "[Cockpit] Open ${URL} in your browser."
fi
