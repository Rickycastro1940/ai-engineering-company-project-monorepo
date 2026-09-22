#!/bin/sh
# Start both Brasaland Next.js apps (Marketing website + staff backoffice).
# NODE_ENV=production → next start; otherwise next dev (Compose bind-mount).
set -eu

if [ "${NODE_ENV:-development}" = "production" ]; then
  npm_script=start
else
  npm_script=dev
fi

term() {
  kill -TERM "$website_pid" "$backoffice_pid" 2>/dev/null || true
  wait
}

trap term INT TERM

cd /uis/website
npm run "$npm_script" -- --hostname 0.0.0.0 --port 3000 &
website_pid=$!

cd /uis/backoffice
npm run "$npm_script" -- --hostname 0.0.0.0 --port 3001 &
backoffice_pid=$!

wait "$website_pid" "$backoffice_pid"
