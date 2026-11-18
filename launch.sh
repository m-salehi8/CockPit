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
HOST="127.0.0.1"
PORT="8765"
URL="http://${HOST}:${PORT}"
PID_FILE="/tmp/cockpit-dev-center.pid"
LOG_FILE="/tmp/cockpit-dev-center.log"
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

if [[ "${1:-}" == "--stop" ]]; then
  if [[ -f "${PID_FILE}" ]]; then
    kill "$(cat "${PID_FILE}")" 2>/dev/null || true
    rm -f "${PID_FILE}"
  fi
  pkill -f "uvicorn main:app.*--port ${PORT}" 2>/dev/null || true
  echo "[Cockpit] Stopped backend server on ${URL}."
  exit 0
fi

if [[ "${1:-}" == "--restart" ]]; then
  if [[ -f "${PID_FILE}" ]]; then
    kill "$(cat "${PID_FILE}")" 2>/dev/null || true
    rm -f "${PID_FILE}"
  fi
  pkill -f "uvicorn main:app.*--port ${PORT}" 2>/dev/null || true
  sleep 0.4
fi

if ! is_running; then
  if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "[Cockpit] Python virtual environment not found. Running install.sh first..."
    "${PROJECT_ROOT}/install.sh" --no-launch
  fi

  echo "[Cockpit] Starting ultra-lightweight FastAPI backend on ${URL}..."
  cd "${BACKEND_DIR}"
  nohup "${VENV_PYTHON}" -m uvicorn main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers 1 \
    --no-access-log \
    --log-level warning > "${LOG_FILE}" 2>&1 &
  echo $! > "${PID_FILE}"

  # Wait up to 6 seconds for server socket readiness
  for _ in {1..30}; do
    if is_running; then
      break
    fi
    sleep 0.2
  done
fi

if [[ "${1:-}" == "--backend-only" ]]; then
  echo "[Cockpit] Backend is active at ${URL}"
  exit 0
fi

mkdir -p "${PROFILE_DIR}"

# Launch isolated Chrome/Chromium instance with explicit WM class so GNOME treats Cockpit as a standalone native app
for BROWSER_BIN in google-chrome google-chrome-stable chromium chromium-browser brave-browser microsoft-edge; do
  if command -v "${BROWSER_BIN}" >/dev/null 2>&1; then
    nohup "${BROWSER_BIN}" \
      --app="${URL}" \
      --class=Cockpit \
      --name=Cockpit \
      --user-data-dir="${PROFILE_DIR}" \
      --no-first-run \
      --no-default-browser-check \
      --disable-extensions \
      --window-size=1360,860 \
      >/dev/null 2>&1 &
    exit 0
  fi
done

if command -v xdg-open >/dev/null 2>&1; then
  nohup xdg-open "${URL}" >/dev/null 2>&1 &
else
  echo "[Cockpit] Open ${URL} in your browser."
fi
