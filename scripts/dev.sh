#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  # Export all variables from .env for this process and its children.
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

echo "[polaris] Starting local infra (DynamoDB Local)…"
docker compose -f "${ROOT_DIR}/docker-compose.yml" up -d

BACKEND_VENV="${ROOT_DIR}/backend/.venv"
if [[ ! -d "${BACKEND_VENV}" ]]; then
  echo "[polaris] Creating backend venv…"
  python3 -m venv "${BACKEND_VENV}"
fi

echo "[polaris] Installing/updating backend deps…"
"${BACKEND_VENV}/bin/python" -m pip install --upgrade pip >/dev/null
"${BACKEND_VENV}/bin/pip" install -r "${ROOT_DIR}/backend/requirements.txt" >/dev/null

echo "[polaris] Ensuring frontend deps…"
if [[ ! -d "${ROOT_DIR}/frontend/node_modules" ]]; then
  (cd "${ROOT_DIR}/frontend" && npm install)
fi

BACKEND_PORT="${PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

echo "[polaris] Starting backend on :${BACKEND_PORT}…"
(
  cd "${ROOT_DIR}"
  export PORT="${BACKEND_PORT}"
  export FRONTEND_BASE_URL="${FRONTEND_BASE_URL:-http://localhost:${FRONTEND_PORT}}"
  export FRONTEND_URL="${FRONTEND_URL:-http://localhost:${FRONTEND_PORT}}"
  export DDB_ENDPOINT="${DDB_ENDPOINT:-http://localhost:8000}"
  export DDB_TABLE_NAME="${DDB_TABLE_NAME:-polaris-rfp-local}"
  "${BACKEND_VENV}/bin/uvicorn" app.main:app --reload --port "${BACKEND_PORT}" --app-dir "${ROOT_DIR}/backend"
) &
BACKEND_PID=$!

cleanup() {
  echo
  echo "[polaris] Shutting down…"
  kill "${BACKEND_PID}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "[polaris] Starting frontend on :${FRONTEND_PORT}…"
cd "${ROOT_DIR}/frontend"
export API_BASE_URL="${API_BASE_URL:-http://localhost:${BACKEND_PORT}}"
export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://localhost:${BACKEND_PORT}}"
exec npm run dev -- --port "${FRONTEND_PORT}"

