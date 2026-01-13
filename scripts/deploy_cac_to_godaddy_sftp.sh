#!/usr/bin/env bash
set -euo pipefail

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

# Safety: avoid nuking a server root accidentally
case "${GODADDY_SFTP_REMOTE_PATH}" in
  ""|"/" )
    echo "ERROR: GODADDY_SFTP_REMOTE_PATH is unsafe (${GODADDY_SFTP_REMOTE_PATH}). Refusing to deploy."
    exit 2
    ;;
esac

echo "Deploying './${LOCAL_DIR}/' -> sftp://${GODADDY_SFTP_HOST}:${GODADDY_SFTP_PORT}${GODADDY_SFTP_REMOTE_PATH}"

# Mirror ./cac contents INTO the remote path.
# --delete keeps remote in sync (removes files no longer in ./cac)
lftp -e "
set net:max-retries 2;
set net:timeout 20;
set sftp:auto-confirm yes;
set sftp:connect-program 'ssh -a -x -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p ${GODADDY_SFTP_PORT}';
open -u \"${GODADDY_SFTP_USER}\",\"${GODADDY_SFTP_PASS}\" sftp://${GODADDY_SFTP_HOST};
lcd ${LOCAL_DIR};
cd ${GODADDY_SFTP_REMOTE_PATH};
mirror -R --delete --verbose --parallel=4 . .;
bye;
"

echo "Deploy complete."
