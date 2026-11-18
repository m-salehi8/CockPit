#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${PROJECT_ROOT}/ ../launch.sh" "$@" 2>/dev/null || exec "$(cd "${PROJECT_ROOT}/.." && pwd)/launch.sh" "$@"
