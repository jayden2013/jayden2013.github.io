#!/usr/bin/env bash
set -euo pipefail

trim() { printf '%s' "$1" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'; }

HOST="$(trim "${GODADDY_FTP_HOST:-}")"
USER="$(trim "${GODADDY_FTP_USER:-}")"
PASS="$(trim "${GODADDY_FTP_PASS:-}")"
PORT="$(trim "${GODADDY_FTP_PORT:-21}")"
REMOTE_PATH="$(trim "${GODADDY_FTP_REMOTE_PATH:-}")"

: "${HOST:?Missing GODADDY_FTP_HOST}"
: "${USER:?Missing GODADDY_FTP_USER}"
: "${PASS:?Missing GODADDY_FTP_PASS}"
: "${PORT:?Missing GODADDY_FTP_PORT}"
: "${REMOTE_PATH:?Missing GODADDY_FTP_REMOTE_PATH}"

LOCAL_DIR="cac"
if [[ ! -d "${LOCAL_DIR}" ]]; then
  echo "ERROR: Local folder './${LOCAL_DIR}' does not exist at repo root."
  exit 2
fi

# Safety check: don't allow syncing to FTP root
case "${REMOTE_PATH}" in
  ""|"/" )
    echo "ERROR: GODADDY_FTP_REMOTE_PATH is unsafe (${REMOTE_PATH}). Refusing to deploy."
    exit 2
    ;;
esac

echo "==================== FTPS DEPLOY CONFIG ===================="
echo "Local dir:            ./${LOCAL_DIR}/"
echo "Remote host:          ${HOST}"
echo "Remote port:          ${PORT}"
echo "Remote path:          ${REMOTE_PATH}"
echo "Username:             ${USER}"
echo "Password:             (hidden) len=${#PASS}"
echo "Connection string:    ftps://${HOST}:${PORT}${REMOTE_PATH}"
echo "Host hex:             $(printf '%s' "$HOST" | od -An -tx1 | tr -s ' ' | sed 's/^ //')"
echo "User hex:             $(printf '%s' "$USER" | od -An -tx1 | tr -s ' ' | sed 's/^ //')"
echo "Remote path hex:      $(printf '%s' "$REMOTE_PATH" | od -An -tx1 | tr -s ' ' | sed 's/^ //')"
echo "============================================================"

echo "Deploying './${LOCAL_DIR}/' -> ftps://${HOST}:${PORT}${REMOTE_PATH}"

# Explicit FTPS settings:
# - ftp:ssl-force true = require TLS
# - ftp:ssl-protect-data true = protect data channel too
# - ssl:verify-certificate no = avoids cert-chain issues on some shared hosts
#   (If your cert validates cleanly, you can switch this to yes.)
lftp -e "
set cmd:fail-exit yes;
set net:max-retries 2;
set net:timeout 25;

set ftp:ssl-force true;
set ftp:ssl-protect-data true;
set ssl:verify-certificate no;

open -u \"${USER}\",\"${PASS}\" -p ${PORT} ${HOST};

lcd ${LOCAL_DIR};
cd ${REMOTE_PATH};

mirror -R --delete --verbose --parallel=4 . .;

bye;
"
echo "Deploy complete."
