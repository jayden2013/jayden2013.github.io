#!/usr/bin/env bash
set -euo pipefail

trim() {
  # trims leading/trailing whitespace + strips CRLF
  echo -n "$1" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

GODADDY_SFTP_HOST="$(trim "${GODADDY_SFTP_HOST:-}")"
GODADDY_SFTP_USER="$(trim "${GODADDY_SFTP_USER:-}")"
GODADDY_SFTP_PASS="$(trim "${GODADDY_SFTP_PASS:-}")"
GODADDY_SFTP_PORT="$(trim "${GODADDY_SFTP_PORT:-}")"
GODADDY_SFTP_REMOTE_PATH="$(trim "${GODADDY_SFTP_REMOTE_PATH:-}")"

: "${GODADDY_SFTP_HOST:?Missing GODADDY_SFTP_HOST}"
: "${GODADDY_SFTP_USER:?Missing GODADDY_SFTP_USER}"
: "${GODADDY_SFTP_PASS:?Missing GODADDY_SFTP_PASS}"
: "${GODADDY_SFTP_PORT:?Missing GODADDY_SFTP_PORT}"
: "${GODADDY_SFTP_REMOTE_PATH:?Missing GODADDY_SFTP_REMOTE_PATH}"

LOCAL_DIR="cac"
if [[ ! -d "${LOCAL_DIR}" ]]; then
  echo "ERROR: Local folder '${LOCAL_DIR}' does not exist at repo root."
  exit 2
fi

case "${GODADDY_SFTP_REMOTE_PATH}" in
  ""|"/" )
    echo "ERROR: GODADDY_SFTP_REMOTE_PATH is unsafe (${GODADDY_SFTP_REMOTE_PATH}). Refusing to deploy."
    exit 2
    ;;
esac

echo "Host: '${GODADDY_SFTP_HOST}' (len=${#GODADDY_SFTP_HOST})"
echo "User: '${GODADDY_SFTP_USER}' (len=${#GODADDY_SFTP_USER})"
echo "Port: '${GODADDY_SFTP_PORT}'"
echo "Remote path: '${GODADDY_SFTP_REMOTE_PATH}'"
echo "Local dir: '${LOCAL_DIR}'"

lftp -e "
set cmd:fail-exit yes;
set net:max-retries 1;
set net:timeout 20;
set sftp:auto-confirm yes;
set sftp:connect-program 'ssh -a -x -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p ${GODADDY_SFTP_PORT}';
open -u \"${GODADDY_SFTP_USER}\",\"${GODADDY_SFTP_PASS}\" sftp://${GODADDY_SFTP_HOST};
pwd;
ls;
lcd ${LOCAL_DIR};
cd ${GODADDY_SFTP_REMOTE_PATH};
pwd;
mirror -R --delete --verbose --parallel=4 . .;
bye;
"

echo "Deploy complete."
