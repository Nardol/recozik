#!/usr/bin/env bash
set -euo pipefail

# Ensure web UI node_modules are installed when package-lock changes.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEBUI="${ROOT}/packages/recozik-webui"
STAMP="${WEBUI}/node_modules/.deps-stamp"

cd "${WEBUI}"

if [[ ! -f package-lock.json ]]; then
  echo "package-lock.json is missing in ${WEBUI}" >&2
  exit 1
fi

if [[ ! -d node_modules || ! -f "${STAMP}" || "${STAMP}" -ot package-lock.json ]]; then
  npm ci --ignore-scripts --prefer-offline --no-audit --no-fund
  mkdir -p "$(dirname "${STAMP}")"
  touch "${STAMP}"
fi

echo "webui deps OK"
