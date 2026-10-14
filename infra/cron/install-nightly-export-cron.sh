#!/usr/bin/env bash
# Install the Brasaland nightly export into the current user's OS crontab.
# Leaves every other crontab line in place. Does not start FastAPI.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  echo "Missing ${PYTHON}. Create the project virtualenv before installing cron." >&2
  exit 1
fi
LOG="${ROOT}/data/raw/nightly_export.log"
mkdir -p "${ROOT}/data/raw"
touch "${LOG}"

MARKER="# brasaland-nightly-export"
BLOCK=$(cat <<EOF
${MARKER}
CRON_TZ=America/Bogota
0 2 * * * cd ${ROOT} && ${PYTHON} scripts/nightly_export.py >> ${LOG} 2>&1
EOF
)

EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "${EXISTING}" | awk '
  $0 == "# brasaland-nightly-export" { skip=2; next }
  skip > 0 { skip--; next }
  { print }
')"

{
  printf '%s\n' "${FILTERED}" | sed '/^$/d'
  printf '\n%s\n' "${BLOCK}"
} | crontab -

echo "Installed OS crontab for nightly export."
echo "Cron expression: 0 2 * * *"
echo "Timezone: America/Bogota"
echo "Command: ${PYTHON} scripts/nightly_export.py"
crontab -l
