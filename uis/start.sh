#!/bin/sh
# Start both Brasaland Next.js apps in this image (Marketing website + staff backoffice).
set -eu

term() {
  kill -TERM "$website_pid" "$backoffice_pid" 2>/dev/null || true
  wait
}

trap term INT TERM

cd /uis/website
npm run start -- --hostname 0.0.0.0 --port 3000 &
website_pid=$!

cd /uis/backoffice
npm run start -- --hostname 0.0.0.0 --port 3001 &
backoffice_pid=$!

wait "$website_pid" "$backoffice_pid"
