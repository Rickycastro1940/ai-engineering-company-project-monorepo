#!/bin/sh
set -e

if [ -f /app/web/package.json ]; then
	echo "Installing web dependencies..."
	cd /app/web && npm install
fi

if [ -f /app/backoffice/package.json ]; then
	echo "Installing backoffice dependencies..."
	cd /app/backoffice && npm install
fi

echo "Starting web on port 3000..."
cd /app/web && npm run dev -- -H 0.0.0.0 -p 3000 &

echo "Starting backoffice on port 3001..."
cd /app/backoffice && npm run dev -- -H 0.0.0.0 -p 3001 &

wait -n
